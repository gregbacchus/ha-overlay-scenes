"""Pure compositing functions."""

from __future__ import annotations

from collections.abc import Callable
from numbers import Real
from typing import Any

from .models import Channel, Layer


def _lerp(old: float, new: float, opacity: float) -> float:
    return old + (new - old) * opacity


def _is_color(value: Any) -> bool:
    return isinstance(value, (tuple, list)) and len(value) == 3 and all(
        isinstance(item, Real) and not isinstance(item, bool) for item in value
    )


def apply_op(op: str, current: Any, value: Any, opacity: float = 1.0) -> Any:
    """Apply a modifier operation to a current value."""
    opacity = min(1.0, max(0.0, float(opacity)))
    if op == "override":
        if _is_color(current) and _is_color(value):
            return tuple(round(_lerp(a, b, opacity)) for a, b in zip(current, value, strict=True))
        if isinstance(current, Real) and isinstance(value, Real) and not (
            isinstance(current, bool) or isinstance(value, bool)
        ):
            result = _lerp(float(current), float(value), opacity)
            return int(result) if isinstance(current, int) and result.is_integer() else result
        return value if opacity > 0 else current

    if op in {"screen", "multiply"}:
        if not (_is_color(current) and _is_color(value)):
            raise TypeError(f"{op} requires two RGB colors")
        if op == "screen":
            return tuple(round(255 - (255 - a) * (255 - b) / 255) for a, b in zip(current, value, strict=True))
        return tuple(round(a * b / 255) for a, b in zip(current, value, strict=True))

    if op == "add":
        return current + value
    if op == "clamp_min":
        return max(current, value)
    if op == "clamp_max":
        return min(current, value)
    if op == "average":
        return (current + value) / 2

    left, right = bool(current), bool(value)
    boolean_ops: dict[str, Callable[[bool, bool], bool]] = {
        "or": lambda a, b: a or b,
        "and": lambda a, b: a and b,
        "nand": lambda a, b: not (a and b),
        "nor": lambda a, b: not (a or b),
        "xor": lambda a, b: a != b,
        "xnor": lambda a, b: a == b,
    }
    if op in boolean_ops:
        return boolean_ops[op](left, right)
    raise ValueError(f"Unsupported compositor operation: {op}")


def resolve_channel(
    base_value: Any,
    source: Layer | None,
    modifiers: list[Layer],
    channel: Channel | None = None,
    resolve_value: Callable[[Any], Any] | None = None,
) -> Any:
    """Resolve one channel from its base, source and ordered modifiers."""
    resolve = resolve_value or (lambda value: value)
    get_value = lambda layer: layer.value_for(channel) if channel is not None else layer.value
    result = resolve(get_value(source)) if source is not None else base_value
    if source is not None and result is False:
        return False
    for modifier in sorted(modifiers, key=lambda layer: layer.priority):
        if result is None:
            if modifier.op in {"or", "and", "nand", "nor", "xor", "xnor"}:
                result = False
            elif modifier.op in {"screen", "multiply"}:
                result = (0, 0, 0)
            else:
                result = 0
        result = apply_op(
            modifier.op,
            result,
            resolve(get_value(modifier)),
            modifier.opacity,
        )
    return result
