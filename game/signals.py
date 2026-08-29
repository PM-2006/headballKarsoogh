from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .gameconfig import get_session_limit
from .models import UserSession


def _prune_old_sessions(user, current_key: str) -> None:
    """Close the user's oldest sessions until only ``session_limit`` remain.

    The fresh login always survives, so a student can never lock themselves out
    of the account they just signed into; it is the stalest browser that goes.
    """
    keepable = get_session_limit() - 1
    stale = list(
        UserSession.objects.filter(user=user)
        .exclude(session_id=current_key)
        .order_by("-updated_at")
        .values_list("session_id", flat=True)[keepable:]
    )
    if stale:
        # Deleting the Session cascades to its UserSession row.
        Session.objects.filter(session_key__in=stale).delete()


@receiver(user_logged_in)
def enforce_session_limit(sender, user, request, **kwargs) -> None:
    if request is None:
        return

    if not request.session.session_key:
        request.session.save()
    current_key = request.session.session_key

    if not (user.is_staff or user.is_superuser):
        _prune_old_sessions(user, current_key)

    UserSession.objects.update_or_create(session_id=current_key, defaults={"user": user})
