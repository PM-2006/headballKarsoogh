"""Knockout bracket rules: who stands where, and what a corrected result undoes.

Everything here works on the plain ``(size, teams, results)`` triple stored on
``KnockoutBracket``. Later-round participants are *derived* by following
winners forward from the first-round draw, never stored -- so a result that is
changed after the fact cannot leave a stale name in a later match. The price
is the cascade in ``clear_downstream``: when a winner changes, every match that
winner had gone on to is voided, because its participants are no longer what
they were when it was decided.
"""
from __future__ import annotations

import re

from .models import KnockoutBracket

SIZES = KnockoutBracket.SIZES
MAX_TEAM_NAME = 40
MAX_TITLE = 80
MAX_SCORE = 99
THIRD = "third"

_KEY = re.compile(r"^(\d+)-(\d+)$")


class BracketError(Exception):
    """A change that would leave the bracket inconsistent. Becomes a 400."""


def rounds_for(size: int) -> int:
    """32 teams -> 5 rounds (R32, R16, QF, SF, final)."""
    return size.bit_length() - 1


def matches_in_round(size: int, r: int) -> int:
    return size >> (r + 1)


def normalize_teams(teams, size: int) -> list[str]:
    """Exactly ``size`` slots: whitespace-collapsed, length-capped, padded."""
    out = []
    for i in range(size):
        raw = teams[i] if isinstance(teams, list) and i < len(teams) else ""
        out.append(" ".join(str(raw or "").split())[:MAX_TEAM_NAME])
    return out


def parse_key(size: int, key: str) -> tuple[int, int] | str:
    """``"2-1"`` -> ``(2, 1)`` after bounds checks; ``"third"`` passes through."""
    if key == THIRD:
        if rounds_for(size) < 2:
            raise BracketError("با کمتر از چهار تیم بازی رده‌بندی وجود ندارد.")
        return THIRD
    match = _KEY.match(str(key))
    if not match:
        raise BracketError("شناسهٔ بازی معتبر نیست.")
    r, i = int(match.group(1)), int(match.group(2))
    if r >= rounds_for(size) or i >= matches_in_round(size, r):
        raise BracketError("این بازی در جدول وجود ندارد.")
    return r, i


# ------------------------------------------------------------- derivation


def participants(size: int, teams: list, results: dict, r: int, i: int):
    """The two names in match ``(r, i)``; ``None`` for a side not yet known."""
    if r == 0:
        a, b = teams[2 * i], teams[2 * i + 1]
        return (a or None, b or None)
    return (
        winner_name(size, teams, results, r - 1, 2 * i),
        winner_name(size, teams, results, r - 1, 2 * i + 1),
    )


def _decided_side(results: dict, key: str):
    entry = results.get(key)
    if not isinstance(entry, dict):
        return None
    winner = entry.get("winner")
    return winner if winner in (0, 1) else None


def winner_name(size, teams, results, r, i):
    side = _decided_side(results, f"{r}-{i}")
    if side is None:
        return None
    return participants(size, teams, results, r, i)[side]


def loser_name(size, teams, results, r, i):
    side = _decided_side(results, f"{r}-{i}")
    if side is None:
        return None
    return participants(size, teams, results, r, i)[1 - side]


def third_participants(size, teams, results):
    """The two semi-final losers, once both semis are decided."""
    rounds = rounds_for(size)
    if rounds < 2:
        return (None, None)
    semi = rounds - 2
    return (
        loser_name(size, teams, results, semi, 0),
        loser_name(size, teams, results, semi, 1),
    )


def champion(size, teams, results):
    return winner_name(size, teams, results, rounds_for(size) - 1, 0)


def third_place(size, teams, results):
    side = _decided_side(results, THIRD)
    if side is None:
        return None
    return third_participants(size, teams, results)[side]


# --------------------------------------------------------------- mutation


def clear_downstream(size: int, results: dict, r: int, i: int) -> None:
    """Void every match the winner of ``(r, i)`` would have gone on to.

    Walks the path to the final (``i // 2`` each round). A semi-final also
    feeds the third-place play-off, so that goes too when a semi changes.
    """
    rounds = rounds_for(size)
    rr, ii = r + 1, i // 2
    while rr < rounds:
        results.pop(f"{rr}-{ii}", None)
        rr, ii = rr + 1, ii // 2
    if r == rounds - 2:
        results.pop(THIRD, None)


def apply_team(size, teams, results, index, name) -> None:
    try:
        index = int(index)
    except (TypeError, ValueError) as exc:
        raise BracketError("شمارهٔ جایگاه تیم معتبر نیست.") from exc
    if not 0 <= index < size:
        raise BracketError("این جایگاه در جدول وجود ندارد.")
    clean = " ".join(str(name or "").split())[:MAX_TEAM_NAME]
    teams[index] = clean
    # A slot emptied out from under a decided first-round match voids it: its
    # recorded winner may now point at nobody.
    if not clean and f"0-{index // 2}" in results:
        results.pop(f"0-{index // 2}", None)
        clear_downstream(size, results, 0, index // 2)


def _clean_score(score):
    if score is None:
        return None
    if not isinstance(score, (list, tuple)) or len(score) != 2:
        raise BracketError("نتیجه باید دو عدد باشد.")
    out = []
    for value in score:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise BracketError("گل‌ها باید عدد صحیح باشند.") from exc
        if not 0 <= number <= MAX_SCORE:
            raise BracketError("تعداد گل‌ها باید بین ۰ تا ۹۹ باشد.")
        out.append(number)
    return out


def apply_result(size, teams, results, key, winner, score) -> None:
    """Record (or clear) one match. Refuses matches whose sides are unknown."""
    parsed = parse_key(size, key)
    if parsed == THIRD:
        sides = third_participants(size, teams, results)
    else:
        sides = participants(size, teams, results, *parsed)
    if None in sides:
        raise BracketError("هر دو تیم این بازی هنوز مشخص نشده‌اند.")

    if winner not in (0, 1, None):
        raise BracketError("برنده باید ۰، ۱ یا خالی باشد.")
    score = _clean_score(score)

    previous = _decided_side(results, key)
    if winner is None and score is None:
        results.pop(key, None)
    else:
        results[key] = {"winner": winner, "score": score}

    if previous != winner and parsed != THIRD:
        clear_downstream(size, results, *parsed)


def apply_size(size_value):
    """Validate a new size. The caller resets the draw to fit it."""
    try:
        size = int(size_value)
    except (TypeError, ValueError) as exc:
        raise BracketError("تعداد تیم‌ها معتبر نیست.") from exc
    if size not in SIZES:
        raise BracketError(
            "تعداد تیم‌ها باید یکی از این مقادیر باشد: "
            + "، ".join(str(n) for n in SIZES)
        )
    return size


def summary(bracket: KnockoutBracket) -> dict:
    """The derived facts a client cannot be trusted to compute for itself."""
    size, teams, results = bracket.size, normalize_teams(bracket.teams, bracket.size), bracket.results or {}
    third_sides = third_participants(size, teams, results)
    return {
        "champion": champion(size, teams, results),
        "third_place": third_place(size, teams, results),
        "third_participants": list(third_sides),
        "rounds": rounds_for(size),
    }
