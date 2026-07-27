"""Pure helpers for picker-backed authoring flows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

SUPPORTED_ATTRIBUTES = {
    "light": {"state", "brightness", "rgb_color"},
    "switch": {"state"},
    "media_player": {"volume_level"},
}


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
