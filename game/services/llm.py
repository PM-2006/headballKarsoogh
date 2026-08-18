from __future__ import annotations

import json
import os

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


def _request_orcarouter(text: str):
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
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=2200,
        )
    except Exception as exc:
        raise LLMServiceError(
            f"خطا در ارتباط با OrcaRouter: {exc}"
        ) from exc


def compile_persian_strategy(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise StrategyValidationError("متن استراتژی خالی است.")
    if len(text) > 5000:
        raise StrategyValidationError("متن استراتژی بیش از حد طولانی است.")

    response = _request_orcarouter(text)

    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMServiceError(
            "ساختار پاسخ OrcaRouter قابل خواندن نبود."
        ) from exc

    if not content:
        raise LLMServiceError(
            "مدل پاسخ خالی برگرداند. دوباره تلاش کن."
        )

    try:
        compiled = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMServiceError(
            "مدل JSON معتبر برنگرداند."
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
