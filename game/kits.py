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


def normalize_color(c: str | None) -> str | None:
    if not isinstance(c, str):
        return None
    return _PALETTE_UPPER.get(c.strip().upper())


def sanitize_kit(colors) -> list[str]:
    """Return exactly three valid palette colours (home/away/alternative).

    Invalid or missing entries fall back to the default for that slot, and the
    positions are preserved (no dedup) so the user's choices stay put.
    """
    out: list[str] = []
    for c in (colors or [])[:3]:
        norm = normalize_color(c)
        out.append(norm if norm else DEFAULT_KIT[len(out)])
    while len(out) < 3:
        out.append(DEFAULT_KIT[len(out)])
    return out[:3]
