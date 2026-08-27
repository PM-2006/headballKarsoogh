from __future__ import annotations

import json
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower
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
        help_text=_("نام نمایشی ربات (حداکثر ۱۲۰ کاراکتر) — باید در کل سامانه یکتا باشد."),
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
        constraints = [
            # Bot names identify a bot in the arena menus and the scoreboard,
            # so two bots may never share one -- not even across users, and not
            # by differing only in case or in surrounding spaces.
            models.UniqueConstraint(
                Lower("name"),
                name="uniq_saved_strategy_name_ci",
                violation_error_message=_(
                    "رباتی با این نام از قبل وجود دارد. یک نام دیگر انتخاب کن."
                ),
            ),
        ]

    def __str__(self) -> str:
        author = self.user.username if self.user else "ناشناس"
        badge = " [ادمین/عمومی]" if self.is_admin_strategy else ""
        return f"{self.name} ({author}){badge}"

    @property
    def is_admin_strategy(self) -> bool:
        """Returns True if created by staff/superuser or explicitly marked public."""
        if self.is_public:
            return True
        if self.user and (self.user.is_staff or self.user.is_superuser):
            return True
        return False

    def clean(self) -> None:
        super().clean()
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": _("نام ربات نمی‌تواند خالی باشد.")})
        if self.name_is_taken():
            raise ValidationError(
                {"name": _("رباتی با نام «%(name)s» از قبل وجود دارد. یک نام دیگر انتخاب کن.") % {"name": self.name}}
            )
        if not self.strategy_data:
            raise ValidationError({"strategy_data": _("داده‌های استراتژی نمی‌تواند خالی باشد.")})

        # Validate against game engine schema
        try:
            validate_strategy(self.strategy_data)
        except StrategyValidationError as exc:
            raise ValidationError({"strategy_data": f"ساختار استراتژی معتبر نیست: {exc}"}) from exc

    def name_is_taken(self) -> bool:
        """True if another saved bot (any user) already uses this name."""
        taken = SavedStrategy.objects.filter(name__iexact=(self.name or "").strip())
        if self.pk:
            taken = taken.exclude(pk=self.pk)
        return taken.exists()

    @classmethod
    def suggest_free_name(cls, name: str) -> str:
        """`name`, or the first free `name (2)`, `name (3)`, ... variant."""
        base = (name or "").strip() or "ربات"
        candidate, index = base, 1
        while cls.objects.filter(name__iexact=candidate).exists():
            index += 1
            suffix = f" ({index})"
            candidate = base[: 120 - len(suffix)] + suffix
        return candidate

    def save(self, *args, **kwargs) -> None:
        # If user is admin/superuser, mark public by default if not set
        if self.user and (self.user.is_staff or self.user.is_superuser):
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "ai_prompt": self.ai_prompt,
            "strategy": self.strategy_data,
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
