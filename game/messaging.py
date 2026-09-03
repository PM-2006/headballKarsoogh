"""Audience resolution and delivery for the in-app inbox.

The rules that decide *who* receives a message live here rather than in the
views, because two callers must agree on them exactly: the real send, and the
"how many people will this reach?" preview the composer shows. If the preview
computed the audience its own way it would eventually disagree with the send,
and the number on screen would be a lie.
"""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import Message, Notification

logger = logging.getLogger(__name__)

EXCERPT_LENGTH = 140


class MessagingError(Exception):
    """Base for the refusals the API turns into a 409."""


class AlreadySentError(MessagingError):
    def __init__(self, message: str = "این پیام قبلاً ارسال شده است.") -> None:
        super().__init__(message)


class EmptyAudienceError(MessagingError):
    def __init__(
        self, message: str = "هیچ گیرنده‌ای انتخاب نشده است؛ پیام برای کسی ارسال نمی‌شود."
    ) -> None:
        super().__init__(message)


def is_messaging_admin(user) -> bool:
    """True for the accounts allowed to write and send messages.

    ``is_staff`` is the flag that marks an admin. ``is_superuser`` is accepted
    alongside it so a superuser whose staff flag was cleared by hand does not
    silently lose the composer -- the rest of this project treats the two the
    same way (see ``GameAccessMiddleware`` and the ``index`` view).
    """
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


def label_for(user) -> str:
    """The display name stamped onto a message at send time."""
    if not user:
        return ""
    full = (user.get_full_name() or "").strip()
    return (full or user.get_username())[:64]


def excerpt(body: str, limit: int = EXCERPT_LENGTH) -> str:
    """First ~``limit`` characters, whitespace collapsed, ellipsis if cut.

    Computed on the server so every client shows the same card text, and so a
    body full of newlines cannot stretch a two-line card open.
    """
    text = " ".join((body or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def resolve_audience(*, to_everyone: bool, user_ids=None, exclude_user_id=None):
    """The recipients implied by an audience selection.

    Built from explicit querysets rather than composed ``Q`` objects on
    purpose: an empty ``Q()`` matches *every* row, so a "nothing selected"
    branch written that way reads as harmless and quietly mails the whole site.
    Here "nothing selected" is its own early return that matches nobody.
    """
    User = get_user_model()
    active = User.objects.filter(is_active=True)

    if to_everyone:
        # "Everyone" wins outright; any named users are irrelevant.
        recipients = active
    elif user_ids:
        recipients = active.filter(pk__in=list(user_ids))
    else:
        return User.objects.none()

    if exclude_user_id:
        # A sent announcement belongs in the author's Sent box, not their bell.
        recipients = recipients.exclude(pk=exclude_user_id)
    return recipients


def recipients_for(message: Message):
    """The recipients of ``message`` as its audience currently stands."""
    user_ids = None
    if not message.to_everyone and message.pk:
        user_ids = list(message.users.values_list("pk", flat=True))
    return resolve_audience(
        to_everyone=message.to_everyone,
        user_ids=user_ids,
        exclude_user_id=message.sender_id,
    )


def audience_count(*, to_everyone: bool, user_ids=None, exclude_user_id=None) -> int:
    return resolve_audience(
        to_everyone=to_everyone,
        user_ids=user_ids,
        exclude_user_id=exclude_user_id,
    ).count()


def audience_label(message: Message) -> str:
    """Short Persian description of who a message was aimed at."""
    if message.to_everyone:
        return "همهٔ کاربران"
    count = message.users.count() if message.pk else 0
    if not count:
        return "بدون گیرنده"
    return f"{count} کاربر انتخاب‌شده"


@transaction.atomic
def send_message(message: Message) -> int:
    """Fan the message out: one ``Notification`` row per recipient. Returns the count.

    The audience is resolved **once**, here, and frozen as rows. Matching at
    read time instead would be cheaper to write and wrong in a way nobody
    notices for weeks: an account created after the announcement went out would
    suddenly find it in their inbox, having never been sent it.

    Raises ``AlreadySentError`` if it has already gone out, and
    ``EmptyAudienceError`` if it would reach nobody -- reporting success for a
    send that reached no one is the worst available outcome.
    """
    if message.is_sent:
        raise AlreadySentError()

    recipients = list(recipients_for(message))
    if not recipients:
        raise EmptyAudienceError()

    Notification.objects.bulk_create(
        [Notification(message=message, user=user) for user in recipients],
        # Belt and braces against a double submit: the unique constraint makes
        # a repeat delivery impossible, and this keeps it from raising.
        ignore_conflicts=True,
    )

    message.status = Message.Status.SENT
    message.sent_at = timezone.now()
    message.sender_label = label_for(message.sender) or message.sender_label
    message.save(update_fields=["status", "sent_at", "sender_label", "updated_at"])

    logger.info(
        "message %s sent by %s to %d recipient(s)",
        message.pk,
        message.sender_id,
        len(recipients),
    )
    return len(recipients)


def unread_count(user) -> int:
    """Backs the bell badge -- one indexed COUNT, not an audience match."""
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def mark_read(user, notification_ids=None) -> int:
    """Mark the user's notifications read. Returns how many actually changed.

    Idempotent, and ids that belong to somebody else (or no longer exist) are
    ignored rather than failing the whole batch: the client sends whatever it
    has on screen, and one stale id must not cost the user the other nine.
    """
    queryset = Notification.objects.filter(user=user, read_at__isnull=True)
    if notification_ids is not None:
        ids = [int(i) for i in notification_ids]
        if not ids:
            return 0
        queryset = queryset.filter(pk__in=ids)
    return queryset.update(read_at=timezone.now())
