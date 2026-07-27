"""Diagnostic sensor entities for Overlay Scenes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DATA_RUNTIMES, DOMAIN
from .models import Channel, Layer
from .presentation import display_name
from .runtime import OverlayRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up diagnostic entities."""
    runtime: OverlayRuntime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    set_name = entry.data.get("name", entry.title)
    channels = {channel for layer in runtime.layers.values() for channel in layer.channels}
    async_add_entities(
        [
            CompositeSensor(
                runtime, set_name, channel, _target_display_name(hass, channel.entity_id)
            )
            for channel in channels
        ]
        + [
            LayerStatusSensor(runtime, set_name, layer)
            for layer in runtime.layers.values()
        ]
    )


def _target_display_name(hass: HomeAssistant, entity_id: str) -> str:
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


class RuntimeSensor(SensorEntity):
    """Base class for runtime-backed sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: OverlayRuntime, set_name: str) -> None:
        self.runtime = runtime
        self._unsub = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.entry_id)},
            name=set_name,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Overlay Scenes",
            model="Overlay Set",
        )

    async def async_added_to_hass(self) -> None:
        self._unsub = self.runtime.add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class CompositeSensor(RuntimeSensor):
    """Expose the current result and active fold stack."""

    def __init__(
        self,
        runtime: OverlayRuntime,
        set_name: str,
        channel: Channel,
        target_name: str,
    ) -> None:
        super().__init__(runtime, set_name)
        self.channel = channel
        self._attr_translation_key = "composite"
        self._attr_translation_placeholders = {
            "target_name": target_name,
            "attribute_name": channel.attribute.replace("_", " ").capitalize(),
        }
        self._attr_unique_id = f"{runtime.entry_id}_{channel.key}_composite"

    @property
    def native_value(self) -> Any:
        value = self.runtime.composites.get(self.channel, self.runtime.base_value(self.channel))
        return str(value) if isinstance(value, (tuple, list, dict)) else value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        source, modifiers = self.runtime.registry.active_layers_for(self.channel)
        return {
            "overlay_set_id": self.runtime.set_id,
            "entity_id": self.channel.entity_id,
            "attribute": self.channel.attribute,
            "source_layer_id": source.qualified_id if source else None,
            "modifier_layer_ids": [layer.qualified_id for layer in modifiers],
            "resolved_value": self.runtime.composites.get(self.channel),
        }


class LayerStatusSensor(RuntimeSensor):
    """Expose a layer's activity and lifecycle diagnostics."""

    def __init__(self, runtime: OverlayRuntime, set_name: str, layer: Layer) -> None:
        super().__init__(runtime, set_name)
        self.layer = layer
        self._attr_translation_key = "layer_status"
        self._attr_translation_placeholders = {
            "layer_name": layer.id.replace("_", " ").capitalize()
        }
        self._attr_unique_id = f"{runtime.entry_id}_{layer.id}_status"

    @property
    def native_value(self) -> str:
        return self.runtime.layer_status[self.layer.id]["state"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        expiry = self.runtime.lifecycle.expires_at(self.layer.id)
        return {
            "overlay_set_id": self.runtime.set_id,
            "layer_id": self.layer.qualified_id,
            "role": str(self.layer.role),
            "priority": self.layer.priority,
            "channels": [channel.key for channel in self.layer.channels],
            "expires_at": expiry.isoformat() if expiry else None,
            "reason": self.runtime.layer_status[self.layer.id]["reason"],
        }
