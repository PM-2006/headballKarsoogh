from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver

from .models import UserSession


@receiver(user_logged_in)
def enforce_single_session(sender, user, request, **kwargs) -> None:
    if request is None:
        return

    if not request.session.session_key:
        request.session.save()
    current_key = request.session.session_key

    Session.objects.filter(usersession__user=user).exclude(session_key=current_key).delete()

    UserSession.objects.update_or_create(user=user, defaults={"session_id": current_key})
