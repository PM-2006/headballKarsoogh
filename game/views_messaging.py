"""JSON endpoints for the in-app inbox.

Kept out of ``views.py`` because that module is already the game API and this
is a self-contained feature; the two share nothing but the auth decorator.

Every endpoint here needs a session. The ``messages/`` half additionally needs
an admin -- see ``messaging.is_messaging_admin``.
"""
from __future__ import annotations

import functools
import json
import logging

from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .messaging import (
    AlreadySentError,
    EmptyAudienceError,
    audience_count,
    audience_label,
    excerpt,
    is_messaging_admin,
    label_for,
    mark_read,
    send_message,
    unread_count,
)
from .models import Message, Notification
from .views import api_login_required

logger = logging.getLogger(__name__)

DEFAULT_INBOX_LIMIT = 60
MAX_INBOX_LIMIT = 200
MAX_AUDIENCE_USERS = 2000
TITLE_MAX_LENGTH = 120

FORBIDDEN_MESSAGE = "این بخش فقط برای مدیران است."
NOT_FOUND_MESSAGE = "پیام پیدا نشد."
SENT_IS_FINAL_MESSAGE = (
    "این پیام ارسال شده و دیگر قابل ویرایش یا حذف نیست؛ "
    "همین حالا در صندوق دیگران است."
)


class BadRequest(Exception):
    """A malformed payload. Turned into a 400 by the endpoint that caught it."""


def _json_body(request) -> dict:
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BadRequest("محتوای درخواست باید JSON معتبر باشد.") from exc
    if not isinstance(payload, dict):
        raise BadRequest("محتوای درخواست باید یک شیء JSON باشد.")
    return payload


