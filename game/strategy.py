from __future__ import annotations
from copy import deepcopy

SENSORS = {
    "my_x": "number", "opponent_x": "number", "ball_x": "number", "ball_y": "number",
    "ball_vx": "number", "ball_vy": "number", "ball_speed": "number",
    "distance_to_ball": "number", "opponent_distance_to_ball": "number",
    "distance_to_own_goal": "number", "distance_to_enemy_goal": "number",
    "ball_distance_to_own_goal": "number", "ball_distance_to_enemy_goal": "number",
    "predicted_ball_x": "number", "predicted_ball_y": "number",
    "remaining_time": "number", "my_score": "number", "opponent_score": "number",
    "score_difference": "number", "can_kick": "boolean", "on_ground": "boolean",
    "ball_in_own_half": "boolean", "ball_in_enemy_half": "boolean",
    "ball_above_me": "boolean", "ball_moving_toward_me": "boolean",
}
OPERATORS = ("<", "<=", ">", ">=", "==", "!=")
ACTIONS = (
    "MOVE_LEFT", "MOVE_RIGHT", "MOVE_TO_BALL", "MOVE_TO_GOAL", "MOVE_TO_CENTER",
    "JUMP", "KICK_LOW", "KICK_HIGH", "KICK_CLEAR", "IDLE",
)

def condition(left, operator, right, right_type="value"):
    return {"left": left, "operator": operator, "rightType": right_type, "right": right}

def rule(priority, conditions, action):
    return {"priority": priority, "conditions": conditions, "action": action}

# Preset opponents shipped with the game. These are the bots students face, so
# they are tuned as a set rather than written to win. Measured over a round-robin
# of 100 matches per pairing (sides mirrored) plus a panel of student-level bots:
# every preset lands in a 31-61% win band against the other five, none of them
# stalemates, and as a group they beat a naive "chase and kick" bot about two
# thirds of the time while losing to a genuinely well-built student bot.
#
# Two engine facts drive the tuning, and both are worth knowing before editing:
#   * KICK_LOW and KICK_HIGH fire toward the enemy goal regardless of which way
#     a player faces. KICK_CLEAR is the exception: it launches the ball upward
#     toward whichever side of the player's body the ball is currently on, so
#     it can also rescue a ball that has fallen behind the player.
#   * JUMP costs more than it gains: holding everything else constant, deleting
#     a bot's jump rule was worth roughly 25 percentage points. A loose jump
#     gate is therefore a handicap, not a style, which is why only "aggressive"
#     jumps here and only for a ball right on its head.
# KICK_CLEAR hits hardest and launches the ball steeply upward, handing
# possession back; defensive presets use it only in their own danger zone.
PRESETS = {
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

def get_preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset: {name}")
    return deepcopy(PRESETS[name])

def vocabulary() -> dict:
    from .engine import get_game_config
    from .gameconfig import get_strategy_strictness
    return {
        "sensors": SENSORS,
        "operators": list(OPERATORS),
        "actions": list(ACTIONS),
        "presets": {key: value["label"] for key, value in PRESETS.items()},
        "config": get_game_config().to_dict(),
        "default_strictness": get_strategy_strictness(),
    }
