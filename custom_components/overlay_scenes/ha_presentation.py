"""Home Assistant-backed presentation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .presentation import display_name


def target_display_name(hass: HomeAssistant, entity_id: str) -> str:
    """Return the current registry-aware display name for a target entity."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    registry_name: str | None = None
    if registry_entry is not None:
        if registry_entry.name is not None:
            registry_name = registry_entry.name
        elif registry_entry.original_name is not None:
            registry_name = registry_entry.original_name
    state = hass.states.get(entity_id)
    state_name = state.name if state is not None else None
    return display_name(entity_id, registry_name, state_name)


def layer_target_names(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> dict[str, str]:
    """Return current display names for every entity targeted by a layer."""
    configured_entities = data["entities"]
    entity_ids = (
        [configured_entities]
        if isinstance(configured_entities, str)
        else configured_entities
    )
    return {
        entity_id: target_display_name(hass, entity_id) for entity_id in entity_ids
    }
