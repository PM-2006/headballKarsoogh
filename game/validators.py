from __future__ import annotations
from .strategy import ACTIONS, OPERATORS, SENSORS

MAX_RULES = 15
MAX_CONDITIONS_PER_RULE = 8
MAX_ABS_NUMBER = 100_000

class StrategyValidationError(ValueError):
    pass

def _validate_condition(cond: dict) -> None:
    if not isinstance(cond, dict):
        raise StrategyValidationError("هر شرط باید یک آبجکت باشد.")
    left = cond.get("left")
    operator = cond.get("operator")
    right_type = cond.get("rightType")
    right = cond.get("right")
    if left not in SENSORS:
        raise StrategyValidationError(f"سنسور ناشناخته: {left}")
    if operator not in OPERATORS:
        raise StrategyValidationError(f"عملگر نامعتبر: {operator}")
    if right_type not in ("value", "sensor"):
        raise StrategyValidationError("نوع سمت راست شرط باید value یا sensor باشد.")
    left_type = SENSORS[left]
    if right_type == "sensor":
        if right not in SENSORS:
            raise StrategyValidationError(f"سنسور سمت راست ناشناخته: {right}")
        if SENSORS[right] != left_type:
            raise StrategyValidationError(f"نمی‌توان {left} را با {right} مقایسه کرد: نوع‌ها سازگار نیستند.")
    else:
        if left_type == "boolean":
            if not isinstance(right, bool):
                raise StrategyValidationError(f"سنسور {left} یک مقدار بله/خیر می‌خواهد.")
            if operator not in ("==", "!="):
                raise StrategyValidationError(f"سنسور بله/خیری {left} فقط == و != را می‌پذیرد.")
        else:
            if isinstance(right, bool) or not isinstance(right, (int, float)):
                raise StrategyValidationError(f"سنسور {left} یک مقدار عددی می‌خواهد.")
            if abs(float(right)) > MAX_ABS_NUMBER:
                raise StrategyValidationError("مقدار عددی شرط خارج از محدوده مجاز است.")

def validate_strategy(strategy: dict) -> dict:
    if not isinstance(strategy, dict):
        raise StrategyValidationError("استراتژی باید یک آبجکت باشد.")
    rules = strategy.get("rules")
    if not isinstance(rules, list):
        raise StrategyValidationError("قوانین استراتژی باید یک لیست باشند.")
    if len(rules) > MAX_RULES:
        raise StrategyValidationError(f"حداکثر {MAX_RULES} قانون مجاز است.")
    seen_priorities = set()
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            raise StrategyValidationError(f"قانون {index} باید یک آبجکت باشد.")
        priority = item.get("priority")
        if not isinstance(priority, int) or priority < 1:
            raise StrategyValidationError(f"اولویت قانون {index} نامعتبر است.")
        if priority in seen_priorities:
            raise StrategyValidationError("اولویت قوانین باید یکتا باشد.")
        seen_priorities.add(priority)
        conditions = item.get("conditions")
        if not isinstance(conditions, list) or not conditions:
            raise StrategyValidationError(f"قانون {priority} حداقل به یک شرط نیاز دارد.")
        if len(conditions) > MAX_CONDITIONS_PER_RULE:
            raise StrategyValidationError(f"قانون {priority} شرط‌های بیش از حد دارد (حداکثر {MAX_CONDITIONS_PER_RULE}).")
        for cond in conditions:
            _validate_condition(cond)
        action = item.get("action")
        if action not in ACTIONS:
            raise StrategyValidationError(f"عمل ناشناخته: {action}")
    default_action = strategy.get("default_action", "IDLE")
    if default_action not in ACTIONS:
        raise StrategyValidationError(f"عمل پیش‌فرض ناشناخته: {default_action}")
    return strategy
