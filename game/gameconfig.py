"""
Admin-editable game configuration.

The physics/game constants live in :class:`game.engine.GameConfig` (defaults +
env vars). This module layers *database* overrides on top of them so a superuser
can tune the game live from the in-app settings panel, and exposes the metadata
(Persian labels, groups, bounds) that drives that panel's form.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from .engine import GameConfig, get_base_config

# Fields stored as integers rather than floats.
INT_FIELDS = {"physics_fps", "record_fps", "physics_substeps", "match_rounds"}

# Coefficient-like fields are constrained to a small 0..2 range.
_COEFF_TOKENS = (
    "restitution", "bounce", "friction", "keep", "drag",
    "transfer", "impulse_scale",
)

# Fields that must stay strictly positive (a zero would break the sim/geometry).
_POSITIVE_REQUIRED = {
    "width", "height", "ground_y", "goal_depth", "goal_height", "ball_radius",
    "player_width", "player_height", "match_time", "physics_fps", "record_fps",
    "physics_substeps", "kick_reach", "head_radius",
}

# Persian labels. Any field without an entry falls back to its raw key.
LABELS: dict[str, str] = {
    # Geometry
    "width": "عرض زمین", "height": "ارتفاع تصویر", "ground_y": "خط زمین (Y)",
    "goal_depth": "عمق دروازه", "goal_height": "ارتفاع دروازه",
    "goal_post_radius": "شعاع تیرک",
    # Ball
    "ball_radius": "شعاع توپ", "gravity": "گرانش توپ", "ball_max_speed": "حداکثر سرعت توپ",
    "floor_bounce": "جهش از زمین", "floor_friction": "اصطکاک زمین",
    "horizontal_drag_per_60fps": "مقاومت هوا", "ball_wall_bounce": "جهش از دیوار",
    "ball_ceiling_bounce": "جهش از سقف", "ball_body_restitution": "کشسانی بدن",
    "ball_head_restitution": "کشسانی سر", "ball_contact_impulse_cap": "سقف ایمپالس تماس",
    "ball_sleep_speed": "سرعت توقف توپ", "body_ball_impulse_scale": "ضریب ایمپالس بدن",
    # Player
    "player_width": "عرض بازیکن", "player_height": "ارتفاع بازیکن",
    "player_speed": "سرعت دویدن", "player_jump_speed": "سرعت پرش",
    "player_gravity": "گرانش بازیکن", "player_acceleration": "شتاب دویدن",
    "player_deceleration": "شتاب ترمز", "player_air_acceleration": "کنترل در هوا",
    "player_air_deceleration": "کاهش سرعت هوایی", "jump_cooldown": "وقفه بین پرش‌ها",
    "head_radius": "شعاع سر", "head_center_y": "مرکز عمودی سر",
    "body_inset_x": "فرورفتگی بدنه", "body_top_offset": "شروع بدنه",
    "player_bump_restitution": "کشسانی برخورد بازیکنان",
    "player_bump_extra_separation": "جداسازی پس از برخورد",
    "player_contact_velocity_transfer": "انتقال سرعت تنه",
    "player_collision_inset": "باریک‌سازی برخورد بازیکن",
    # Kicks
    "kick_reach": "برد ضربه", "kick_low_x": "قدرت افقی شوت زمینی",
    "kick_low_y": "قدرت عمودی شوت زمینی", "kick_low_cooldown": "ریکاوری شوت زمینی",
    "kick_high_x": "قدرت افقی شوت هوایی", "kick_high_y": "قدرت عمودی شوت هوایی",
    "kick_high_cooldown": "ریکاوری شوت هوایی", "kick_clear_x": "قدرت افقی دفع",
    "kick_clear_y": "قدرت عمودی دفع", "kick_clear_cooldown": "ریکاوری دفع",
    "kick_keep_ball_velocity": "حفظ سرعت توپ در ضربه",
    "kick_player_velocity_transfer": "انتقال سرعت به شوت", "move_deadzone": "ناحیه مرده حرکت",
    # Anti-lock / contested
    "running_touch_lift": "پرتاب توپ هنگام دو", "contested_ball_pop_y": "پرتاب عمودی درگیری",
    "contested_ball_horizontal_keep": "حفظ افقی درگیری", "contested_player_recoil": "پس‌زنی درگیری",
    "contested_kick_pop_y": "پرتاب عمودی شوت همزمان", "contested_kick_horizontal_keep": "حفظ افقی شوت همزمان",
    "contested_kick_recoil": "پس‌زنی شوت همزمان", "contested_escape_x": "فرار افقی توپ",
    "stall_speed_threshold": "آستانه توقف توپ", "stall_pop_after": "زمان تا پرتاب ضد توقف",
    "stall_kickoff_after": "زمان تا شروع مجدد", "stall_pop_vx": "سرعت افقی ضد توقف",
    "stall_pop_vy": "سرعت عمودی ضد توقف",
    # Timing
    "match_time": "زمان هر راند", "match_rounds": "تعداد راندها",
    "rest_time": "زمان استراحت بین راندها", "kickoff_freeze": "مکث پس از گل",
    "physics_fps": "نرخ فریم فیزیک", "record_fps": "نرخ ضبط فریم",
    "physics_substeps": "زیرگام‌های فیزیک",
}

# Ordered (key, Persian title) groups. Field -> group is by prefix/membership.
GROUP_ORDER = [
    ("geometry", "ابعاد و هندسه زمین"),
    ("ball", "فیزیک توپ"),
    ("player", "بازیکن"),
    ("kick", "ضربات و شوت‌ها"),
    ("contested", "ضد قفل‌شدگی و درگیری"),
    ("timing", "زمان‌بندی مسابقه"),
]

_GEOMETRY = {"width", "height", "ground_y", "goal_depth", "goal_height", "goal_post_radius"}
_BALL = {"gravity", "floor_bounce", "floor_friction", "horizontal_drag_per_60fps",
         "body_ball_impulse_scale"}
_TIMING = {"match_time", "match_rounds", "rest_time", "kickoff_freeze",
           "physics_fps", "record_fps", "physics_substeps"}


def _group_of(key: str) -> str:
    if key in _GEOMETRY:
        return "geometry"
    if key in _TIMING:
        return "timing"
    if key.startswith("ball_") or key in _BALL:
        return "ball"
    if key.startswith("kick_") or key == "move_deadzone":
        return "kick"
    if key.startswith("contested_") or key.startswith("stall_") or key == "running_touch_lift":
        return "contested"
    if key.startswith("player_") or key in {"jump_cooldown", "head_radius", "head_center_y",
                                            "body_inset_x", "body_top_offset"}:
        return "player"
    return "player"


# Fields whose sensible range is not "0 .. 3x the default": (min, max, step).
_EXPLICIT_BOUNDS: dict[str, tuple[float, float, float]] = {
    # A match needs at least one round, and rounds are whole numbers.
    "match_rounds": (1.0, 10.0, 1.0),
    # 0 means "no break at all" -- the arena skips the rest screen entirely.
    "rest_time": (0.0, 120.0, 1.0),
}


def _bounds(key: str, default: float) -> tuple[float, float, float]:
    """Return (min, max, step) for an editable field."""
    if key in _EXPLICIT_BOUNDS:
        return _EXPLICIT_BOUNDS[key]
    if any(tok in key for tok in _COEFF_TOKENS):
        return (0.0, 2.0, 0.01)
    if default < 0:
        span = abs(default) * 2.5
        return (round(-span, 1), round(span, 1), 5.0)
    lo = 0.0
    if key in _POSITIVE_REQUIRED:
        lo = max(1.0, round(default * 0.3))
    hi = max(1.0, round(default * 3)) if default > 0 else 100.0
    if default <= 1:
        step = 0.01
    elif default < 10:
        step = 0.05
    else:
        step = 1.0
    if key in INT_FIELDS:
        # Whole-number fields must not offer fractional spinner steps.
        step = max(1.0, round(step))
    return (float(lo), float(hi), float(step))


def editable_keys() -> list[str]:
    return [f.name for f in dataclasses.fields(GameConfig)]


def _coerce(key: str, value: Any) -> float:
    num = float(value)
    lo, hi, _step = _bounds(key, getattr(GameConfig(), key))
    num = max(lo, min(hi, num))
    if key in INT_FIELDS:
        num = float(int(round(num)))
    return num


def spec(config: GameConfig | None = None) -> list[dict]:
    """Grouped field metadata + current values for the panel form."""
    if config is None:
        config = get_effective_config()
    defaults = GameConfig()
    by_group: dict[str, list[dict]] = {gid: [] for gid, _ in GROUP_ORDER}
    for f in dataclasses.fields(GameConfig):
        key = f.name
        default = getattr(defaults, key)
        lo, hi, step = _bounds(key, default)
        by_group[_group_of(key)].append({
            "key": key,
            "label": LABELS.get(key, key),
            "value": getattr(config, key),
            "default": default,
            "min": lo,
            "max": hi,
            "step": step,
            "int": key in INT_FIELDS,
        })
    return [
        {"id": gid, "title": title, "fields": by_group[gid]}
        for gid, title in GROUP_ORDER
        if by_group[gid]
    ]


def sanitize(raw: dict) -> dict:
    """Keep only valid editable keys, coerced & clamped."""
    valid = set(editable_keys())
    out: dict[str, float] = {}
    for key, value in (raw or {}).items():
        if key not in valid:
            continue
        try:
            out[key] = _coerce(key, value)
        except (TypeError, ValueError):
            continue
    return out


def load_overrides() -> dict:
    """DB overrides, sanitized. Empty on any error (e.g. table not migrated yet)."""
    try:
        from .models import GameConfigOverride
        obj = GameConfigOverride.objects.filter(singleton_id=1).first()
        return sanitize(obj.overrides) if obj else {}
    except Exception:
        return {}


def apply_overrides(config: GameConfig, overrides: dict) -> GameConfig:
    clean = sanitize(overrides)
    return dataclasses.replace(config, **clean) if clean else config


def get_effective_config() -> GameConfig:
    """Base (defaults+env) config with DB overrides applied."""
    return apply_overrides(get_base_config(), load_overrides())


def config_with_overrides(overrides: dict) -> GameConfig:
    """Base config with the given (unsaved) overrides — used for panel previews."""
    return apply_overrides(get_base_config(), overrides)


def save_overrides(raw: dict, user=None) -> dict:
    """Persist overrides (dropping any that equal the default). Returns the stored map."""
    from .models import GameConfigOverride
    clean = sanitize(raw)
    defaults = GameConfig()
    clean = {k: v for k, v in clean.items() if v != getattr(defaults, k)}
    obj = GameConfigOverride.load()
    obj.overrides = clean
    if user is not None and getattr(user, "is_authenticated", False):
        obj.updated_by = user
    obj.save()
    return clean


def reset_overrides(user=None) -> dict:
    return save_overrides({}, user=user)
