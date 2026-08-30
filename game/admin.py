from __future__ import annotations

import json
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import GameConfigOverride, SavedStrategy


@admin.register(GameConfigOverride)
class GameConfigOverrideAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "game_enabled",
        "session_limit",
        "strategy_strictness",
        "show_strictness_to_user",
        "updated_by",
        "updated_at",
    )
    readonly_fields = ("updated_at",)


@admin.register(SavedStrategy)
class SavedStrategyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user_display",
        "is_admin_badge",
        "rules_count",
        "updated_at",
        "created_at",
    )
    list_filter = (
        "is_public",
        "user__is_staff",
        "user__is_superuser",
        "created_at",
        "updated_at",
    )
    search_fields = (
        "name",
        "description",
        "ai_prompt",
        "user__username",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "formatted_json",
    )
    fieldsets = (
        (
            _("اطلاعات عمومی"),
            {
                "fields": ("name", "user", "is_public", "description"),
            },
        ),
        (
            _("داده‌های هوش مصنوعی و تاکتیک"),
            {
                "fields": ("ai_prompt", "strategy_data", "formatted_json"),
            },
        ),
        (
            _("زمان‌بندی"),
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("کاربر"))
    def user_display(self, obj: SavedStrategy) -> str:
        if not obj.user:
            return "—"
        role = " (مدیر)" if (obj.user.is_staff or obj.user.is_superuser) else ""
        return f"{obj.user.username}{role}"

    @admin.display(description=_("نوع استراتژی"), boolean=False)
    def is_admin_badge(self, obj: SavedStrategy) -> str:
        if obj.is_admin_strategy:
            return mark_safe(
                '<span style="background-color: #2e7d32; color: #fff; padding: 3px 8px; border-radius: 4px; font-weight: bold;">🏆 عمومی / رسمی</span>'
            )
        return mark_safe(
            '<span style="background-color: #1976d2; color: #fff; padding: 3px 8px; border-radius: 4px;">👤 ربات کاربر</span>'
        )

    @admin.display(description=_("تعداد قوانین"))
    def rules_count(self, obj: SavedStrategy) -> int:
        if isinstance(obj.strategy_data, dict) and "rules" in obj.strategy_data:
            return len(obj.strategy_data["rules"])
        return 0

    @admin.display(description=_("نمایش زیبا JSON"))
    def formatted_json(self, obj: SavedStrategy) -> str:
        if not obj.strategy_data:
            return "—"
        formatted = json.dumps(obj.strategy_data, indent=2, ensure_ascii=False)
        return format_html(
            '<pre style="background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 6px; font-family: monospace; max-height: 400px; overflow: auto; direction: ltr; text-align: left;">{}</pre>',
            formatted,
        )
