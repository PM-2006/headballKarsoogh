from pathlib import Path
import re
import sys

ENGINE = Path("game/engine.py")
STRATEGY = Path("game/strategy.py")
PROMPT = Path("game/prompts/strategy_compiler.py")

for path in (ENGINE, STRATEGY, PROMPT):
    if not path.exists():
        print(f"ERROR: {path} not found. Run this from the repository root.")
        sys.exit(1)

def read_normalized(path):
    raw = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline, raw

def write_preserving(path, text, newline, original_raw, suffix):
    backup = path.with_suffix(path.suffix + suffix)
    if not backup.exists():
        backup.write_text(original_raw, encoding="utf-8")
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")
    print(f"Updated: {path}")
    print(f"Backup:  {backup}")

# ---------------------------------------------------------------------------
# engine.py
# ---------------------------------------------------------------------------
text, nl, raw = read_normalized(ENGINE)

# Version marker: replace any current version string without depending on its old value.
text = re.sub(
    r'^PHYSICS_VERSION\s*=\s*"[^"]+"',
    'PHYSICS_VERSION = "v3.2-aerial-jump-kicks"',
    text,
    count=1,
    flags=re.MULTILINE,
)

# More visible lift. Support both the old GitHub values and a local copy that
# already received the previous aerial-shot tuning.
for old, new in [
    ("kick_low_y: float = -170.0", "kick_low_y: float = -280.0"),
    ("kick_high_y: float = -620.0", "kick_high_y: float = -760.0"),
    ("kick_clear_y: float = -360.0", "kick_clear_y: float = -520.0"),
    ('kick_low_y=_env_float("GAME_KICK_LOW_Y", -170.0)',
     'kick_low_y=_env_float("GAME_KICK_LOW_Y", -280.0)'),
    ('kick_high_y=_env_float("GAME_KICK_HIGH_Y", -620.0)',
     'kick_high_y=_env_float("GAME_KICK_HIGH_Y", -760.0)'),
    ('kick_clear_y=_env_float("GAME_KICK_CLEAR_Y", -360.0)',
     'kick_clear_y=_env_float("GAME_KICK_CLEAR_Y", -520.0)'),
]:
    text = text.replace(old, new)

# A matched JUMP rule must not monopolize the strategy while the player is
# already airborne. Skip that physically impossible action and let the next
# matching rule (for example an air kick) execute.
old_choose = '''def _choose_action(strategy: dict, state: dict) -> tuple[int | str, str]:
    for item in sorted(strategy["rules"], key=lambda row: row["priority"]):
        if all(_condition_true(cond, state) for cond in item["conditions"]):
            return item["priority"], item["action"]
    return "default", strategy.get("default_action", "IDLE")
'''
new_choose = '''def _choose_action(strategy: dict, state: dict) -> tuple[int | str, str]:
    for item in sorted(strategy["rules"], key=lambda row: row["priority"]):
        if not all(_condition_true(cond, state) for cond in item["conditions"]):
            continue

        action = item["action"]

        # JUMP is a take-off command, not a persistent airborne state.
        # Once the player is already in the air, an otherwise-matching JUMP
        # rule is skipped so lower-priority rules can kick or steer.
        if action == "JUMP" and not state["on_ground"]:
            continue

        return item["priority"], action
    return "default", strategy.get("default_action", "IDLE")
'''
if new_choose not in text:
    if old_choose not in text:
        print("ERROR: Could not find _choose_action() in the expected form.")
        sys.exit(2)
    text = text.replace(old_choose, new_choose, 1)

# Do not let downward ball velocity cancel the intended upward kick impulse.
old_kick = '''    else:
        _, impulse_x, impulse_y = impulses[0]
        ball.vx = ball.vx * config.kick_keep_ball_velocity + impulse_x
        ball.vy = ball.vy * config.kick_keep_ball_velocity + impulse_y
'''
new_kick = '''    else:
        _, impulse_x, impulse_y = impulses[0]
        ball.vx = ball.vx * config.kick_keep_ball_velocity + impulse_x

        # Keep existing upward motion, but do not let a descending ball cancel
        # the lift requested by KICK_LOW / KICK_HIGH / KICK_CLEAR.
        upward_carry = min(ball.vy, 0.0) * config.kick_keep_ball_velocity
        ball.vy = upward_carry + impulse_y
'''
if new_kick not in text:
    if old_kick not in text:
        print("ERROR: Could not find the single-kick velocity block.")
        sys.exit(3)
    text = text.replace(old_kick, new_kick, 1)

