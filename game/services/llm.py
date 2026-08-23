from __future__ import annotations

import json
import os
import re

from openai import OpenAI

from game.prompts.strategy_compiler import build_strategy_compiler_prompt
from game.validators import StrategyValidationError, validate_strategy


ORCAROUTER_BASE_URL = os.getenv(
    "ORCAROUTER_BASE_URL",
    "https://api.orcarouter.ai/v1",
)
ORCAROUTER_MODEL = os.getenv(
    "ORCAROUTER_MODEL",
    "deepseek/deepseek-v4-flash-free",
)


class LLMConfigurationError(RuntimeError):
    """The server is missing required LLM configuration."""


class LLMServiceError(RuntimeError):
    """The external LLM service failed or returned an unusable result."""


def _client() -> OpenAI:
    api_key = os.getenv("ORCAROUTER_API_KEY")
    if not api_key:
        raise LLMConfigurationError(
            "ORCAROUTER_API_KEY تنظیم نشده است. کلید OrcaRouter را فقط روی سرور به‌صورت متغیر محیطی قرار بده."
        )

    return OpenAI(
        base_url=ORCAROUTER_BASE_URL,
        api_key=api_key,
        timeout=45.0,
    )


def _usage_summary(response) -> dict:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def _response_content(response) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMServiceError(
            "ساختار پاسخ OrcaRouter قابل خواندن نبود."
        ) from exc

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                value = part.get("text") or part.get("content")
            else:
                value = getattr(part, "text", None)
            if isinstance(value, str):
                parts.append(value)
        return "\n".join(parts).strip()

    return ""


def _parse_json_object(content: str) -> dict:
    """Extract a valid JSON object without inventing or repairing fields."""
    if not isinstance(content, str):
        raise json.JSONDecodeError("response is not text", "", 0)

    text = content.lstrip("\ufeff").strip()
    if not text:
        raise json.JSONDecodeError("empty response", text, 0)

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    fence_match = re.fullmatch(
        r"\s*```(?:json)?\s*(.*?)\s*```\s*",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence_match:
        fenced = fence_match.group(1).strip()
        try:
            value = json.loads(fenced)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    raise json.JSONDecodeError("no valid JSON object found", text, 0)


def _request_orcarouter(text: str, *, strict_retry: bool = False):
    retry_instruction = ""
    if strict_retry:
        retry_instruction = (
            "\n\nاین درخواست تکراری است چون پاسخ قبلی JSON قابل خواندن نبود. "
            "این بار پاسخ باید دقیقاً یک JSON object باشد؛ "
            "اولین کاراکتر { و آخرین کاراکتر } باشد. "
            "هیچ Markdown، code fence، توضیح یا متن دیگری ننویس."
        )

    try:
        return _client().chat.completions.create(
            model=ORCAROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": build_strategy_compiler_prompt(),
                },
                {
                    "role": "user",
                    "content": (
                        "متن زیر فقط استراتژی دانش‌آموز است. آن را طبق System Prompt کامپایل کن:\n\n"
                        + text
                        + retry_instruction
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.0 if strict_retry else 0.1,
            max_tokens=3500,
        )
    except Exception as exc:
        raise LLMServiceError(
            f"خطا در ارتباط با OrcaRouter: {exc}"
        ) from exc


def _compile_response(response) -> dict:
    content = _response_content(response)
    if not content:
        raise json.JSONDecodeError("empty model response", "", 0)
    return _parse_json_object(content)


def compile_persian_strategy(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise StrategyValidationError("متن استراتژی خالی است.")
    if len(text) > 5000:
        raise StrategyValidationError("متن استراتژی بیش از حد طولانی است.")

    response = _request_orcarouter(text)

    try:
        compiled = _compile_response(response)
    except json.JSONDecodeError:
        response = _request_orcarouter(text, strict_retry=True)
        try:
            compiled = _compile_response(response)
        except json.JSONDecodeError as exc:
            raise LLMServiceError(
                "مدل حتی پس از تلاش مجدد JSON قابل‌خواندن برنگرداند. دوباره تلاش کن یا متن استراتژی را کمی ساده‌تر بنویس."
            ) from exc

    if not isinstance(compiled, dict) or "valid" not in compiled:
        raise LLMServiceError(
            "خروجی مدل ساختار مورد انتظار را ندارد."
        )

    feedback = compiled.get("feedback")
    if not isinstance(feedback, list):
        feedback = []

    usage_summary = _usage_summary(response)
    model_name = getattr(response, "model", None) or ORCAROUTER_MODEL

    if compiled.get("valid") is not True:
        return {
            "valid": False,
            "feedback": feedback or [
                "این استراتژی هنوز به شرط‌های دقیق و قابل اجرا تبدیل نمی‌شود."
            ],
            "strategy": None,
            "model": model_name,
            "usage": usage_summary,
        }

    strategy = compiled.get("strategy")
    try:
        validate_strategy(strategy)
    except StrategyValidationError as exc:
        raise LLMServiceError(
            f"مدل یک Strategy نامعتبر ساخت و Validator بازی آن را رد کرد: {exc}"
        ) from exc

    strategy["label"] = "My Bot"

    return {
        "valid": True,
        "feedback": feedback,
        "strategy": strategy,
        "model": model_name,
        "usage": usage_summary,
    }
