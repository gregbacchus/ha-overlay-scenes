"""Native Home Assistant config entry presentation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def overlay_set_title(name: str, set_id: str) -> str:
    """Return an Overlay Set title that exposes its service-facing ID."""
    return f"{name} · ID: {set_id}"


def layer_title(
    overlay_set_id: str,
    data: Mapping[str, Any],
    target_names: Mapping[str, str] | None = None,
) -> str:
    """Return a Layer title with its address and controlled channels."""
    configured_entities = data["entities"]
    entities = (
        [configured_entities]
        if isinstance(configured_entities, str)
        else configured_entities
    )
    targets = ", ".join(
        target_names.get(entity_id, entity_id) if target_names else entity_id
        for entity_id in entities
    )
    readable_layer_name = data["layer_id"].replace("_", " ").capitalize()
    attribute_name = data["attribute"].strip().replace("_", " ").capitalize()
    return (
        f"{readable_layer_name} · {overlay_set_id}.{data['layer_id']} · "
        f"{attribute_name} · {targets}"
    )


def display_name(
    entity_id: str, registry_name: str | None, state_name: str | None
) -> str:
    """Resolve a target's current user-facing name without using a sentinel."""
    if state_name is not None:
        return state_name
    if registry_name is not None:
        return registry_name
    object_id = entity_id.partition(".")[2]
    return object_id.replace("_", " ").capitalize()


def renamed_layer_targets(
    data: Mapping[str, Any], old_entity_id: str, new_entity_id: str
) -> dict[str, Any] | None:
    """Return updated layer data when a configured target changes address."""
    configured_entities = data["entities"]
    if isinstance(configured_entities, str):
        if configured_entities != old_entity_id:
            return None
        return dict(data) | {"entities": new_entity_id}

    if old_entity_id not in configured_entities:
        return None
    entities = [
        new_entity_id if entity_id == old_entity_id else entity_id
        for entity_id in configured_entities
    ]
    return dict(data) | {"entities": entities}
