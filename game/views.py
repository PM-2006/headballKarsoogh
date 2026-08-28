from __future__ import annotations
import json
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .engine import batch_matches, simulate_match
from .gameconfig import (
    config_with_overrides,
    reset_overrides,
    save_overrides,
    spec as config_spec,
)
from .models import SavedStrategy
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


def _name_taken_by_other(name: str, user) -> bool:
    """True if a *different* user already owns a bot with this name.

    Names must be globally unique across users so a bot's name identifies its
    creator, but a single user may reuse their own names as often as they like.
    """
    return (
        SavedStrategy.objects.filter(name__iexact=name)
        .exclude(user=user)
        .exists()
    )

def _resolve_strategy(payload, key, user=None):
    item = payload.get(key)
    if not isinstance(item, dict):
        raise StrategyValidationError(f"{key} must be an object.")
    if "preset" in item:
        try:
            return get_preset(item["preset"])
        except KeyError as exc:
            raise StrategyValidationError(str(exc)) from exc
    if "strategy_id" in item:
        try:
            strategy_id = int(item["strategy_id"])
        except (ValueError, TypeError):
            raise StrategyValidationError(f"شناسه استراتژی {key} نامعتبر است.")
        try:
            saved = SavedStrategy.objects.select_related("user").get(id=strategy_id)
        except SavedStrategy.DoesNotExist:
            raise StrategyValidationError(f"استراتژی با شناسه {strategy_id} یافت نشد.")

        if user and not (saved.user == user or saved.is_admin_strategy or user.is_staff or user.is_superuser):
            raise StrategyValidationError(f"شما اجازه دسترسی به استراتژی {saved.name} را ندارید.")
        return validate_strategy(saved.strategy_data)

    strategy = item.get("strategy")
    if strategy is None:
        raise StrategyValidationError(f"{key} must contain either 'preset', 'strategy_id', or 'strategy'.")
    return validate_strategy(strategy)

