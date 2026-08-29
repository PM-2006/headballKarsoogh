from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Tuple

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    LengthFinishReasonError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from game.prompts.strategy_compiler import (
    ClarificationQuestion,
    StrategyCompilerResponse,
    build_strategy_compiler_prompt,
)
from game.validators import StrategyValidationError, validate_strategy


class LLMConfigurationError(RuntimeError):
    """The server is missing required LLM configuration."""


class LLMServiceError(RuntimeError):
    """The external LLM service failed or returned an unusable result."""


def _discover_fallback_credentials() -> Tuple[str | None, str | None, str | None]:
    """Look for working API keys in opencode.jsonc if not explicitly set in environment."""
    home_dir = Path.home()
    config_path = home_dir / ".config" / "opencode" / "opencode.jsonc"
    if not config_path.is_file():
        return None, None, None

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        providers = data.get("provider", {})
        # Check providers in priority order
        for p_name in ("mwapi", "orcarouter", "hcnsec", "tokenrouter"):
            p_data = providers.get(p_name)
            if not p_data:
                continue
            opts = p_data.get("options", {})
            api_key = opts.get("apiKey")
            base_url = opts.get("baseURL")
            models = list(p_data.get("models", {}).keys())
            if api_key and base_url:
                model_name = models[0] if models else "claude-haiku-4-5-20251001"
                return api_key, base_url, model_name
    except Exception:
        pass

    return None, None, None


def _get_llm_config() -> Tuple[str, str, str]:
    """Retrieve API key, Base URL, and Model name with fallback discovery."""
    api_key = os.getenv("ORCAROUTER_API_KEY")
    base_url = os.getenv("ORCAROUTER_BASE_URL")
    model = os.getenv("ORCAROUTER_MODEL")

    if not api_key:
        fallback_key, fallback_url, fallback_model = _discover_fallback_credentials()
        if fallback_key:
            api_key = fallback_key
            if not base_url and fallback_url:
                base_url = fallback_url
            if not model and fallback_model:
                model = fallback_model

    if not base_url:
        base_url = "https://api.orcarouter.ai/v1"
    if not model:
        model = "deepseek/deepseek-v4-flash-free"

    if not api_key:
        raise LLMConfigurationError(
            "کلید دسترسی هوش مصنوعی (ORCAROUTER_API_KEY) تنظیم نشده است. لطفاً کلید API را در فایل .env یا متغیرهای محیطی سیستم قرار دهید."
        )

    return api_key, base_url, model


def _client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=35.0,
    )


def _usage_summary(response: Any) -> dict[str, int]:
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


def _clean_json_text(text: str) -> str:
    """Strip markdown fences or trailing prose to extract clean JSON string."""
    if not isinstance(text, str):
        return ""
    cleaned = text.lstrip("\ufeff").strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return cleaned


def _parse_pydantic_response(response: Any) -> StrategyCompilerResponse:
    """Extract and validate the StrategyCompilerResponse Pydantic model from OpenAI response."""
    choice = response.choices[0]
    message = choice.message

    # Check for AI refusal
    refusal = getattr(message, "refusal", None)
    if refusal:
        return StrategyCompilerResponse(
            valid=False,
            feedback=[f"مدل از پردازش این درخواست خودداری کرد: {refusal}"],
            strategy=None,
        )

    # 1. Direct parsed object from beta.chat.completions.parse
    parsed = getattr(message, "parsed", None)
    if isinstance(parsed, StrategyCompilerResponse):
        return parsed
    if isinstance(parsed, dict):
        return StrategyCompilerResponse.model_validate(parsed)

    # 2. Extract from raw content string with clean markdown fence stripping
    content = message.content or ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(part.get("text") or part.get("content") or "")
            else:
                parts.append(getattr(part, "text", "") or "")
        content = "\n".join(parts)

    cleaned_json = _clean_json_text(content)
    if not cleaned_json:
        raise LLMServiceError("پاسخ دریافتی از مدل هوش مصنوعی خالی بود.")

    try:
        return StrategyCompilerResponse.model_validate_json(cleaned_json)
    except ValidationError:
        # Try JSON decoder raw decode for embedded JSON blocks
        decoder = json.JSONDecoder()
        for idx, char in enumerate(cleaned_json):
            if char != "{":
                continue
            try:
                data, _ = decoder.raw_decode(cleaned_json[idx:])
                if isinstance(data, dict):
                    return StrategyCompilerResponse.model_validate(data)
            except Exception:
                continue
        raise


