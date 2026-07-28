"""Resolve picker-backed automation action inputs."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


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
