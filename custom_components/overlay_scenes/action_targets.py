"""Resolve picker-backed action inputs without changing legacy identifiers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def exactly_one_reference(
    picker_value: str | None,
    legacy_value: str | None,
    picker_name: str,
    legacy_name: str,
) -> tuple[str, bool]:
    """Return one supplied reference and whether it came from the picker."""
    if (picker_value is None) == (legacy_value is None):
        raise ValueError(f"Select exactly one {picker_name} or provide one {legacy_name}")
    if picker_value is not None:
        return picker_value, True
    if legacy_value is None:
        raise ValueError(f"No {legacy_name} was provided")
    return legacy_value, False


def layer_reference_from_entity(
    get_state: Callable[[str], Any | None], entity_id: str
) -> str:
    """Resolve a layer status entity to its public qualified layer ID."""
    state = get_state(entity_id)
    attributes: Mapping[str, Any] = state.attributes if state is not None else {}
    reference = attributes.get("layer_id")
    if not isinstance(reference, str) or not reference:
        raise ValueError("Selected entity is not an Overlay Scenes layer status")
    return reference
