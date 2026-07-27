"""Diagnostic sensor entities for Overlay Scenes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DATA_RUNTIMES, DOMAIN
from .ha_presentation import target_display_name
from .models import Channel, Layer
from .runtime import OverlayRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up diagnostic entities."""
    runtime: OverlayRuntime = hass.data[DOMAIN][DATA_RUNTIMES][entry.entry_id]
    channels = {channel for layer in runtime.layers.values() for channel in layer.channels}
    async_add_entities(
        [
            CompositeSensor(
                runtime, channel, target_display_name(hass, channel.entity_id)
            )
            for channel in channels
        ]
        + [
            LayerStatusSensor(runtime, layer) for layer in runtime.layers.values()
        ]
    )


class RuntimeSensor(SensorEntity):
    """Base class for runtime-backed sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, runtime: OverlayRuntime) -> None:
        self.runtime = runtime
        self._unsub = None

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
        channel: Channel,
        target_name: str,
    ) -> None:
        super().__init__(runtime)
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

    def __init__(self, runtime: OverlayRuntime, layer: Layer) -> None:
        super().__init__(runtime)
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
