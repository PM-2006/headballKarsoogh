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

PRESETS = {
    "aggressive": {
        "label": "Aggressive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True)], "KICK_LOW"),
            rule(3, [condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 120)], "JUMP"),
            rule(4, [condition("ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(5, [condition("ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "IDLE",
    },
    "defensive": {
        "label": "Defensive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_own_half", "==", True)], "KICK_CLEAR"),
            rule(2, [condition("ball_in_own_half", "==", True), condition("opponent_distance_to_ball", "<", "distance_to_ball", "sensor")], "MOVE_TO_GOAL"),
            rule(3, [condition("ball_in_own_half", "==", True)], "MOVE_TO_BALL"),
            rule(4, [condition("distance_to_own_goal", ">", 240)], "MOVE_TO_GOAL"),
        ],
        "default_action": "IDLE",
    },
    "predictive": {
        "label": "Predictive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True)], "KICK_CLEAR"),
            rule(3, [condition("ball_moving_toward_me", "==", True), condition("ball_above_me", "==", True)], "JUMP"),
            rule(4, [condition("predicted_ball_x", "<", "my_x", "sensor")], "MOVE_LEFT"),
            rule(5, [condition("predicted_ball_x", ">=", "my_x", "sensor")], "MOVE_RIGHT"),
        ],
        "default_action": "IDLE",
    },
    "counter": {
        "label": "Counter Attack",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(2, [condition("can_kick", "==", True), condition("ball_in_own_half", "==", True)], "KICK_CLEAR"),
            rule(3, [condition("ball_in_own_half", "==", True), condition("opponent_distance_to_ball", "<", "distance_to_ball", "sensor")], "MOVE_TO_GOAL"),
            rule(4, [condition("ball_in_enemy_half", "==", True)], "MOVE_TO_CENTER"),
            rule(5, [condition("distance_to_ball", "<", "opponent_distance_to_ball", "sensor")], "MOVE_TO_BALL"),
        ],
        "default_action": "MOVE_TO_CENTER",
    },
    "adaptive": {
        "label": "Adaptive",
        "rules": [
            rule(1, [condition("can_kick", "==", True), condition("ball_in_own_half", "==", True)], "KICK_CLEAR"),
            rule(2, [condition("can_kick", "==", True), condition("ball_in_enemy_half", "==", True)], "KICK_HIGH"),
            rule(3, [condition("remaining_time", "<", 15), condition("score_difference", "<", 0)], "MOVE_TO_BALL"),
            rule(4, [condition("remaining_time", "<", 15), condition("score_difference", ">", 0)], "MOVE_TO_GOAL"),
            rule(5, [condition("distance_to_ball", "<", "opponent_distance_to_ball", "sensor")], "MOVE_TO_BALL"),
            rule(6, [condition("ball_in_own_half", "==", True)], "MOVE_TO_GOAL"),
        ],
        "default_action": "MOVE_TO_CENTER",
    },
    "goalie": {
        "label": "Goal Keeper",
        "rules": [
            rule(1, [condition("can_kick", "==", True)], "KICK_CLEAR"),
            rule(2, [condition("ball_in_own_half", "==", True), condition("ball_above_me", "==", True), condition("distance_to_ball", "<", 150)], "JUMP"),
            rule(3, [condition("ball_in_own_half", "==", True)], "MOVE_TO_BALL"),
            rule(4, [condition("distance_to_own_goal", ">", 130)], "MOVE_TO_GOAL"),
        ],
        "default_action": "IDLE",
    },
}

def get_preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"Unknown preset: {name}")
    return deepcopy(PRESETS[name])

def vocabulary() -> dict:
    return {
        "sensors": SENSORS,
        "operators": list(OPERATORS),
        "actions": list(ACTIONS),
        "presets": {key: value["label"] for key, value in PRESETS.items()},
    }