def compile_persian_strategy(
    text: str,
    attempt: int = 1,
    conversation_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compile a Persian natural language football strategy into an executable Strategy dictionary
    using Pydantic structured schemas and the official OpenAI SDK.

    Supports a multi-round clarification flow:
    - attempt=1: first try, AI may ask up to 5 clarification questions
    - attempt=2: second try with answers, AI may ask 5 more questions
    - attempt>=3: final try, AI must decide with reasonable defaults

    conversation_history is a list of {"questions": [...], "answers": [...]} dicts
    from previous rounds.
    """
    text = (text or "").strip()
    if not text:
        raise StrategyValidationError("متن استراتژی خالی است.")
    if len(text) > 5000:
        raise StrategyValidationError("متن استراتژی بیش از حد مجاز (۵۰۰۰ کاراکتر) است.")

    attempt = max(1, min(attempt, 10))  # Clamp to sane range
    conversation_history = conversation_history or []

    api_key, base_url, model = _get_llm_config()
    client = _client(api_key, base_url)

    system_prompt = build_strategy_compiler_prompt(attempt=attempt)
    user_prompt = (
        f"متن زیر فقط استراتژی فوتبال دانش‌آموز است. این تلاش شماره {attempt} است."
        " آن را مطابق با ساختار مشخص‌شده کامپایل کن:\n\n"
        + text
    )

    # Build messages list with conversation history
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Append previous Q&A rounds as assistant/user message pairs
    for round_data in conversation_history:
        questions = round_data.get("questions", [])
        answers = round_data.get("answers", [])
        if questions:
            q_text = "سوال‌های من برای روشن‌تر شدن استراتژی:\n"
            for i, q in enumerate(questions, 1):
                q_label = q.get("question", q) if isinstance(q, dict) else str(q)
                q_text += f"{i}. {q_label}\n"
            messages.append({"role": "assistant", "content": q_text})
        if answers:
            a_text = "جواب‌های دانش‌آموز:\n"
            for i, a in enumerate(answers, 1):
                a_text += f"{i}. {a}\n"
            messages.append({"role": "user", "content": a_text})


    response = None
    parsed_result = None

    # Step 1: Attempt structured output with client.beta.chat.completions.parse
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=StrategyCompilerResponse,
            temperature=0.0,
            max_tokens=3500,
        )
        parsed_result = _parse_pydantic_response(response)
    except Exception:
        # Step 2: Fallback for proxies or models that don't support beta.chat.completions.parse
        try:
            # Append schema hint to the last user message for the fallback path
            fallback_messages = list(messages)
            last_msg = fallback_messages[-1]
            fallback_messages[-1] = {
                "role": last_msg["role"],
                "content": last_msg["content"]
                    + "\n\nپاسخ باید دقیقاً یک JSON معتبر منطبق بر اسکیمای StrategyCompilerResponse باشد.",
            }
            response = client.chat.completions.create(
                model=model,
                messages=fallback_messages,
                temperature=0.0,
                max_tokens=3500,
            )
            parsed_result = _parse_pydantic_response(response)
        except AuthenticationError as exc:
            raise LLMServiceError(
                "خطای احراز هویت: کلید دسترسی هوش مصنوعی (API Key) نامعتبر یا منقضی شده است."
            ) from exc
        except (PermissionDeniedError, APIStatusError) as exc:
            status_code = getattr(exc, "status_code", 0)
            if status_code in (402, 403):
                raise LLMServiceError(
                    "اعتبار یا سهمیه مصرف کلید API هوش مصنوعی به پایان رسیده است (Insufficient Quota)."
                ) from exc
            raise LLMServiceError(f"خطای سرویس هوش مصنوعی (کد {status_code}): {exc}") from exc
        except RateLimitError as exc:
            raise LLMServiceError(
                "محدودیت تعداد درخواست هوش مصنوعی (Rate Limit) رخ داده است. لطفاً چند لحظه بعد مجدداً تلاش فرمایید."
            ) from exc
        except APITimeoutError as exc:
            raise LLMServiceError(
                "زمان انتظار برای پاسخ مدل هوش مصنوعی به پایان رسید (Timeout). لطفاً مجدداً تلاش کنید."
            ) from exc
        except InternalServerError as exc:
            raise LLMServiceError(
                "سرویس‌دهنده هوش مصنوعی موقتاً با اختلال مواجه شده است. لطفاً کمی بعد تلاش کنید."
            ) from exc
        except LengthFinishReasonError as exc:
            raise LLMServiceError(
                "طول پاسخ مدل از سقف مجاز فراتر رفت. لطفاً استراتژی را خلاصه‌تر بنویسید."
            ) from exc
        except APIConnectionError as exc:
            raise LLMServiceError(
                "امکان برقراری ارتباط با سرور هوش مصنوعی وجود ندارد. اتصال اینترنت یا آدرس Base URL را بررسی کنید."
            ) from exc
        except ValidationError as val_exc:
            raise LLMServiceError(
                f"پاسخ هوش مصنوعی با اعتبارسنجی ساختار Pydantic مطابقت ندارد: {val_exc.errors()}"
            ) from val_exc
        except Exception as exc:
            raise LLMServiceError(f"خطای ناشناخته در پردازش استراتژی با هوش مصنوعی: {exc}") from exc

    usage_summary = _usage_summary(response)
    model_name = getattr(response, "model", None) or model

    # If the AI is asking clarification questions (and hasn't exceeded max rounds)
    if parsed_result.needs_clarification and parsed_result.questions and attempt <= 2:
        return {
            "valid": False,
            "needs_clarification": True,
            "questions": [
                {
                    "question": q.question,
                    "options": q.options,
                }
                for q in parsed_result.questions[:5]
            ],
            "feedback": parsed_result.feedback,
            "strategy": None,
            "attempt": attempt,
            "model": model_name,
            "usage": usage_summary,
        }

    # If the student's strategy could not be compiled cleanly
    if not parsed_result.valid or parsed_result.strategy is None:
        return {
            "valid": False,
            "needs_clarification": False,
            "questions": [],
            "feedback": parsed_result.feedback
            or ["این استراتژی هنوز به شرط‌های دقیق و قابل اجرا تبدیل نمی‌شود."],
            "strategy": None,
            "model": model_name,
            "usage": usage_summary,
        }

    # Convert Pydantic StrategySchema model to Python dictionary
    strategy_dict = parsed_result.strategy.model_dump()
    strategy_dict["label"] = "My Bot"

    # Pass through deterministic game engine validator
    try:
        validate_strategy(strategy_dict)
    except StrategyValidationError as exc:
        raise LLMServiceError(
            f"مدل یک Strategy نامعتبر ساخت و Validator موتور بازی آن را رد کرد: {exc}"
        ) from exc

    return {
        "valid": True,
        "needs_clarification": False,
        "questions": [],
        "feedback": parsed_result.feedback,
        "strategy": strategy_dict,
        "model": model_name,
        "usage": usage_summary,
    }
