"""Overlay Scenes integration setup."""

from __future__ import annotations

from datetime import timedelta
import json
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_RUNTIMES,
    DOMAIN,
    PLATFORMS,
    SERVICE_ACTIVATE_LAYER,
    SERVICE_DEACTIVATE_LAYER,
    SUBENTRY_TYPE_LAYER,
)
from .models import Channel, Layer, LifetimeSpec
from .runtime import OverlayRuntime

ACTIVATE_SCHEMA = vol.Schema(
    {vol.Required("layer_id"): cv.string, vol.Optional("duration_override"): cv.time_period}
)
DEACTIVATE_SCHEMA = vol.Schema({vol.Required("layer_id"): cv.string})


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration services once."""
    domain_data = hass.data.setdefault(DOMAIN, {DATA_RUNTIMES: {}})

    def find_runtime(layer_id: str) -> OverlayRuntime:
        matches = [
            runtime
            for runtime in domain_data[DATA_RUNTIMES].values()
            if layer_id in runtime.layers
        ]
        if not matches:
            raise ValueError(f"Unknown Overlay Scenes layer: {layer_id}")
        if len(matches) > 1:
            raise ValueError(f"Layer id is ambiguous across Overlay Sets: {layer_id}")
        return matches[0]

    async def activate(call: ServiceCall) -> None:
        runtime = find_runtime(call.data["layer_id"])
        await runtime.async_activate(call.data["layer_id"], call.data.get("duration_override"))

    async def deactivate(call: ServiceCall) -> None:
        runtime = find_runtime(call.data["layer_id"])
        await runtime.async_deactivate(call.data["layer_id"])

    hass.services.async_register(DOMAIN, SERVICE_ACTIVATE_LAYER, activate, schema=ACTIVATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DEACTIVATE_LAYER, deactivate, schema=DEACTIVATE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an Overlay Set and all configured layer subentries."""
    layers: dict[str, Layer] = {}
    for subentry in entry.subentries.values():
        if subentry.subentry_type != SUBENTRY_TYPE_LAYER:
            continue
        layer = _layer_from_config(entry.entry_id, dict(subentry.data))
        layers[layer.id] = layer
    runtime = OverlayRuntime(hass, entry.entry_id, layers)
    hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id] = runtime
    await runtime.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
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
    attributes = [item.strip() for item in data["attribute"].split(",") if item.strip()]
    duration = data.get("duration_seconds")
    return Layer(
        id=data["layer_id"],
        overlay_set_id=overlay_set_id,
        role=data["role"],
        priority=int(data.get("priority", 0)),
        channels=[Channel(entity_id, attribute) for entity_id in entities for attribute in attributes],
        value=_parse_value(data["value"]),
        op=data.get("op", "override"),
        opacity=float(data.get("opacity", 1.0)),
        lifetime=LifetimeSpec(
            mode=data["lifetime_mode"],
            duration=timedelta(seconds=float(duration)) if duration else None,
            condition_entity=data.get("condition_entity"),
        ),
    )