@login_required
@ensure_csrf_cookie
def index(request):
    from .engine import get_game_config
    # "Students" are ordinary players: they get the guided AI-only builder,
    # while staff/superusers keep the manual rule editor and the raw JSON view.
    is_student = not (request.user.is_staff or request.user.is_superuser)
    return render(
        request,
        "game/index.html",
        {
            "game_config": get_game_config().to_dict(),
            "is_student": is_student,
        },
    )

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
@require_http_methods(["GET", "POST"])
def api_strategies(request):
    if request.method == "GET":
        is_admin = bool(request.user.is_staff or request.user.is_superuser)
        my_strategies = request.user.saved_strategies.select_related("user__kit").all()
        public_strategies = SavedStrategy.objects.filter(
            Q(is_public=True) | Q(user__is_staff=True) | Q(user__is_superuser=True)
        ).exclude(user=request.user).select_related("user__kit")

        resp = {
            "is_admin": is_admin,
            "username": request.user.username,
            "my_strategies": [
                {**s.to_dict(), "is_owner": True} for s in my_strategies
            ],
            "public_strategies": [
                {**s.to_dict(), "is_owner": False} for s in public_strategies
            ],
        }
        # Admins may line up and work with every bot ever made by any user.
        if is_admin:
            everyone = SavedStrategy.objects.select_related("user__kit").order_by(
                "user__username", "name"
            )
            resp["all_strategies"] = [
                {**s.to_dict(), "is_owner": s.user_id == request.user.id}
                for s in everyone
            ]
        return JsonResponse(resp)

    # POST: Create a new strategy
    try:
        payload = _json_body(request)
        name = (payload.get("name") or "").strip()
        if not name:
            return JsonResponse({"error": "نام استراتژی الزامی است."}, status=400)
        if len(name) > 120:
            return JsonResponse({"error": "نام استراتژی حداکثر می‌تواند ۱۲۰ کاراکتر باشد."}, status=400)
        if _name_taken_by_other(name, request.user):
            return JsonResponse(
                {"error": f"نام «{name}» قبلاً توسط کاربر دیگری استفاده شده است. یک نام دیگر انتخاب کنید."},
                status=409,
            )

        raw_strategy = payload.get("strategy")
        if not raw_strategy:
            return JsonResponse({"error": "داده‌های استراتژی ارسال نشده است."}, status=400)

        validated_strategy = validate_strategy(raw_strategy)
        ai_prompt = payload.get("ai_prompt", "").strip()
        description = payload.get("description", "").strip()
        is_public = bool(payload.get("is_public", False)) and (request.user.is_staff or request.user.is_superuser)

        saved = SavedStrategy.objects.create(
            user=request.user,
            name=name,
            description=description,
            ai_prompt=ai_prompt,
            strategy_data=validated_strategy,
            is_public=is_public,
        )
        return JsonResponse({
            "success": True,
            "message": "استراتژی با موفقیت ذخیره شد.",
            "strategy": {**saved.to_dict(), "is_owner": True},
        }, status=201)
    except StrategyValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except ValidationError as exc:
        return JsonResponse({"error": str(exc.messages if hasattr(exc, "messages") else exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": f"خطا در ذخیره‌سازی: {exc}"}, status=500)


@login_required
@require_http_methods(["GET", "PUT", "POST", "DELETE"])
def api_strategy_detail(request, pk: int):
    try:
        saved = SavedStrategy.objects.select_related("user").get(pk=pk)
    except SavedStrategy.DoesNotExist:
        return JsonResponse({"error": "استراتژی یافت نشد."}, status=404)

    is_owner = (saved.user == request.user)
    is_admin = (request.user.is_staff or request.user.is_superuser)

    if request.method == "GET":
        if not (is_owner or saved.is_admin_strategy or is_admin):
            return JsonResponse({"error": "شما اجازه دسترسی به این استراتژی را ندارید."}, status=403)
        # Read-only viewing of official/public bots is open to everyone; editing
        # stays restricted to the owner (enforced on the PUT/POST/DELETE paths).
        return JsonResponse({
            "strategy": {**saved.to_dict(), "is_owner": is_owner},
        })

    if request.method == "DELETE":
        if not (is_owner or is_admin):
            return JsonResponse({"error": "شما اجازه حذف این استراتژی را ندارید."}, status=403)
        saved.delete()
        return JsonResponse({"success": True, "message": "استراتژی با موفقیت حذف شد."})

    # PUT or POST for update
    if not (is_owner or is_admin):
        return JsonResponse({"error": "شما اجازه ویرایش این استراتژی را ندارید."}, status=403)

    try:
        payload = _json_body(request)
        if "name" in payload:
            name = (payload.get("name") or "").strip()
            if not name:
                return JsonResponse({"error": "نام استراتژی نمی‌تواند خالی باشد."}, status=400)
            # Name must stay unique across users (checked against the bot's owner,
            # not the editor, so an admin editing a bot can't steal another's name).
            if _name_taken_by_other(name, saved.user):
                return JsonResponse(
                    {"error": f"نام «{name}» قبلاً توسط کاربر دیگری استفاده شده است. یک نام دیگر انتخاب کنید."},
                    status=409,
                )
            saved.name = name

        if "description" in payload:
            saved.description = payload.get("description", "").strip()

        if "ai_prompt" in payload:
            saved.ai_prompt = payload.get("ai_prompt", "").strip()

        if "strategy" in payload:
            validated_strategy = validate_strategy(payload["strategy"])
            saved.strategy_data = validated_strategy

        if "is_public" in payload and is_admin:
            saved.is_public = bool(payload["is_public"])

        saved.save()
        return JsonResponse({
            "success": True,
            "message": "استراتژی با موفقیت به‌روزرسانی شد.",
            "strategy": {**saved.to_dict(), "is_owner": is_owner},
        })
    except StrategyValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except ValidationError as exc:
        return JsonResponse({"error": str(exc.messages if hasattr(exc, "messages") else exc)}, status=400)
    except Exception as exc:
        return JsonResponse({"error": f"خطا در ویرایش استراتژی: {exc}"}, status=500)


@login_required
@require_POST
def api_simulate(request):
    try:
        payload = _json_body(request)
        blue = _resolve_strategy(payload, "blue", user=request.user)
        red = _resolve_strategy(payload, "red", user=request.user)
        seed = int(payload.get("seed", 1))
        # Superusers may preview a match with unsaved config overrides.
        config = None
        overrides = payload.get("overrides")
        if overrides and request.user.is_superuser:
            config = config_with_overrides(overrides)
        return JsonResponse(
            simulate_match(blue, red, seed=seed, record_frames=True, config=config)
        )
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

@login_required
@require_POST
def api_batch(request):
    try:
        payload = _json_body(request)
        blue = _resolve_strategy(payload, "blue", user=request.user)
        red = _resolve_strategy(payload, "red", user=request.user)
        seed = int(payload.get("seed", 1))
        matches = int(payload.get("matches", 100))
        return JsonResponse(batch_matches(blue, red, matches=matches, seed=seed))
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def api_kit(request):
    """Get the current user's team-kit colours + the palette, or save new ones."""
    from .kits import PALETTE
    from .models import PlayerKit

    kit = PlayerKit.for_user(request.user)
    if request.method == "POST":
        from .kits import sanitize_kit
        try:
            payload = _json_body(request)
        except StrategyValidationError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        colors = sanitize_kit(payload.get("colors"))
        kit.home, kit.away, kit.alternative = colors
        kit.save()
        return JsonResponse({
            "success": True,
            "message": "رنگ‌های تیم ذخیره شد.",
            "colors": kit.colors(),
        })
    return JsonResponse({"palette": PALETTE, "colors": kit.colors()})


def _forbidden():
    return JsonResponse({"error": "دسترسی فقط برای مدیر ارشد مجاز است."}, status=403)


@login_required
@require_http_methods(["GET", "POST"])
def api_game_config(request):
    """Superuser-only: read the tunable config spec (GET) or save overrides (POST)."""
    if not request.user.is_superuser:
        return _forbidden()

    from .engine import get_game_config

    if request.method == "GET":
        return JsonResponse({"groups": config_spec(get_game_config())})

    try:
        payload = _json_body(request)
        stored = save_overrides(payload.get("values") or {}, user=request.user)
        cfg = get_game_config()
        return JsonResponse({
            "success": True,
            "message": "تنظیمات بازی ذخیره شد.",
            "stored": stored,
            "config": cfg.to_dict(),
            "groups": config_spec(cfg),
        })
    except StrategyValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        return JsonResponse({"error": f"خطا در ذخیره تنظیمات: {exc}"}, status=500)


@login_required
@require_POST
def api_game_config_reset(request):
    """Superuser-only: clear all overrides, back to code/env defaults."""
    if not request.user.is_superuser:
        return _forbidden()
    from .engine import get_game_config

    reset_overrides(user=request.user)
    cfg = get_game_config()
    return JsonResponse({
        "success": True,
        "message": "تنظیمات بازی به حالت پیش‌فرض بازگشت.",
        "config": cfg.to_dict(),
        "groups": config_spec(cfg),
    })


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
