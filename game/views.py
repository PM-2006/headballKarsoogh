from __future__ import annotations
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .engine import batch_matches, simulate_match
from .strategy import get_preset, vocabulary
from .validators import StrategyValidationError, validate_strategy
from .services.llm import (
    LLMConfigurationError,
    LLMServiceError,
    compile_persian_strategy,
)

def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StrategyValidationError("Request body must be valid JSON.") from exc

def _resolve_strategy(payload, key):
    item = payload.get(key)
    if not isinstance(item, dict):
        raise StrategyValidationError(f"{key} must be an object.")
    if "preset" in item:
        try:
            return get_preset(item["preset"])
        except KeyError as exc:
            raise StrategyValidationError(str(exc)) from exc
    strategy = item.get("strategy")
    if strategy is None:
        raise StrategyValidationError(f"{key} must contain either 'preset' or 'strategy'.")
    return validate_strategy(strategy)

@login_required
@ensure_csrf_cookie
def index(request):
    return render(request, "game/index.html")

@login_required
@require_GET
def api_vocabulary(request):
    return JsonResponse(vocabulary())

@login_required
@require_POST
def api_validate_strategy(request):
    try:
        payload = _json_body(request)
        strategy = validate_strategy(payload.get("strategy"))
        return JsonResponse({"valid": True, "strategy": strategy})
    except StrategyValidationError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=400)

@login_required
@require_POST
def api_simulate(request):
    try:
        payload = _json_body(request)
        blue = _resolve_strategy(payload, "blue")
        red = _resolve_strategy(payload, "red")
        seed = int(payload.get("seed", 1))
        return JsonResponse(simulate_match(blue, red, seed=seed, record_frames=True))
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

@login_required
@require_POST
def api_batch(request):
    try:
        payload = _json_body(request)
        blue = _resolve_strategy(payload, "blue")
        red = _resolve_strategy(payload, "red")
        seed = int(payload.get("seed", 1))
        matches = int(payload.get("matches", 100))
        return JsonResponse(batch_matches(blue, red, matches=matches, seed=seed))
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_POST
def api_compile_strategy(request):
    try:
        payload = _json_body(request)
        result = compile_persian_strategy(payload.get("text", ""))
        return JsonResponse(result)
    except StrategyValidationError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=400)
    except LLMConfigurationError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=503)
    except LLMServiceError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=502)