def admin_required(view):
    """403 for anyone who is not an admin. Sits under ``api_login_required``."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_messaging_admin(request.user):
            return JsonResponse({"error": FORBIDDEN_MESSAGE}, status=403)
        return view(request, *args, **kwargs)

    return wrapper


def _not_found():
    return JsonResponse({"error": NOT_FOUND_MESSAGE}, status=404)


def _iso(value):
    return value.isoformat() if value else None


def _clamped_limit(request) -> int:
    try:
        limit = int(request.GET.get("limit", DEFAULT_INBOX_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_INBOX_LIMIT
    return max(1, min(limit, MAX_INBOX_LIMIT))


def _id_list(raw) -> list[int]:
    """Coerce a JSON array into a list of ints, skipping anything unusable."""
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise BadRequest("فهرست شناسه‌ها باید آرایه باشد.")
    ids = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


# ---------------------------------------------------------------- serialisers


def _notification_dict(notification: Notification) -> dict:
    message = notification.message
    return {
        "id": notification.id,
        "message_id": message.id,
        "title": message.title,
        # The whole body ships with the list. These are a few lines each, and
        # refetching one on every open feels broken on a slow connection.
        "body": message.body,
        "excerpt": excerpt(message.body),
        "sender": message.sender_label or "مدیر",
        "sent_at": _iso(message.sent_at),
        "is_read": notification.read_at is not None,
        "read_at": _iso(notification.read_at),
    }


def _message_dict(message: Message, *, viewer=None) -> dict:
    data = {
        "id": message.id,
        "title": message.title,
        "body": message.body,
        "excerpt": excerpt(message.body),
        "status": message.status,
        "to_everyone": message.to_everyone,
        "users": [user.pk for user in message.users.all()],
        "audience_label": audience_label(message),
        # The count travels separately from the label so the client can render
        # it in Persian digits like every other number in this UI.
        "audience_count": len(message.users.all()),
        "sender": message.sender_label or "مدیر",
        "is_mine": bool(viewer and message.sender_id == viewer.pk),
        "created_at": _iso(message.created_at),
        "updated_at": _iso(message.updated_at),
        "sent_at": _iso(message.sent_at),
    }
    if message.is_sent:
        delivered = getattr(message, "delivered_count", None)
        read = getattr(message, "read_count", None)
        if delivered is None:
            delivered = message.notifications.count()
            read = message.notifications.filter(read_at__isnull=False).count()
        data.update({"delivered": delivered, "read": read, "unread": delivered - read})
    return data


# ------------------------------------------------------------------ the inbox


@api_login_required
@require_GET
def api_notifications(request):
    """The caller's inbox and their unread count, in one response.

    Deliberately one endpoint rather than two: split them and the bell's badge
    can disagree with the list it opens, which reads as a bug every time.
    """
    owned = Notification.objects.filter(user=request.user)
    rows = owned.select_related("message").order_by("-id")[: _clamped_limit(request)]
    return JsonResponse(
        {
            "unread": unread_count(request.user),
            "total": owned.count(),
            "results": [_notification_dict(row) for row in rows],
        }
    )


@api_login_required
@require_GET
def api_notification_detail(request, pk: int):
    """One message in full. Reading it does **not** mark it read.

    A request that reports state must not change it; the client calls
    ``read/`` once it has actually rendered the message.
    """
    notification = (
        Notification.objects.select_related("message")
        .filter(pk=pk, user=request.user)
        .first()
    )
    if notification is None:
        return _not_found()
    return JsonResponse(
        {
            "notification": _notification_dict(notification),
            "unread": unread_count(request.user),
        }
    )


@api_login_required
@require_POST
def api_notifications_read(request):
    """Mark the given ids read. Idempotent; foreign or stale ids are ignored."""
    try:
        payload = _json_body(request)
        ids = _id_list(payload.get("ids"))
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    marked = mark_read(request.user, ids)
    return JsonResponse({"marked": marked, "unread": unread_count(request.user)})


@api_login_required
@require_POST
def api_notifications_read_all(request):
    marked = mark_read(request.user)
    return JsonResponse({"marked": marked, "unread": unread_count(request.user)})


# ------------------------------------------------------------ admin: messages


def _admin_queryset(user):
    """Drafts are private to their author; sent messages are open to all admins.

    Two admins editing one half-written announcement is a worse failure than
    not being able to see a colleague's draft.
    """
    return Message.objects.filter(
        Q(status=Message.Status.SENT) | Q(status=Message.Status.DRAFT, sender=user)
    )


def _with_counts(queryset):
    return queryset.annotate(
        delivered_count=Count("notifications", distinct=True),
        read_count=Count(
            "notifications",
            filter=Q(notifications__read_at__isnull=False),
            distinct=True,
        ),
    )


@api_login_required
@admin_required
@require_http_methods(["GET", "POST"])
def api_messages(request):
    if request.method == "GET":
        status = (request.GET.get("status") or Message.Status.SENT).strip()
        if status not in Message.Status.values:
            return JsonResponse(
                {"error": "وضعیت درخواست‌شده معتبر نیست (draft یا sent)."}, status=400
            )
        queryset = _admin_queryset(request.user).filter(status=status)
        if status == Message.Status.DRAFT:
            queryset = queryset.order_by("-updated_at")
        else:
            queryset = _with_counts(queryset).order_by("-sent_at", "-id")
        queryset = queryset.prefetch_related("users")[:MAX_INBOX_LIMIT]
        return JsonResponse(
            {
                "status": status,
                "results": [_message_dict(m, viewer=request.user) for m in queryset],
            }
        )

    try:
        payload = _json_body(request)
        title = str(payload.get("title") or "").strip()
        if not title:
            raise BadRequest("عنوان پیام نمی‌تواند خالی باشد.")
        if len(title) > TITLE_MAX_LENGTH:
            raise BadRequest(
                "عنوان پیام حداکثر %d کاراکتر است." % TITLE_MAX_LENGTH
            )
        body = str(payload.get("body") or "")
        to_everyone = bool(payload.get("to_everyone"))
        user_ids = _id_list(payload.get("users"))
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    should_send = bool(payload.get("send"))
    try:
        # Create and send share one transaction so a refused send leaves no
        # half-made draft behind; the composer still holds the text either way.
        with transaction.atomic():
            message = Message.objects.create(
                sender=request.user,
                sender_label=label_for(request.user),
                title=title,
                body=body,
                to_everyone=to_everyone,
            )
            if not to_everyone and user_ids:
                message.users.set(user_ids)
            delivered = send_message(message) if should_send else 0
    except EmptyAudienceError as exc:
        return JsonResponse({"error": str(exc)}, status=409)

    return JsonResponse(
        {
            "success": True,
            "message": "پیام ارسال شد." if should_send else "پیش‌نویس ذخیره شد.",
            "delivered": delivered,
            "result": _message_dict(message, viewer=request.user),
        },
        status=201,
    )


@api_login_required
@admin_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def api_message_detail(request, pk: int):
    message = (
        _admin_queryset(request.user).filter(pk=pk).prefetch_related("users").first()
    )
    if message is None:
        return _not_found()

    if request.method == "GET":
        return JsonResponse({"result": _message_dict(message, viewer=request.user)})

    # A sent message is already in other people's inboxes. Editing it would
    # rewrite what they were told, so it is final in both directions.
    if message.is_sent:
        return JsonResponse({"error": SENT_IS_FINAL_MESSAGE}, status=409)
    if message.sender_id != request.user.pk:
        return _not_found()

    if request.method == "DELETE":
        message.delete()
        return JsonResponse({"success": True, "message": "پیش‌نویس حذف شد."})

    try:
        payload = _json_body(request)
        fields = []
        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if not title:
                raise BadRequest("عنوان پیام نمی‌تواند خالی باشد.")
            if len(title) > TITLE_MAX_LENGTH:
                raise BadRequest("عنوان پیام حداکثر %d کاراکتر است." % TITLE_MAX_LENGTH)
            message.title = title
            fields.append("title")
        if "body" in payload:
            message.body = str(payload.get("body") or "")
            fields.append("body")
        if "to_everyone" in payload:
            message.to_everyone = bool(payload.get("to_everyone"))
            fields.append("to_everyone")
        user_ids = _id_list(payload.get("users")) if "users" in payload else None
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    if fields:
        message.save(update_fields=[*fields, "updated_at"])
    if user_ids is not None:
        message.users.set(user_ids)

    message.refresh_from_db()
    return JsonResponse(
        {
            "success": True,
            "message": "پیش‌نویس به‌روزرسانی شد.",
            "result": _message_dict(message, viewer=request.user),
        }
    )


@api_login_required
@admin_required
@require_POST
def api_message_send(request, pk: int):
    # Only the author can send a draft, because only the author can see it.
    message = Message.objects.filter(pk=pk, sender=request.user).first()
    if message is None:
        return _not_found()
    try:
        delivered = send_message(message)
    except (AlreadySentError, EmptyAudienceError) as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse(
        {
            "success": True,
            "message": "پیام برای %d نفر ارسال شد." % delivered,
            "delivered": delivered,
            "result": _message_dict(message, viewer=request.user),
        }
    )


@api_login_required
@admin_required
@require_GET
def api_message_recipients(request, pk: int):
    """Read receipts for one sent message -- unread recipients first."""
    message = (
        _admin_queryset(request.user).filter(pk=pk).prefetch_related("users").first()
    )
    if message is None:
        return _not_found()
    if not message.is_sent:
        return JsonResponse(
            {"error": "این پیام هنوز ارسال نشده و گیرنده‌ای ندارد."}, status=409
        )

    rows = (
        message.notifications.select_related("user")
        # nulls_first is spelled out because PostgreSQL and SQLite disagree on
        # where NULLs land by default: left implicit, dev and production would
        # order this list differently.
        .order_by(F("read_at").asc(nulls_first=True), "user__username")
    )
    recipients = [
        {
            "id": row.id,
            "user_id": row.user_id,
            "username": row.user.get_username(),
            "label": label_for(row.user),
            "is_read": row.read_at is not None,
            "read_at": _iso(row.read_at),
        }
        for row in rows
    ]
    read = sum(1 for row in recipients if row["is_read"])
    return JsonResponse(
        {
            "message": _message_dict(message, viewer=request.user),
            "delivered": len(recipients),
            "read": read,
            "unread": len(recipients) - read,
            "recipients": recipients,
        }
    )


@api_login_required
@admin_required
@require_GET
def api_message_audience(request):
    """The user list behind the composer's picker."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = (
        User.objects.filter(is_active=True)
        .exclude(pk=request.user.pk)
        .order_by("username")[:MAX_AUDIENCE_USERS]
    )
    return JsonResponse(
        {
            "users": [
                {
                    "id": user.pk,
                    "username": user.get_username(),
                    "label": label_for(user),
                    "is_admin": bool(user.is_staff or user.is_superuser),
                }
                for user in users
            ]
        }
    )


@api_login_required
@admin_required
@require_POST
def api_message_audience_preview(request):
    """How many people a selection would actually reach, sender excluded."""
    try:
        payload = _json_body(request)
        user_ids = _id_list(payload.get("users"))
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    to_everyone = bool(payload.get("to_everyone"))
    count = audience_count(
        to_everyone=to_everyone,
        user_ids=user_ids,
        exclude_user_id=request.user.pk,
    )
    if to_everyone:
        label = "همه — %d نفر" % count
    elif count:
        label = "%d نفر" % count
    else:
        label = "هیچ‌کس انتخاب نشده"
    return JsonResponse({"count": count, "to_everyone": to_everyone, "label": label})
