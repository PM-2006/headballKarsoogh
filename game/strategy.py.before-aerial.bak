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
#   * Every kick fires toward the enemy goal regardless of which way a player
#     faces, so winning the ball converts almost directly into goals. Chasing
#     the ball beats holding position -- presets that camp near their own goal
#     were the ones that used to lose every match, or draw 0-0 with each other.
#   * JUMP costs more than it gains: holding everything else constant, deleting
#     a bot's jump rule was worth roughly 25 percentage points. A loose jump
#     gate is therefore a handicap, not a style, which is why only "aggressive"
#     jumps here and only for a ball right on its head.
# KICK_CLEAR hits hardest but lofts the ball, handing possession back; the
# defensive presets use it only inside their own danger zone for that reason.
PRESETS = {
    # Straight-ahead pressure: runs at the ball, lobs once it is upfield, and is
    # the only preset that leaves the ground. Weakest of the six on purpose.
    "aggressive": {
        "label": "Aggressive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 70)], "JUMP"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    # Reads the bounce and gets to the landing spot first, then drives the ball
    # flat. No wasted motion -- and no jumping.
    "predictive": {
        "label": "Predictive",
        "rules": [
            rule(1, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(2, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(3, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    # Hammers the ball away only when it is genuinely near its own goal, and
    # plays flat everywhere else. Contests every ball rather than sitting back.
    "defensive": {
        "label": "Defensive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 500)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    # Boots the ball out of its own half, then launches it long from the other
    # side, chasing the landing spot the whole way.
    "counter": {
        "label": "Counter Attack",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_own_half", "==", True)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    # Plays it straight for most of the match, then chases the scoreline in the
    # last ten seconds: sit on a lead, or throw everything forward when behind.
    "adaptive": {
        "label": "Adaptive",
        "rules": [
            rule(1, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(2, [condition("remaining_time", "<", 10), condition("score_difference", ">", 0), condition("ball_in_enemy_half", "==", True)], "MOVE_TO_GOAL"),
            rule(3, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(4, [condition("remaining_time", "<", 10), condition("score_difference", "<", 0), condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "MOVE_TO_BALL",
    },
    # Clears anything that reaches its danger zone, launches it long from
    # elsewhere, and drops onto its line once the ball is parked deep upfield.
    "goalie": {
        "label": "Goal Keeper",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_distance_to_own_goal", "<", 600)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True)], "KICK_HIGH"),
            rule(3, [condition("opponent_distance_to_ball", "<", "distance_to_ball", "sensor"), condition("ball_in_enemy_half", "==", True), condition("ball_distance_to_own_goal", ">", 1100)], "MOVE_TO_GOAL"),
            rule(4, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(5, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
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
    return {
        "sensors": SENSORS,
        "operators": list(OPERATORS),
        "actions": list(ACTIONS),
        "presets": {key: value["label"] for key, value in PRESETS.items()},
        "config": get_game_config().to_dict(),
    }
