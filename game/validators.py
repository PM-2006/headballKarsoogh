from __future__ import annotations
from .strategy import ACTIONS, OPERATORS, SENSORS

MAX_RULES = 15
MAX_CONDITIONS_PER_RULE = 8
MAX_ABS_NUMBER = 100_000

class StrategyValidationError(ValueError):
    pass

def _validate_condition(cond: dict) -> None:
    if not isinstance(cond, dict):
        raise StrategyValidationError("Each condition must be an object.")
    left = cond.get("left")
    operator = cond.get("operator")
    right_type = cond.get("rightType")
    right = cond.get("right")
    if left not in SENSORS:
        raise StrategyValidationError(f"Unknown sensor: {left}")
    if operator not in OPERATORS:
        raise StrategyValidationError(f"Invalid operator: {operator}")
    if right_type not in ("value", "sensor"):
        raise StrategyValidationError("rightType must be 'value' or 'sensor'.")
    left_type = SENSORS[left]
    if right_type == "sensor":
        if right not in SENSORS:
            raise StrategyValidationError(f"Unknown right-side sensor: {right}")
        if SENSORS[right] != left_type:
            raise StrategyValidationError(f"Cannot compare {left} with {right}: incompatible types.")
    else:
        if left_type == "boolean":
            if not isinstance(right, bool):
                raise StrategyValidationError(f"{left} expects a boolean value.")
            if operator not in ("==", "!="):
                raise StrategyValidationError(f"Boolean sensor {left} only supports == and !=.")
        else:
            if isinstance(right, bool) or not isinstance(right, (int, float)):
                raise StrategyValidationError(f"{left} expects a numeric value.")
            if abs(float(right)) > MAX_ABS_NUMBER:
                raise StrategyValidationError("Numeric condition value is out of range.")

def validate_strategy(strategy: dict) -> dict:
    if not isinstance(strategy, dict):
        raise StrategyValidationError("Strategy must be an object.")
    rules = strategy.get("rules")
    if not isinstance(rules, list):
        raise StrategyValidationError("Strategy rules must be a list.")
    if len(rules) > MAX_RULES:
        raise StrategyValidationError(f"Maximum {MAX_RULES} rules are allowed.")
    seen_priorities = set()
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            raise StrategyValidationError(f"Rule {index} must be an object.")
        priority = item.get("priority")
        if not isinstance(priority, int) or priority < 1:
            raise StrategyValidationError(f"Rule {index} has invalid priority.")
        if priority in seen_priorities:
            raise StrategyValidationError("Rule priorities must be unique.")
        seen_priorities.add(priority)
        conditions = item.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise StrategyValidationError(f"Rule {priority} needs at least one condition.")
        if len(conditions) > MAX_CONDITIONS_PER_RULE:
            raise StrategyValidationError(f"Rule {priority} has too many conditions.")
        for cond in conditions:
            _validate_condition(cond)
        action = item.get("action")
        if action not in ACTIONS:
            raise StrategyValidationError(f"Unknown action: {action}")
    default_action = strategy.get("default_action", "IDLE")
    if default_action not in ACTIONS:
        raise StrategyValidationError(f"Unknown default action: {default_action}")
    return strategy
