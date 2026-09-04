"""JSON endpoints for the knockout brackets.

One resource per division (``?division=boys`` / ``?division=girls``), each with
its own draw, results, title and publish switch. Everyone signed in may read a
division (once published); admins edit it with small PATCHes -- a name, a
result, the size -- so two admins typing at once only ever step on the exact
field they both touched, never each other's whole draw.
"""
from __future__ import annotations

import json
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .bracket import (
    MAX_TITLE,
    BracketError,
    apply_result,
    apply_size,
    apply_team,
    normalize_teams,
    summary,
)
from .messaging import is_messaging_admin, label_for
from .models import KnockoutBracket
from .views import api_login_required

logger = logging.getLogger(__name__)

FORBIDDEN_MESSAGE = "فقط مدیران می‌توانند جدول را تغییر دهند."
UNKNOWN_DIVISION = "بخش جدول معتبر نیست."


def _division(request, payload=None) -> str:
    """Which bracket this request is about; the query string wins over the body."""
    value = request.GET.get("division")
    if not value and isinstance(payload, dict):
        value = payload.get("division")
    value = (value or KnockoutBracket.BOYS).strip().lower()
    if value not in KnockoutBracket.DIVISION_KEYS:
        raise BracketError(UNKNOWN_DIVISION)
    return value


def _bracket_dict(bracket: KnockoutBracket, user) -> dict:
    can_edit = is_messaging_admin(user)
    data = {
        "division": bracket.division,
        "division_label": bracket.get_division_display(),
        "published": bracket.published,
        "can_edit": can_edit,
        "title": bracket.title,
        "size": bracket.size,
        "teams": normalize_teams(bracket.teams, bracket.size),
        "results": bracket.results or {},
        "updated_at": bracket.updated_at.isoformat() if bracket.updated_at else None,
        "updated_by": label_for(bracket.updated_by) if bracket.updated_by else "",
    }
    data.update(summary(bracket))
    if can_edit:
        # Every account is a team in this game, so the draw is usually typed
        # from this list. Sent only to editors; viewers have no use for it.
        User = get_user_model()
        data["suggestions"] = list(
            User.objects.filter(is_active=True)
            .order_by("username")
            .values_list("username", flat=True)[:500]
        )
    return data


@api_login_required
@require_http_methods(["GET", "PATCH"])
def api_bracket(request):
    payload = None
    if request.method == "PATCH":
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            if not isinstance(payload, dict):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "محتوای درخواست باید یک شیء JSON باشد."}, status=400)

    try:
        division = _division(request, payload)
    except BracketError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    bracket = KnockoutBracket.load(division)
    can_edit = is_messaging_admin(request.user)

    if request.method == "GET":
        if not bracket.published and not can_edit:
            # Nothing to see yet -- and nothing leaks about the half-typed draw.
            return JsonResponse(
                {
                    "division": bracket.division,
                    "division_label": bracket.get_division_display(),
                    "published": False,
                    "can_edit": False,
                    "title": bracket.title,
                }
            )
        return JsonResponse(_bracket_dict(bracket, request.user))

    if not can_edit:
        return JsonResponse({"error": FORBIDDEN_MESSAGE}, status=403)

    size = bracket.size
    teams = normalize_teams(bracket.teams, size)
    results = dict(bracket.results or {})

    try:
        # Size first: it resets the draw, and anything else in the same
        # request is meant to apply to the new shape.
        if "size" in payload:
            new_size = apply_size(payload["size"])
            if new_size != size:
                size = new_size
                teams = normalize_teams(teams, size)
                results = {}
        if payload.get("reset_results"):
            results = {}
        if "title" in payload:
            title = " ".join(str(payload["title"] or "").split())[:MAX_TITLE]
            bracket.title = title or KnockoutBracket.DEFAULT_TITLES[division]
        if "published" in payload:
            bracket.published = bool(payload["published"])
        for index, name in (payload.get("teams") or {}).items():
            apply_team(size, teams, results, index, name)
        for key, entry in (payload.get("results") or {}).items():
            entry = entry if isinstance(entry, dict) else {}
            apply_result(size, teams, results, key, entry.get("winner"), entry.get("score"))
    except BracketError as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    bracket.size = size
    bracket.teams = teams
    bracket.results = results
    bracket.updated_by = request.user
    bracket.save()
    logger.info(
        "bracket (%s) updated by %s: %s", division, request.user.username, sorted(payload.keys())
    )
    return JsonResponse(_bracket_dict(bracket, request.user))
