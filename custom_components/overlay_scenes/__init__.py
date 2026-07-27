"""Overlay Scenes integration setup."""

from __future__ import annotations

import json
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import EventDeviceRegistryUpdatedData
from homeassistant.helpers.entity_registry import EventEntityRegistryUpdatedData
from homeassistant.helpers.event import (
    async_track_device_registry_updated_event,
    async_track_entity_registry_updated_event,
)

from .const import (
    DATA_RUNTIMES,
    DOMAIN,
    PLATFORMS,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_ACTIVATE_SET,
    SERVICE_DEACTIVATE_LAYER,
    SERVICE_DEACTIVATE_SET,
    SUBENTRY_TYPE_LAYER,
)
from .device_cleanup import remove_legacy_overlay_set_device
from .ha_presentation import layer_target_names
from .models import Channel, Layer, LifetimeSpec, parse_layer_reference
from .presentation import layer_title, overlay_set_title, renamed_layer_targets
from .runtime import OverlayRuntime

ACTIVATE_SCHEMA = vol.Schema(
    {vol.Required("layer_id"): cv.string, vol.Optional("duration_override"): cv.time_period}
)
DEACTIVATE_SCHEMA = vol.Schema({vol.Required("layer_id"): cv.string})
SET_ACTION_SCHEMA = vol.Schema({vol.Required("overlay_set_id"): cv.string})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration services once."""
    domain_data = hass.data.setdefault(DOMAIN, {DATA_RUNTIMES: {}})

    def find_layer(layer_reference: str) -> tuple[OverlayRuntime, str]:
        set_id, layer_id = parse_layer_reference(layer_reference)
        runtime = find_set_runtime(set_id)
        if layer_id not in runtime.layers:
            raise ValueError(f"Unknown Overlay Scenes layer: {layer_reference}")
        return runtime, layer_id

    def find_set_runtime(set_id: str) -> OverlayRuntime:
        matches = [
            runtime
            for runtime in domain_data[DATA_RUNTIMES].values()
            if runtime.set_id == set_id
        ]
        if not matches:
            raise ValueError(f"Unknown Overlay Set: {set_id}")
        if len(matches) > 1:
            raise ValueError(f"Overlay Set id is ambiguous: {set_id}")
        return matches[0]

    async def activate(call: ServiceCall) -> None:
        runtime, layer_id = find_layer(call.data["layer_id"])
        await runtime.async_activate(layer_id, call.data.get("duration_override"))

    async def deactivate(call: ServiceCall) -> None:
        runtime, layer_id = find_layer(call.data["layer_id"])
        await runtime.async_deactivate(layer_id)

    async def activate_set(call: ServiceCall) -> None:
        await find_set_runtime(call.data["overlay_set_id"]).async_activate_set()

    async def deactivate_set(call: ServiceCall) -> None:
        await find_set_runtime(call.data["overlay_set_id"]).async_deactivate_set()

    hass.services.async_register(DOMAIN, SERVICE_ACTIVATE_LAYER, activate, schema=ACTIVATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DEACTIVATE_LAYER, deactivate, schema=DEACTIVATE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_ACTIVATE_SET, activate_set, schema=SET_ACTION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DEACTIVATE_SET, deactivate_set, schema=SET_ACTION_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Overlay Set and all configured layer subentries."""
    fallback_set_id = re.sub(
        r"[^a-z0-9_]+", "_", entry.data.get("name", entry.title).lower()
    ).strip("_")
    set_id = entry.data.get("set_id", entry.unique_id or fallback_set_id or entry.entry_id)
    set_name = entry.data.get("name", entry.title)
    hass.config_entries.async_update_entry(
        entry, title=overlay_set_title(set_name, set_id)
    )
    layers: dict[str, Layer] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_LAYER:
            continue
        hass.config_entries.async_update_subentry(
            entry,
            subentry,
            title=layer_title(
                set_id, subentry.data, layer_target_names(hass, subentry.data)
            ),
        )
        layer = _layer_from_config(set_id, dict(subentry.data))
        if layer.id in layers:
            raise ValueError(
                f"Duplicate layer reference in Overlay Set: {layer.qualified_id}"
            )
        layers[layer.id] = layer
    runtime = OverlayRuntime(
        hass,
        entry.entry_id,
        layers,
        set_id=set_id,
    )
    hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id] = runtime
    await runtime.async_start()
    remove_legacy_overlay_set_device(dr.async_get(hass), DOMAIN, entry.entry_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _track_target_name_changes(hass, entry, layers)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an Overlay Set."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime: OverlayRuntime = hass.data[DOMAIN][DATA_RUNTIMES].pop(entry.entry_id)
    await runtime.async_stop()
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _track_target_name_changes(
    hass: HomeAssistant, entry: ConfigEntry, layers: dict[str, Layer]
) -> None:
    """Reload generated names and follow target entity-ID changes."""
    target_entity_ids = {
        channel.entity_id for layer in layers.values() for channel in layer.channels
    }
    if not target_entity_ids:
        return

    @callback
    def handle_entity_update(
        event: Event[EventEntityRegistryUpdatedData],
    ) -> None:
        if event.data["action"] != "update":
            return
        if old_entity_id := event.data.get("old_entity_id"):
            targets_updated = False
            for subentry in entry.subentries.values():
                if subentry.subentry_type != SUBENTRY_TYPE_LAYER:
                    continue
                updated_data = renamed_layer_targets(
                    subentry.data, old_entity_id, event.data["entity_id"]
                )
                if updated_data is None:
                    continue
                targets_updated = True
                hass.config_entries.async_update_subentry(
                    entry, subentry, data=updated_data
                )
            if targets_updated:
                return

        changes = event.data["changes"]
        if {"name", "original_name", "device_id"}.isdisjoint(changes):
            return
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        async_track_entity_registry_updated_event(
            hass, target_entity_ids, handle_entity_update
        )
    )

    entity_registry = er.async_get(hass)
    target_device_ids = {
        registry_entry.device_id
        for entity_id in target_entity_ids
        if (registry_entry := entity_registry.async_get(entity_id)) is not None
        and registry_entry.device_id is not None
    }
    if not target_device_ids:
        return

    @callback
    def handle_device_update(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] == "update":
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        async_track_device_registry_updated_event(
            hass, target_device_ids, handle_device_update
        )
    )


def _parse_value(value: Any) -> Any:
    if not isinstance(value, str) or "{{" in value or "{%" in value:
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _layer_from_config(overlay_set_id: str, data: dict[str, Any]) -> Layer:
    """Convert a layer config subentry into the internal model."""
    entities = data["entities"]
    if isinstance(entities, str):
        entities = [entities]
    attribute = data["attribute"].strip()
    if not attribute or "," in attribute:
        raise ValueError("A layer must target exactly one attribute")
    duration = data.get("duration_seconds")
    return Layer(
        id=data["layer_id"],
        overlay_set_id=overlay_set_id,
        role=data["role"],
        priority=int(data.get("priority", 0)),
        channels=[Channel(entity_id, attribute) for entity_id in entities],
        value=_parse_value(data["value"]),
        op=data.get("op", "override"),
        opacity=float(data.get("opacity", 1.0)),
        lifetime=LifetimeSpec(
            mode=data["lifetime_mode"],
            duration=cv.time_period(duration) if duration else None,
            condition_entity=data.get("condition_entity"),
        ),
        include_in_set_actions=data.get("include_in_set_actions", True),
    )