write_preserving(ENGINE, text, nl, raw, ".before-air-actions.bak")

# ---------------------------------------------------------------------------
# strategy.py
# ---------------------------------------------------------------------------
text, nl, raw = read_normalized(STRATEGY)

new_presets = '''PRESETS = {
    "aggressive": {
        "label": "Aggressive",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 190)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(4, [condition("can_kick", "==", True)], "KICK_LOW"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    "predictive": {
        "label": "Predictive",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 180)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(4, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(5, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(6, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    "defensive": {
        "label": "Defensive",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 175)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 500)], "KICK_CLEAR"),
            rule(4, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(5, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(6, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(7, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    "counter": {
        "label": "Counter Attack",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 190)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_in_own_half", "==", True)], "KICK_CLEAR"),
            rule(4, [condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(5, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(6, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    "adaptive": {
        "label": "Adaptive",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 180)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(4, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(5, [condition("remaining_time", "<", 10), condition("score_difference", ">", 0), condition("ball_in_enemy_half", "==", True)], "MOVE_TO_GOAL"),
            rule(6, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(7, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    "goalie": {
        "label": "Goal Keeper",
        "rules": [
            rule(1, [condition("on_ground", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 185)], "JUMP"),
            rule(2, [condition("on_ground", "==", False), condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 600)], "KICK_CLEAR"),
            rule(4, [condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(5, [condition("opponent_distance_to_ball", "<", "distance_to_ball", "sensor"), condition("ball_in_enemy_half", "==", True), condition("ball_distance_to_own_goal", ">", 1100)], "MOVE_TO_GOAL"),
            rule(6, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(7, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
}
'''

pattern = r'PRESETS = \{.*?\n\}\n(?=\ndef get_preset)'
match = re.search(pattern, text, flags=re.DOTALL)
if not match:
    print("ERROR: Could not locate PRESETS block in game/strategy.py")
    sys.exit(4)
text = text[:match.start()] + new_presets + text[match.end():]

write_preserving(STRATEGY, text, nl, raw, ".before-air-actions.bak")

# ---------------------------------------------------------------------------
# strategy compiler prompt
# ---------------------------------------------------------------------------
text, nl, raw = read_normalized(PROMPT)

anchor = '- «توپ به سمت من می‌آید» -> ball_moving_toward_me == true'
addition = '''- «روی زمین هستم» -> on_ground == true
- «در هوا هستم / در حال پرش هستم» -> on_ground == false

JUMP + AIRBORNE KICK MAPPING
- JUMP is a take-off action. The player can kick while airborne; can_kick works both on the ground and in the air.
- If the student explicitly says to jump and then shoot while airborne, represent it as ordered rules:
  1) the stated jump condition + on_ground == true -> JUMP
  2) on_ground == false + can_kick == true -> the explicitly requested kick type
- Do not invent the kick type. If the student only says «شوت» without high/low/clear, still ask for clarification.
'''
if "JUMP + AIRBORNE KICK MAPPING" not in text:
    if anchor not in text:
        print("ERROR: Could not find semantic-mapping anchor in compiler prompt.")
        sys.exit(5)
    text = text.replace(anchor, anchor + "\n" + addition, 1)

write_preserving(PROMPT, text, nl, raw, ".before-air-actions.bak")

print()
print("OK: jump + airborne shooting update applied.")
print("Behavior now:")
print("  - JUMP rules only take off from the ground.")
print("  - Once airborne, matching lower-priority KICK rules can run.")
print("  - Airborne kicking uses the same KICK_LOW / KICK_HIGH / KICK_CLEAR actions.")
print("  - Built-in bots jump at reachable high balls.")
print("  - Built-in bots prefer KICK_HIGH in the air and more often in attack.")
print("  - Vertical kick defaults are LOW=-280, HIGH=-760, CLEAR=-520.")
