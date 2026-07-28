"""Pure helpers for picker-backed authoring flows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .const import BOOLEAN_OPS, COLOR_OPS, NUMERIC_OPS

SUPPORTED_ATTRIBUTES = {
    "light": {"state", "brightness", "rgb_color"},
    "switch": {"state"},
    "media_player": {"volume_level"},
}

VALUE_HELP = {
    "state": "Enter true or false, or a template returning a boolean.",
    "brightness": "Enter a percentage from 0 to 100, or a template returning that number.",
    "rgb_color": "Enter an RGB list such as [255, 100, 20], or a template returning one.",
    "volume_level": "Enter a number from 0.0 to 1.0, or a template returning that number.",
}


def attribute_value_help(attribute: str) -> str:
    """Return concise value guidance for a controllable attribute."""
    try:
        return VALUE_HELP[attribute]
    except KeyError as error:
        raise ValueError(f"Unsupported Overlay Scenes attribute: {attribute}") from error


def operations_for_attribute(attribute: str) -> tuple[str, ...]:
    """Return only operations compatible with an attribute's value type."""
    if attribute == "state":
        return BOOLEAN_OPS
    if attribute == "rgb_color":
        return COLOR_OPS
    if attribute in {"brightness", "volume_level"}:
        return NUMERIC_OPS
    raise ValueError(f"Unsupported Overlay Scenes attribute: {attribute}")


def normalize_entity_ids(value: str | Iterable[str]) -> list[str]:
    """Normalize the single or multiple values returned by an entity selector."""
    return [value] if isinstance(value, str) else list(value)


def common_entity_attributes(
    get_state: Callable[[str], Any | None], entity_ids: str | Iterable[str]
) -> list[str]:
    """Return attributes currently shared by every selected entity."""
    common: set[str] | None = None
    for entity_id in normalize_entity_ids(entity_ids):
        state = get_state(entity_id)
        domain = entity_id.split(".", 1)[0]
        supported = SUPPORTED_ATTRIBUTES.get(domain, set())
        attributes = set(state.attributes) if state is not None else set()
        if "state" in supported:
            attributes.add("state")
        attributes &= supported
        common = attributes if common is None else common & attributes
    available = common or set()
    return (["state"] if "state" in available else []) + sorted(available - {"state"})
