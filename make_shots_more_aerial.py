from pathlib import Path
import sys

ENGINE = Path("game/engine.py")
STRATEGY = Path("game/strategy.py")

for path in (ENGINE, STRATEGY):
    if not path.exists():
        print(f"ERROR: {path} not found. Run this script from the repository root.")
        sys.exit(1)

def normalize(raw: str):
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")

def write_preserving_newlines(path: Path, text: str, newline: str):
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")

def apply_replacements(path: Path, replacements):
    raw = path.read_text(encoding="utf-8")
    text, newline = normalize(raw)
    original = text

    for old, new in replacements:
        if new in text:
            continue
        if old not in text:
            print(f"ERROR: Expected block not found in {path}:")
            print(old[:350])
            print("\nNo changes written to this file.")
            sys.exit(2)
        text = text.replace(old, new, 1)

    if text == original:
        print(f"Already updated: {path}")
        return

    backup = path.with_suffix(path.suffix + ".before-aerial.bak")
    if not backup.exists():
        backup.write_text(raw, encoding="utf-8")

    write_preserving_newlines(path, text, newline)
    print(f"Updated: {path}")
    print(f"Backup:  {backup}")

engine_replacements = [
    ("kick_low_y: float = -170.0", "kick_low_y: float = -280.0"),
    ("kick_high_y: float = -620.0", "kick_high_y: float = -760.0"),
    ("kick_clear_y: float = -360.0", "kick_clear_y: float = -520.0"),
    ('kick_low_y=_env_float("GAME_KICK_LOW_Y", -170.0)',
     'kick_low_y=_env_float("GAME_KICK_LOW_Y", -280.0)'),
    ('kick_high_y=_env_float("GAME_KICK_HIGH_Y", -620.0)',
     'kick_high_y=_env_float("GAME_KICK_HIGH_Y", -760.0)'),
    ('kick_clear_y=_env_float("GAME_KICK_CLEAR_Y", -360.0)',
     'kick_clear_y=_env_float("GAME_KICK_CLEAR_Y", -520.0)'),
    (
'''    else:
        _, impulse_x, impulse_y = impulses[0]
        ball.vx = ball.vx * config.kick_keep_ball_velocity + impulse_x
        ball.vy = ball.vy * config.kick_keep_ball_velocity + impulse_y
''',
'''    else:
        _, impulse_x, impulse_y = impulses[0]
        ball.vx = ball.vx * config.kick_keep_ball_velocity + impulse_x

        # Preserve existing UPWARD motion, but do not let a falling ball cancel
        # the intended lift of a kick. This gives KICK_HIGH / KICK_CLEAR a
        # consistent arcade arc even when the player strikes a descending ball.
        upward_carry = min(ball.vy, 0.0) * config.kick_keep_ball_velocity
        ball.vy = upward_carry + impulse_y
'''
    ),
]

strategy_replacements = [
    (
'''    "predictive": {
        "label": "Predictive",
        "rules": [
            rule(1, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(2, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(3, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
''',
'''    "predictive": {
        "label": "Predictive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
'''
    ),
    (
'''    "defensive": {
        "label": "Defensive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 500)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
''',
'''    "defensive": {
        "label": "Defensive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 500)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(4, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(5, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
'''
    ),
    (
'''    "adaptive": {
        "label": "Adaptive",
        "rules": [
            rule(1, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(2, [condition("remaining_time", "<", 10), condition("score_difference", ">", 0), condition("ball_in_enemy_half", "==", True)], "MOVE_TO_GOAL"),
            rule(3, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
''',
'''    "adaptive": {
        "label": "Adaptive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("remaining_time", "<", 10), condition("score_difference", ">", 0), condition("ball_in_enemy_half", "==", True)], "MOVE_TO_GOAL"),
            rule(4, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(5, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
'''
    ),
]

apply_replacements(ENGINE, engine_replacements)
apply_replacements(STRATEGY, strategy_replacements)

print()
print("OK: aerial-shot tuning applied.")
print("New vertical kick values:")
print("  KICK_LOW   -280   (small visible lift)")
print("  KICK_HIGH  -760   (real high arc)")
print("  KICK_CLEAR -520   (lofted clearance)")
print("Also: falling-ball velocity no longer cancels upward kick lift.")
print("Preset bots now choose KICK_HIGH more often in the enemy half.")
