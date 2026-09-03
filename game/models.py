from __future__ import annotations

import json
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from .validators import validate_strategy, StrategyValidationError


class SavedStrategy(models.Model):
    """
    Stores executable JSON football strategies created by users or admins.
    Admin-created or public strategies are visible to all users as official opponents.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_strategies",
        verbose_name=_("کاربر سازنده"),
    )
    name = models.CharField(
        max_length=120,
        verbose_name=_("نام استراتژی"),
        help_text=_("نام نمایشی ربات (حداکثر ۱۲۰ کاراکتر)"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("توضیحات"),
        help_text=_("توضیحات اختیاری درباره تاکتیک و شیوه بازی ربات"),
    )
    ai_prompt = models.TextField(
        blank=True,
        default="",
        verbose_name=_("متن پرامپت هوش مصنوعی"),
        help_text=_("متن فارسی استراتژی که برای ساخت این ربات به هوش مصنوعی داده شده است"),
    )
    strategy_data = models.JSONField(
        verbose_name=_("داده‌های JSON استراتژی"),
        help_text=_("ساختار معتبر JSON استراتژی شامل قوانین (rules) و عملکرد پیش‌فرض (default_action)"),
    )
    is_public = models.BooleanField(
        default=False,
        verbose_name=_("عمومی برای همه کاربران"),
        help_text=_("اگر فعال باشد، یا اگر توسط ادمین ساخته شده باشد، برای تمام کاربران به عنوان حریف قابل انتخاب خواهد بود."),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاریخ ایجاد"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("آخرین به‌روزرسانی"),
    )

    class Meta:
        verbose_name = _("استراتژی ذخیره‌شده")
        verbose_name_plural = _("استراتژی‌های ذخیره‌شده")
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        author = self.user.username if self.user else "ناشناس"
        badge = " [ادمین/عمومی]" if self.is_admin_strategy else ""
        return f"{self.name} ({author}){badge}"

    @property
    def is_admin_strategy(self) -> bool:
        if self.user and self.user.is_staff and not self.user.is_superuser:
            return False
        if self.is_public:
            return True
        if self.user and self.user.is_superuser:
            return True
        return False

    def clean(self) -> None:
        super().clean()
        if not self.strategy_data:
            raise ValidationError({"strategy_data": _("داده‌های استراتژی نمی‌تواند خالی باشد.")})

        # Validate against game engine schema
        try:
            validate_strategy(self.strategy_data)
        except StrategyValidationError as exc:
            raise ValidationError({"strategy_data": f"ساختار استراتژی معتبر نیست: {exc}"}) from exc

        # Max strategies limit per user (superusers exempt)
        if self.user_id and not (self.user and self.user.is_superuser):
            from .gameconfig import get_strategy_limit
            max_limit = get_strategy_limit()
            existing_count = SavedStrategy.objects.filter(user_id=self.user_id)
            if self.pk:
                existing_count = existing_count.exclude(pk=self.pk)
            if existing_count.count() >= max_limit:
                raise ValidationError(_(f"هر کاربر می‌تواند حداکثر {max_limit} استراتژی ذخیره کند."))

    def save(self, *args, **kwargs) -> None:
        # Superuser bots are official opponents. Staff bots stay private.
        if self.user and self.user.is_superuser:
            self.is_public = True

        # Ensure label inside strategy_data matches name if not explicitly set
        if isinstance(self.strategy_data, dict):
            if not self.strategy_data.get("label") or self.strategy_data.get("label") == "My Bot":
                self.strategy_data["label"] = self.name

        self.full_clean()
        super().save(*args, **kwargs)

    def _owner_kit(self) -> list[str]:
        from .kits import DEFAULT_KIT
        try:
            if self.user_id and hasattr(self.user, "kit"):
                return self.user.kit.colors()
        except Exception:
            pass
        return list(DEFAULT_KIT)

    def rules_count(self) -> int:
        data = self.strategy_data
        if isinstance(data, dict) and isinstance(data.get("rules"), list):
            return len(data["rules"])
        return 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "ai_prompt": self.ai_prompt,
            "strategy": self.strategy_data,
            "rules_count": self.rules_count(),
            "is_public": self.is_admin_strategy,
            "is_owner": True,  # adjusted in views based on request.user
            "author": self.user.username if self.user else "",
            "kit": self._owner_kit(),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M"),
        }


class GameConfigOverride(models.Model):
    """
    Singleton row holding admin overrides for the physics/game constants.
    Values here are layered on top of the env/code defaults by
    ``engine.get_game_config()``. Only superusers may edit it (via the in-app
    settings panel). ``overrides`` maps GameConfig field names -> numbers.
    """

    singleton_id = models.PositiveSmallIntegerField(
        default=1, unique=True, editable=False
    )
    overrides = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("مقادیر بازنویسی‌شده"),
        help_text=_("نگاشت نام فیلد تنظیمات بازی به مقدار عددی."),
    )
    # Not part of ``overrides``: that dict is sanitised into bounded floats
    # keyed by GameConfig field names, and this is neither.
    game_enabled = models.BooleanField(
        default=True,
        verbose_name=_("بازی فعال است"),
        help_text=_(
            "اگر غیرفعال شود، هیچ کاربری جز مدیران به بازی دسترسی نخواهد داشت."
        ),
    )
    # Also outside ``overrides``, for the same reason: it is a whole number of
    # sessions, not a bounded physics float.
    session_limit = models.PositiveSmallIntegerField(
        default=3,
        verbose_name=_("حداکثر نشست همزمان"),
        help_text=_(
            "تعداد نشست‌هایی که هر کاربر عادی می‌تواند همزمان باز داشته باشد. "
            "با ورود جدید، قدیمی‌ترین نشست‌های اضافه بسته می‌شوند. مدیران مستثنا هستند."
        ),
    )
    strategy_limit = models.PositiveSmallIntegerField(
        default=4,
        verbose_name=_("حداکثر استراتژی هر کاربر"),
        help_text=_(
            "حداکثر تعداد استراتژی‌های ذخیره‌شده مجاز برای هر کاربر عادی (از ۱ تا ۱۰)."
        ),
    )
    strategy_strictness = models.PositiveSmallIntegerField(
        default=2,
        verbose_name=_("سخت‌گیری پیش‌فرض استراتژی"),
        help_text=_(
            "سطح پیش‌فرض سخت‌گیری هوش مصنوعی در تبدیل متن به استراتژی (از ۱ تا ۵)."
        ),
    )
    show_strictness_to_user = models.BooleanField(
        default=True,
        verbose_name=_("امکان انتخاب سطح توسط کاربر"),
        help_text=_(
            "اگر فعال باشد، بخش انتخاب سطح سخت‌گیری برای دانش‌آموزان نمایش داده می‌شود؛ "
            "در غیر این صورت مخفی شده و سطح پیش‌فرض ادمین اجباری اعمال می‌شود."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("آخرین به‌روزرسانی"))
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("آخرین ویرایشگر"),
    )

    class Meta:
        verbose_name = _("تنظیمات بازی")
        verbose_name_plural = _("تنظیمات بازی")

    def __str__(self) -> str:
        return f"GameConfigOverride(#{self.pk}, {len(self.overrides or {})} overrides)"

    @classmethod
    def load(cls) -> "GameConfigOverride":
        obj, _created = cls.objects.get_or_create(singleton_id=1)
        return obj


class PlayerKit(models.Model):
    """A user's three team-kit colours (home / away / alternative)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kit",
        verbose_name=_("کاربر"),
    )
    home = models.CharField(max_length=9, default="#2196F3", verbose_name=_("رنگ اصلی (خانه)"))
    away = models.CharField(max_length=9, default="#E6194B", verbose_name=_("رنگ دوم (میهمان)"))
    alternative = models.CharField(max_length=9, default="#FFB300", verbose_name=_("رنگ جایگزین"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("رنگ تیم")
        verbose_name_plural = _("رنگ‌های تیم")

    def __str__(self) -> str:
        return f"{self.user.username}: {self.home}/{self.away}/{self.alternative}"

    def colors(self) -> list[str]:
        return [self.home, self.away, self.alternative]

    @classmethod
    def for_user(cls, user) -> "PlayerKit":
        obj, _created = cls.objects.get_or_create(user=user)
        return obj


class UserSession(models.Model):
    """Maps each login session to the user holding it.

    Ordinary users end up with at most ``GameConfigOverride.session_limit`` rows,
    because every login prunes their oldest sessions back down to that ceiling.
    Staff keep as many as they like: they are exempt from that prune, but are
    still tracked so that demoting someone leaves no session unreachable.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_sessions",
        verbose_name=_("کاربر"),
    )
    session = models.OneToOneField(
        Session,
        on_delete=models.CASCADE,
        verbose_name=_("نشست"),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("نشست فعال")
        verbose_name_plural = _("نشست‌های فعال")

    def __str__(self) -> str:
        return f"{self.user.username}: {self.session_id}"


class Message(models.Model):
    """What an admin wrote, and who it was aimed at.

    Deliberately separate from :class:`Notification`. A ``Message`` is the
    announcement itself; a ``Notification`` is one copy of it sitting in one
    person's inbox, and that is where read state lives. Collapsing the two
    would mean re-deriving the audience on every read, which is both slower
    and wrong -- see ``messaging.send_message`` for why.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("پیش‌نویس")
        SENT = "sent", _("ارسال‌شده")

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_messages",
        verbose_name=_("فرستنده"),
    )
    # Stamped when the message is written and refreshed at send time, so a
    # delivered announcement keeps the name it was signed with even if the
    # account is later renamed or deleted.
    sender_label = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name=_("نام نمایشی فرستنده"),
    )

    title = models.CharField(max_length=120, verbose_name=_("عنوان"))
    body = models.TextField(blank=True, default="", verbose_name=_("متن پیام"))

    # The audience. Everyone, or exactly the people named in ``users``.
    to_everyone = models.BooleanField(
        default=False,
        verbose_name=_("برای همه"),
        help_text=_("اگر فعال باشد، فهرست کاربران نادیده گرفته می‌شود."),
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="targeted_messages",
        verbose_name=_("گیرندگان مشخص"),
    )

    status = models.CharField(
        max_length=8,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_("وضعیت"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاریخ ایجاد"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("آخرین به‌روزرسانی"))
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name=_("تاریخ ارسال"))

    class Meta:
        verbose_name = _("پیام")
        verbose_name_plural = _("پیام‌ها")
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status", "-id"], name="msg_status_recent"),
        ]
        constraints = [
            # A draft has never been sent and a sent message always has a
            # timestamp. Enforced in the database because "sent" drives whether
            # the message may still be edited, and a row that disagrees with
            # itself would make that check unanswerable.
            models.CheckConstraint(
                condition=(
                    models.Q(status="draft", sent_at__isnull=True)
                    | models.Q(status="sent", sent_at__isnull=False)
                ),
                name="msg_sent_at_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.status}]"

    @property
    def is_sent(self) -> bool:
        return self.status == self.Status.SENT


class Notification(models.Model):
    """One message as delivered to one person. Read state lives here."""

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("پیام"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("گیرنده"),
    )
    read_at = models.DateTimeField(null=True, blank=True, verbose_name=_("زمان خواندن"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("تاریخ دریافت"))

    class Meta:
        verbose_name = _("اعلان")
        verbose_name_plural = _("اعلان‌ها")
        ordering = ["-id"]
        constraints = [
            # One delivery per person per message: re-sending must not double up.
            models.UniqueConstraint(
                fields=["message", "user"], name="uniq_notification_per_recipient"
            ),
        ]
        indexes = [
            # The inbox listing.
            models.Index(fields=["user", "-id"], name="notif_user_recent"),
            # The unread badge count, which is read on every page load.
            models.Index(
                fields=["user"],
                condition=models.Q(read_at__isnull=True),
                name="notif_user_unread",
            ),
        ]

    def __str__(self) -> str:
        state = "read" if self.read_at else "unread"
        return f"#{self.message_id} -> {self.user_id} ({state})"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
