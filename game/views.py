from __future__ import annotations
import functools
import hashlib
import json
import logging
import threading
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .engine import (
    DEFAULT_BATCH_MATCHES,
    MAX_BATCH_MATCHES,
    PHYSICS_VERSION,
    batch_matches,
    get_game_config,
    simulate_match,
)
from .gameconfig import (
    MAX_SESSION_LIMIT,
    MIN_SESSION_LIMIT,
    config_with_overrides,
    get_session_limit,
    is_game_enabled,
    set_game_enabled,
    set_session_limit,
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

logger = logging.getLogger(__name__)


def api_login_required(view):
    """@login_required for JSON endpoints: answers 401 instead of redirecting.

    The stock decorator sends an unauthenticated caller a 302 to the HTML login
    page. fetch() follows redirects transparently, so the browser ends up
    handing response.json() a login page carrying status 200 -- the request
    looks successful and the parse fails, which surfaced to students as
    "the server response could not be read" when all that had happened was that
    their session ended. A 401 with a JSON body lets the client say so plainly.
    """

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {
                    "error": "نشست شما به پایان رسیده است. دوباره وارد شو.",
                    "auth_required": True,
                },
                status=401,
            )
        return view(request, *args, **kwargs)

    return wrapper

# Only one batch at a time per worker process. A batch is a pure-CPU loop, so
# running two in one process just splits a single core between them and makes
# both slower; run gunicorn with one worker per vCPU to use every core.
_BATCH_SLOT = threading.BoundedSemaphore(1)

BATCH_BUSY_MESSAGE = "سرور مشغول است. کمی بعد دوباره تلاش کن."


def _result_key(kind, config, *parts):
    """Cache key for a deterministic engine result.

    A match is a pure function of the strategies, the seed and the effective
    game config. The config is hashed in because superusers can retune the
    physics at runtime, which must invalidate every result computed under the
    old settings rather than serve a replay that no longer matches the engine.
    """
    blob = json.dumps([config.to_dict(), *parts], sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]
    return f"{kind}:{PHYSICS_VERSION}:{digest}"


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

@require_GET
def healthz(request):
    """Unauthenticated liveness probe for the container healthcheck.

    The check used to call /api/vocabulary/. Once that endpoint required a
    session it answered with a redirect to the login page, so the probe was
    really only asserting that the login page renders -- it would have reported
    a healthy container with a completely broken API.
    """
    return JsonResponse({"status": "ok"})


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

@api_login_required
@require_GET
def api_vocabulary(request):
    return JsonResponse(vocabulary())

@api_login_required
@require_POST
def api_validate_strategy(request):
    try:
        payload = _json_body(request)
        strategy = validate_strategy(payload.get("strategy"))
        return JsonResponse({"valid": True, "strategy": strategy})
    except StrategyValidationError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=400)

@api_login_required
@require_http_methods(["GET", "POST"])
def api_strategies(request):
    if request.method == "GET":
        is_admin = bool(request.user.is_superuser)
        my_strategies = request.user.saved_strategies.select_related("user__kit").all()
        public_strategies = SavedStrategy.objects.filter(
            Q(user__is_superuser=True) | Q(is_public=True, user__is_staff=False)
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
        is_public = bool(payload.get("is_public", False)) and request.user.is_superuser

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


@api_login_required
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


@api_login_required
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
        if config is None:
            config = get_game_config()
        key = _result_key("sim", config, blue, red, seed)
        result = cache.get(key)
        if result is None:
            result = simulate_match(blue, red, seed=seed, record_frames=True, config=config)
            cache.set(key, result)
        return JsonResponse(result)
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

@api_login_required
@require_POST
def api_batch(request):
    try:
        payload = _json_body(request)
        blue = _resolve_strategy(payload, "blue", user=request.user)
        red = _resolve_strategy(payload, "red", user=request.user)
        seed = int(payload.get("seed", 1))
        matches = int(payload.get("matches", DEFAULT_BATCH_MATCHES))
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    matches = max(1, min(matches, MAX_BATCH_MATCHES))
    config = get_game_config()
    key = _result_key("batch", config, blue, red, matches, seed)
    result = cache.get(key)
    if result is not None:
        return JsonResponse(result)


    if not _BATCH_SLOT.acquire(blocking=False):
        return JsonResponse({"error": BATCH_BUSY_MESSAGE}, status=429)
    try:
        result = batch_matches(blue, red, matches=matches, seed=seed, config=config)
    finally:
        _BATCH_SLOT.release()

    cache.set(key, result)
    return JsonResponse(result)


@api_login_required
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


@api_login_required
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


@api_login_required
@require_http_methods(["GET", "POST"])
def api_game_active(request):
    """Superuser-only: read (GET) or set (POST) whether the game is open.

    Kept separate from api_game_config, which is about numeric tuning and runs
    every value through save_overrides().
    """
    if not request.user.is_superuser:
        return _forbidden()

    if request.method == "GET":
        return JsonResponse({"active": is_game_enabled()})

    try:
        payload = _json_body(request)
    except StrategyValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if "active" not in payload:
        return JsonResponse({"error": "مقدار active ارسال نشده است."}, status=400)

    active = set_game_enabled(bool(payload["active"]), user=request.user)
    logger.info("game-active set to %s by %s", active, request.user.username)
    return JsonResponse({
        "active": active,
        "message": "بازی فعال شد." if active else "بازی غیرفعال شد.",
    })


@api_login_required
@require_http_methods(["GET", "POST"])
def api_session_limit(request):
    """Superuser-only: read (GET) or set (POST) the concurrent-session ceiling.

    Separate from api_game_config for the same reason as api_game_active: that
    endpoint runs every value through save_overrides(), which only understands
    the engine's bounded physics floats.
    """
    if not request.user.is_superuser:
        return _forbidden()

    if request.method == "GET":
        return JsonResponse({
            "limit": get_session_limit(),
            "min": MIN_SESSION_LIMIT,
            "max": MAX_SESSION_LIMIT,
        })

    try:
        payload = _json_body(request)
    except StrategyValidationError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if "limit" not in payload:
        return JsonResponse({"error": "مقدار limit ارسال نشده است."}, status=400)

    limit = set_session_limit(payload["limit"], user=request.user)
    logger.info("session-limit set to %s by %s", limit, request.user.username)
    return JsonResponse({
        "limit": limit,
        "min": MIN_SESSION_LIMIT,
        "max": MAX_SESSION_LIMIT,
        "message": f"حداکثر نشست همزمان روی {limit} تنظیم شد.",
    })


@api_login_required
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


@api_login_required
@require_POST
def api_compile_strategy(request):
    try:
        payload = _json_body(request)
        text = payload.get("text", "")
        attempt = int(payload.get("attempt", 1))
        conversation_history = payload.get("conversation_history") or []

        result = compile_persian_strategy(
            text,
            attempt=attempt,
            conversation_history=conversation_history,
        )
        # The model name and token counts are operational detail. They are worth
        # keeping for cost tracking but are not the student's business, and
        # anything returned here is readable from the browser's network tab, so
        # they get logged rather than serialised into the response.
        model = result.pop("model", None)
        usage = result.pop("usage", None)
        result.pop("attempt", None)  # Internal tracking, not for the client
        logger.info(
            "compile-strategy user=%s model=%s attempt=%s usage=%s",
            request.user.username,
            model,
            attempt,
            usage,
        )
        return JsonResponse(result)
    except (StrategyValidationError, ValueError, TypeError) as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=400)
    except LLMConfigurationError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=503)
    except LLMServiceError as exc:
        return JsonResponse({"valid": False, "error": str(exc)}, status=502)
