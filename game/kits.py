"""
Team kit colours.

Each user stores three kit colours (home / away / alternative) chosen from a
fixed 28-colour palette. At match time the client picks, out of the two teams'
available kits, the pair with the greatest colour difference so the two players
are always easy to tell apart. Kits are persisted per user in the database.
"""
from __future__ import annotations

# 28 visually distinct kit colours (good mutual separation across the hue wheel
# plus a few neutrals). Order is stable — the UI shows them as a 28-swatch grid.
PALETTE = [
    "#E6194B", "#FF3838", "#F58231", "#FF8C00", "#FFB300", "#FFE119", "#BFEF45",
    "#3CB44B", "#00A651", "#14B37D", "#469990", "#17C0C0", "#42D4F4", "#2196F3",
    "#4363D8", "#0F52BA", "#000075", "#6A0DAD", "#911EB4", "#C04DE6", "#F032E6",
    "#FF6FA5", "#9A6324", "#8B4513", "#800000", "#808000", "#2F2F3A", "#FFFFFF",
]

# home, away, alternative
DEFAULT_KIT = ["#2196F3", "#E6194B", "#FFB300"]

_PALETTE_UPPER = {c.upper(): c for c in PALETTE}

# Kit colours must differ in hue (not merely be non-identical) so the three kits
# stay easy to tell apart. These thresholds mirror the client-side check.
_HUE_MIN = 32.0      # minimum hue separation (degrees) for chromatic colours
_NEUTRAL_S = 0.18    # saturation below this counts as a neutral / grey


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if not d:
        hue = 0.0
    elif mx == r:
        hue = ((g - b) / d) % 6
    elif mx == g:
        hue = (b - r) / d + 2
    else:
        hue = (r - g) / d + 4
    hue *= 60
    if hue < 0:
        hue += 360
    light = (mx + mn) / 2
    sat = d / (1 - abs(2 * light - 1)) if d else 0.0
    return hue, sat, light


def colors_too_close(a: str, b: str) -> bool:
    """True when two kit colours are visually confusable (same hue family)."""
    if a.upper() == b.upper():
        return True
    ha, sa, la = _hex_to_hsl(a)
    hb, sb, lb = _hex_to_hsl(b)
    neutral_a, neutral_b = sa < _NEUTRAL_S, sb < _NEUTRAL_S
    if neutral_a and neutral_b:
        return abs(la - lb) < 0.22
    if neutral_a != neutral_b:
        return False
    dh = abs(ha - hb)
    if dh > 180:
        dh = 360 - dh
    if dh >= _HUE_MIN:
        return False
    return abs(la - lb) < 0.28


def normalize_color(c: str | None) -> str | None:
    if not isinstance(c, str):
        return None
    return _PALETTE_UPPER.get(c.strip().upper())


def sanitize_kit(colors) -> list[str]:
    """Return exactly three *hue-distinct* valid palette colours (home/away/alt).

    Each slot must differ noticeably in hue from the other two so the three kits
    stay visually separable. Invalid, missing, or too-similar entries fall back
    to the first still-acceptable colour (preferring the slot's default), and
    positions are otherwise preserved so the user's choices stay put.
    """

    def acceptable(candidate: str, chosen: list[str]) -> bool:
        return not any(colors_too_close(candidate, c) for c in chosen)

    def first_acceptable(chosen: list[str], prefer: str) -> str:
        if acceptable(prefer, chosen):
            return prefer
        for c in PALETTE:
            if acceptable(c, chosen):
                return c
        return prefer  # 28 spread-out hues → always resolvable for 3 slots

    out: list[str] = []
    raw = list((colors or [])[:3])
    while len(raw) < 3:
        raw.append(None)
    for slot, c in enumerate(raw):
        norm = normalize_color(c)
        if not norm or not acceptable(norm, out):
            norm = first_acceptable(out, DEFAULT_KIT[slot])
        out.append(norm)
    return out[:3]
