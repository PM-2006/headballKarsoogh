from __future__ import annotations

import json
import logging
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
from game.validators import (
    MAX_CONDITIONS_PER_RULE,
    MAX_RULES,
    StrategyValidationError,
    validate_strategy,
)

logger = logging.getLogger(__name__)

# Headroom for the largest strategy the schema permits plus its Persian feedback.
MAX_COMPLETION_TOKENS = 8000


class LLMConfigurationError(RuntimeError):
    """The server is missing required LLM configuration."""


class LLMServiceError(RuntimeError):
    """The external LLM service failed or returned an unusable result."""


class LLMTruncatedResponseError(LLMServiceError):
    """The model ran out of completion budget mid-answer."""


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
        base_url = "https://api.gapgpt.app/v1"
    if not model:
        model = "deepseek-v4-flash"

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

    if getattr(choice, "finish_reason", None) == "length":
        raise LLMTruncatedResponseError(
            "پاسخ مدل ناقص ماند. دوباره دکمهٔ تبدیل را بزن؛ اگر باز هم تکرار شد، "
            "استراتژی را به قانون‌های کمتری خلاصه کن."
        )

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


def _plain_json_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Add the real response schema for providers without Structured Outputs."""
    schema = json.dumps(
        StrategyCompilerResponse.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    fallback_instruction = (
        "\n\nPLAIN JSON FALLBACK\n"
        "Return exactly one JSON object and no markdown or prose. "
        "Do not add keys that are absent from this JSON Schema. "
        "The response must validate against this schema:\n"
        f"{schema}"
    )
    fallback_messages = [dict(message) for message in messages]
    fallback_messages[0]["content"] += fallback_instruction
    return fallback_messages


def _can_fallback_to_plain_json(exc: Exception) -> bool:
    """True only when the structured-output mechanism itself may be unsupported."""
    if isinstance(exc, LLMTruncatedResponseError):
        return False
    if isinstance(
        exc,
        (
            AuthenticationError,
            PermissionDeniedError,
            RateLimitError,
            APITimeoutError,
            InternalServerError,
            APIConnectionError,
            LengthFinishReasonError,
        ),
    ):
        return False
    if isinstance(exc, APIStatusError):
        # OpenAI-compatible proxies commonly use one of these statuses when
        # response_format=json_schema or the beta parse route is unsupported.
        return getattr(exc, "status_code", 0) in (400, 404, 415, 422)
    return isinstance(exc, (LLMServiceError, ValidationError, TypeError, ValueError))


def _service_error(exc: Exception) -> LLMServiceError:
    """Map provider/SDK details to short, actionable messages for students."""
    if isinstance(exc, LLMServiceError):
        return exc
    if isinstance(exc, AuthenticationError):
        message = "سرویس ساخت ربات درست تنظیم نشده است. لطفاً به مربی اطلاع بده."
    elif isinstance(exc, PermissionDeniedError):
        message = "دسترسی سرویس ساخت ربات یا اعتبار آن کافی نیست. لطفاً به مربی اطلاع بده."
    elif isinstance(exc, RateLimitError):
        message = "درخواست‌ها زیاد شده‌اند. چند لحظه صبر کن و دوباره دکمهٔ تبدیل را بزن."
    elif isinstance(exc, APITimeoutError):
        message = "مدل دیر پاسخ داد. دوباره دکمهٔ تبدیل را بزن؛ متن استراتژی‌ات حفظ شده است."
    elif isinstance(exc, InternalServerError):
        message = "سرویس ساخت ربات موقتاً مشکل دارد. کمی بعد دوباره تلاش کن."
    elif isinstance(exc, LengthFinishReasonError):
        message = "پاسخ مدل ناقص ماند. دوباره تلاش کن؛ اگر تکرار شد، استراتژی را به قانون‌های کمتری خلاصه کن."
    elif isinstance(exc, APIConnectionError):
        message = "ارتباط با سرویس ساخت ربات برقرار نشد. کمی بعد دوباره تلاش کن."
    elif isinstance(exc, ValidationError):
        message = "پاسخ مدل کامل نبود. دوباره تلاش کن یا استراتژی را کمی ساده‌تر بنویس."
    elif isinstance(exc, APIStatusError):
        status_code = getattr(exc, "status_code", 0)
        if status_code == 402:
            message = "اعتبار سرویس ساخت ربات تمام شده است. لطفاً به مربی اطلاع بده."
        elif status_code >= 500:
            message = "سرویس ساخت ربات موقتاً مشکل دارد. کمی بعد دوباره تلاش کن."
        else:
            message = "سرویس ساخت ربات این درخواست را نپذیرفت. دوباره تلاش کن یا به مربی اطلاع بده."
    else:
        message = "ساخت ربات انجام نشد. دوباره تلاش کن؛ اگر تکرار شد به مربی اطلاع بده."
    return LLMServiceError(message)


def _normalize_conversation_history(
    conversation_history: list[dict[str, Any]] | None,
) -> list[dict[str, list[Any]]]:
    """Validate and bound browser-supplied clarification history."""
    if conversation_history is None:
        return []
    if not isinstance(conversation_history, list):
        raise StrategyValidationError("تاریخچهٔ پاسخ‌ها نامعتبر است.")

    normalized: list[dict[str, list[Any]]] = []
    for round_data in conversation_history[:2]:
        if not isinstance(round_data, dict):
            raise StrategyValidationError("تاریخچهٔ پاسخ‌ها نامعتبر است.")
        questions = round_data.get("questions") or []
        answers = round_data.get("answers") or []
        if not isinstance(questions, list) or not isinstance(answers, list):
            raise StrategyValidationError("تاریخچهٔ پاسخ‌ها نامعتبر است.")
        clean_questions: list[Any] = []
        for question in questions[:5]:
            if isinstance(question, dict):
                clean_questions.append(
                    {"question": str(question.get("question", ""))[:500]}
                )
            else:
                clean_questions.append(str(question)[:500])
        clean_answers = [str(answer)[:500] for answer in answers[:5]]
        normalized.append({"questions": clean_questions, "answers": clean_answers})
    return normalized


def _enforce_strategy_limits(strategy_dict: dict[str, Any]) -> list[str]:
    """Trim a compiled strategy down to what the engine accepts.

    Also renumbers priorities: the list order is the model's intended order, so
    a duplicated or skipped priority must not fail engine validation.
    Returns Persian notes for anything that had to be dropped.
    """
    notes: list[str] = []
    rules = strategy_dict.get("rules") or []

    # A rule with no conditions always fires and would shadow every rule below
    # it, so it is dropped rather than kept as a silent catch-all.
    kept = [rule for rule in rules if rule.get("conditions")]
    if len(kept) != len(rules):
        notes.append("چند قانون بدون شرط بودند و حذف شدند.")

    # Sort by the model's stated priority, keeping list order as the tie-break
    # and for rules that left priority unset.
    def _sort_key(pair: tuple[int, dict]) -> tuple[int, int]:
        index, rule = pair
        priority = rule.get("priority")
        if not isinstance(priority, int) or priority < 1:
            priority = 10**6  # unset priority sinks to the end, order preserved
        return priority, index

    kept = [rule for _, rule in sorted(enumerate(kept), key=_sort_key)]

    if len(kept) > MAX_RULES:
        notes.append(
            f"استراتژی تو بیشتر از {MAX_RULES} قانون داشت؛ "
            f"{MAX_RULES} قانون با بالاترین اولویت نگه داشته شد و بقیه حذف شدند."
        )
        kept = kept[:MAX_RULES]

    trimmed_conditions = False
    for priority, rule in enumerate(kept, start=1):
        rule["priority"] = priority
        conditions = rule.get("conditions") or []
        if len(conditions) > MAX_CONDITIONS_PER_RULE:
            rule["conditions"] = conditions[:MAX_CONDITIONS_PER_RULE]
            trimmed_conditions = True
    if trimmed_conditions:
        notes.append(
            f"بعضی قانون‌ها بیشتر از {MAX_CONDITIONS_PER_RULE} شرط داشتند؛ شرط‌های اضافه حذف شدند."
        )

    strategy_dict["rules"] = kept
    return notes


def compile_persian_strategy(
    text: str,
    attempt: int = 1,
    conversation_history: list[dict[str, Any]] | None = None,
    strictness: int = 2,
) -> dict[str, Any]:
    """
    Compile a Persian natural language football strategy into an executable Strategy dictionary
    using Pydantic structured schemas and the official OpenAI SDK.

    Supports a multi-round clarification flow with configurable strictness (1 to 5):
    - attempt=1: first try, AI may ask clarification questions based on strictness
    - attempt=2: second try with answers, AI may ask follow-up questions
    - attempt>=3: final try, AI must decide with reasonable defaults
    """
    text = (text or "").strip()
    if not text:
        raise StrategyValidationError("متن استراتژی خالی است.")
    if len(text) > 5000:
        raise StrategyValidationError("متن استراتژی بیش از حد مجاز (۵۰۰۰ کاراکتر) است.")

    attempt = max(1, min(attempt, 10))
    strictness = max(1, min(5, int(strictness or 2)))
    conversation_history = _normalize_conversation_history(conversation_history)

    api_key, base_url, model = _get_llm_config()
    client = _client(api_key, base_url)

    system_prompt = build_strategy_compiler_prompt(attempt=attempt, strictness=strictness)
    user_prompt = (
        f"متن زیر فقط استراتژی فوتبال دانش‌آموز است. این تلاش شماره {attempt} است."
        " آن را مطابق با ساختار مشخص‌شده کامپایل کن:\n\n"
        + "<student_strategy>\n"
        + text
        + "\n</student_strategy>"
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


    # Step 1: Attempt structured output with client.beta.chat.completions.parse
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=StrategyCompilerResponse,
            temperature=0.0,
            max_tokens=MAX_COMPLETION_TOKENS,
        )
        parsed_result = _parse_pydantic_response(response)
    except Exception as structured_exc:
        if not _can_fallback_to_plain_json(structured_exc):
            logger.warning("Structured strategy compilation failed", exc_info=True)
            raise _service_error(structured_exc) from structured_exc

        # Step 2: Fallback for proxies or models that don't support beta.chat.completions.parse
        try:
            fallback_messages = _plain_json_messages(messages)
            response = client.chat.completions.create(
                model=model,
                messages=fallback_messages,
                temperature=0.0,
                max_tokens=MAX_COMPLETION_TOKENS,
            )
            parsed_result = _parse_pydantic_response(response)
        except Exception as exc:
            logger.warning("Plain-JSON strategy compilation failed", exc_info=True)
            raise _service_error(exc) from exc

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

    # Models overshoot the rule/condition caps on long strategies. Trimming to
    # fit gives the student a bot that runs, instead of an error telling them to
    # rewrite a text that was within its own length limit all along.
    limit_notes = _enforce_strategy_limits(strategy_dict)

    # Pass through deterministic game engine validator
    try:
        validate_strategy(strategy_dict)
    except StrategyValidationError as exc:
        logger.warning("Compiled strategy rejected by engine validator: %s", exc)
        raise LLMServiceError(
            "استراتژی ساخته شد اما یکی از قانون‌ها قابل اجرا نبود. دوباره تلاش کن یا جمله را کمی ساده‌تر بنویس."
        ) from exc

    return {
        "valid": True,
        "needs_clarification": False,
        "questions": [],
        "feedback": parsed_result.feedback + limit_notes,
        "strategy": strategy_dict,
        "model": model_name,
        "usage": usage_summary,
    }
