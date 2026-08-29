from pathlib import Path
import re
import sys

ENGINE = Path("game/engine.py")
STRATEGY = Path("game/strategy.py")
PROMPT = Path("game/prompts/strategy_compiler.py")

for path in (ENGINE, STRATEGY, PROMPT):
    if not path.exists():
        print(f"ERROR: {path} not found. Run this script from the repository root.")
        sys.exit(1)


def read_file(path: Path):
    raw = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    return raw.replace("\r\n", "\n"), newline, raw


def write_file(path: Path, text: str, newline: str, raw: str):
    backup = path.with_suffix(path.suffix + ".before-jump-air-kicks.bak")
    if not backup.exists():
        backup.write_text(raw, encoding="utf-8")
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8", newline="")
    print(f"Updated: {path}")


# 1) ENGINE: current main already has the stronger aerial kick values and
# the falling-ball fix. We only change action selection so JUMP does not block
# lower-priority kick rules while the player is already airborne.
text, newline, raw = read_file(ENGINE)

required_engine_markers = [
    'kick_low_y: float = -280.0',
    'kick_high_y: float = -760.0',
    'kick_clear_y: float = -520.0',
    'upward_carry = min(ball.vy, 0.0) * config.kick_keep_ball_velocity',
]
missing = [marker for marker in required_engine_markers if marker not in text]
if missing:
    print("ERROR: engine.py does not match the current GitHub base expected by this script.")
    print("Missing markers:")
    for marker in missing:
        print("  -", marker)
    print("No files were changed.")
    sys.exit(2)

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

        # JUMP means "take off now". Once the player is already airborne,
        # skip JUMP and allow the next matching rule (for example a kick).
        if action == "JUMP" and not state["on_ground"]:
            continue

        return item["priority"], action

    return "default", strategy.get("default_action", "IDLE")
'''

if new_choose not in text:
    if old_choose not in text:
        print("ERROR: Could not find the current _choose_action() block in game/engine.py")
        print("No files were changed.")
        sys.exit(3)
    text = text.replace(old_choose, new_choose, 1)

text = re.sub(
    r'^PHYSICS_VERSION\s*=\s*"[^"]+"',
    'PHYSICS_VERSION = "v3.2-jump-air-kicks"',
    text,
    count=1,
    flags=re.MULTILINE,
)
write_file(ENGINE, text, newline, raw)


# 2) BUILT-IN PRESETS: all bots jump for reachable high balls, and once in
# the air they prefer a high shot if the ball is within kick range.
text, newline, raw = read_file(STRATEGY)

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

preset_pattern = r'PRESETS = \{.*?\n\}\n(?=\ndef get_preset)'
match = re.search(preset_pattern, text, flags=re.DOTALL)
if not match:
    print("ERROR: Could not find PRESETS block in game/strategy.py")
    sys.exit(4)
text = text[:match.start()] + new_presets + text[match.end():]
write_file(STRATEGY, text, newline, raw)


# 3) AI compiler prompt: teach it to compile "jump then shoot in the air"
# as two ordered rules using on_ground.
text, newline, raw = read_file(PROMPT)
if "JUMP + AIRBORNE KICK MAPPING" not in text:
    anchor = '- «توپ به سمت من می‌آید» -> ball_moving_toward_me == true'
    if anchor not in text:
        print("ERROR: Could not find the expected mapping anchor in strategy_compiler.py")
        sys.exit(5)
    addition = '''
- «روی زمین هستم» -> on_ground == true
- «در هوا هستم / در حال پرش هستم» -> on_ground == false

JUMP + AIRBORNE KICK MAPPING
- JUMP is a take-off action; the player is allowed to kick while airborne.
- can_kick is valid both on the ground and in the air.
- If the student explicitly asks to jump and then shoot while airborne, compile it as ordered rules:
  1) the student's jump condition + on_ground == true -> JUMP
  2) on_ground == false + can_kick == true -> the explicitly requested kick action
- KICK_LOW, KICK_HIGH, and KICK_CLEAR are all allowed while airborne.
- Do not invent a kick type. If the student only says «شوت» without high/low/clear, ask for clarification.
'''
    text = text.replace(anchor, anchor + addition, 1)
write_file(PROMPT, text, newline, raw)

print()
print("OK: jump + airborne shooting update applied from current GitHub main.")
print("Preserved current kick physics: LOW=-280, HIGH=-760, CLEAR=-520")
print("All built-in bots now jump at reachable high balls.")
print("While airborne, they prefer KICK_HIGH when can_kick is true.")
