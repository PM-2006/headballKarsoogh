from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render

from .gameconfig import is_game_enabled


GAME_CLOSED_MESSAGE = (
    "بازی در حال حاضر توسط مدیر غیرفعال شده است. لطفاً بعداً دوباره سر بزن."
)

# Paths that stay open even with the game closed.
#
# Without the auth routes the admin who closed the game could not sign back in
# to reopen it, and without /healthz/ the container healthcheck would start
# failing the moment the game was switched off -- the switch would look like an
# outage. /admin/ is here so the singleton stays editable from Django admin as
# a fallback if the in-app toggle itself is ever broken.
ALWAYS_OPEN_PREFIXES = (
    "/accounts/",
    "/login/",
    "/logout/",
    "/admin/",
    "/healthz/",
    "/static/",
)


class GameAccessMiddleware:
    """Closes the whole site to non-admins while the game is deactivated.

    Implemented as middleware rather than a per-view decorator because the
    point of a kill switch is that nothing slips through: a decorator left off
    a future endpoint would be a hole in the lock, and there is no reminder to
    add one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._is_blocked(request):
            if request.path.startswith("/api/"):
                return JsonResponse({"error": GAME_CLOSED_MESSAGE}, status=403)
            return render(
                request,
                "game/closed.html",
                {"message": GAME_CLOSED_MESSAGE},
                status=403,
            )
        return self.get_response(request)

    def _is_blocked(self, request) -> bool:
        if request.path.startswith(ALWAYS_OPEN_PREFIXES):
            return False
        user = getattr(request, "user", None)
        # Staff and superusers keep full access: they need to reach the panel
        # to switch the game back on, and to test while it is closed.
        if user is not None and user.is_authenticated and (user.is_staff or user.is_superuser):
            return False
        return not is_game_enabled()
