"""Runtime coordinator for an Overlay Set."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.template import Template

from .compositor import resolve_channel
from .lifecycle import LifecycleManager, state_is_truthy
from .models import Channel, Layer
from .registry import ChannelRegistry
from .store import LayerStore, parse_expiry, serialize_active
from .writethrough import WriteThroughHandler

_LOGGER = logging.getLogger(__name__)


class OverlayRuntime:
    """Coordinate registry, lifecycle, composition and persistence."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        layers: dict[str, Layer],
        set_id: str | None = None,
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.set_id = set_id or entry_id
        self.layers = layers
        self.registry = ChannelRegistry(self._registry_changed)
        self.store = LayerStore(hass)
        self.writer = WriteThroughHandler(hass)
        self.lifecycle = LifecycleManager(hass, self.registry, self._schedule_save)
        self.composites: dict[Channel, Any] = {}
        self._base_values: dict[Channel, Any] = {}
        self.layer_status: dict[str, dict[str, Any]] = {
            layer_id: {"state": "idle", "reason": None} for layer_id in layers
        }
        self._state_unsubs: list[Any] = []
        self._listeners: list[Any] = []

    async def async_start(self) -> None:
        """Restore active state and install base-state listeners."""
        channels = {channel for layer in self.layers.values() for channel in layer.channels}
        by_entity: dict[str, set[Channel]] = {}
        for channel in channels:
            by_entity.setdefault(channel.entity_id, set()).add(channel)
            self._base_values[channel] = self._read_state_value(
                self.hass.states.get(channel.entity_id), channel
            )
        for entity_id, entity_channels in by_entity.items():
            @callback
            def handle_base_changed(
                event: Event, items: set[Channel] = entity_channels
            ) -> None:
                self._base_changed(event, items)

            self._state_unsubs.append(
                async_track_state_change_event(
                    self.hass,
                    [entity_id],
                    handle_base_changed,
                )
            )

        stored = await self.store.async_load()
        restored: dict[str, tuple[Layer, datetime | None]] = {}
        now = datetime.now(UTC)
        for record in stored.get("active", []):
            if record.get("layer", {}).get("overlay_set_id") not in {
                self.set_id,
                self.entry_id,
            }:
                continue
            layer = self.layers.get(record["layer"]["id"])
            if layer is None:
                continue
            channel = Channel.from_key(record["channel"])
            if "base_value" in record:
                self._base_values[channel] = record["base_value"]
            expiry = parse_expiry(record.get("expires_at"))
            if expiry is not None and expiry <= now:
                continue
            # Restore only the channel that was independently active.
            scoped = Layer(
                id=layer.id,
                overlay_set_id=layer.overlay_set_id,
                role=layer.role,
                channels=[channel],
                value=layer.value,
                op=layer.op,
                priority=layer.priority,
                opacity=layer.opacity,
                lifetime=layer.lifetime,
                include_in_set_actions=layer.include_in_set_actions,
            )
            self.registry.activate(scoped)
            restored[f"{layer.id}|{channel.key}"] = (scoped, expiry)
        for layer, expiry in restored.values():
            self.lifecycle.start(layer, expires_at=expiry)

        for layer in self.layers.values():
            if str(layer.lifetime.mode) == "while_condition" and layer.lifetime.condition_entity:
                state = self.hass.states.get(layer.lifetime.condition_entity)
                if state and state_is_truthy(state.state):
                    self.registry.activate(layer)
                else:
                    self.registry.deactivate(layer.id, "condition_false")
                self.lifecycle.start(layer)

    async def async_activate(self, layer_id: str, duration: timedelta | None = None) -> None:
        """Activate or refresh a configured layer."""
        layer = self.layers[layer_id]
        already_active = bool(self.registry.channels_for(layer_id))
        evictions = self.registry.activate(layer)
        for event in evictions:
            expiry = self.lifecycle.expires_at(event.evicted.id, event.channel)
            _LOGGER.debug(
                "source %s evicted source %s on channel %s, cancelling expiry at %s",
                event.source.id,
                event.evicted.id,
                event.channel.key,
                expiry,
            )
            self.lifecycle.cancel(
                event.evicted, event.channel, f"evicted_by:{event.source.id}"
            )
            if not self.registry.channels_for(event.evicted.id):
                self._set_status(event.evicted.id, "idle", f"evicted_by:{event.source.id}")
        if already_active:
            self.lifecycle.refresh(layer, duration)
        else:
            self.lifecycle.start(layer, duration)
        self._set_status(layer.id, "active", "service_call")

    async def async_deactivate(self, layer_id: str, reason: str = "service_call") -> None:
        """Deactivate a configured layer."""
        self.lifecycle.cancel_layer(layer_id, reason)
        self.registry.deactivate(layer_id, reason)
        self._set_status(layer_id, "idle", reason)
        self._schedule_save()

    def _set_action_layers(self) -> list[Layer]:
        """Return layers controlled by set-level actions."""
        return [
            layer
            for layer in self.layers.values()
            if layer.include_in_set_actions
            and str(layer.lifetime.mode) != "while_condition"
        ]

    async def async_activate_set(self) -> None:
        """Activate every opted-in, non-condition layer in this Overlay Set."""
        layers = self._set_action_layers()
        source_by_channel: dict[Channel, str] = {}
        for layer in layers:
            if str(layer.role) != "source":
                continue
            for channel in layer.channels:
                if previous := source_by_channel.get(channel):
                    raise ValueError(
                        "Overlay Set has conflicting sources "
                        f"{previous} and {layer.id} on channel {channel.key}"
                    )
                source_by_channel[channel] = layer.id
        for layer in layers:
            await self.async_activate(layer.id)

    async def async_deactivate_set(self) -> None:
        """Deactivate every opted-in, non-condition layer in this Overlay Set."""
        for layer in self._set_action_layers():
            await self.async_deactivate(layer.id)

    async def async_stop(self) -> None:
        """Stop callbacks and persist state."""
        await self._async_save()
        self.lifecycle.shutdown()
        self.writer.shutdown()
        for unsub in self._state_unsubs:
            unsub()
        self._state_unsubs.clear()

    def add_listener(self, listener: Any) -> Any:
        """Subscribe an entity to coordinator changes."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def base_value(self, channel: Channel) -> Any:
        """Return the last externally authored value for a channel."""
        return self._base_values.get(channel)

    @staticmethod
    def _read_state_value(state: Any, channel: Channel) -> Any:
        """Extract a channel value from a Home Assistant State."""
        if state is None:
            return None
        if channel.attribute == "state":
            if state.state == STATE_ON:
                return True
            if state.state == STATE_OFF:
                return False
            return state.state
        value = state.attributes.get(channel.attribute)
        if (
            channel.entity_id.startswith("light.")
            and channel.attribute == "brightness"
        ):
            if state.state == STATE_OFF or value is None:
                return 0
            return float(value) * 100 / 255
        return value

    @callback
    def _registry_changed(self, channels: set[Channel], trigger: str) -> None:
        if trigger.startswith("activate:"):
            layer_id = trigger.split(":", 1)[1]
            self._set_status(layer_id, "active", "condition_true")
        elif trigger.startswith("deactivate:"):
            _, layer_id, reason = trigger.split(":", 2)
            if not self.registry.channels_for(layer_id):
                self._set_status(layer_id, "idle", reason)
        affected_entities = {channel.entity_id for channel in channels}
        entity_channels = {
            channel
            for layer in self.layers.values()
            for channel in layer.channels
            if channel.entity_id in affected_entities
        }
        self.hass.async_create_task(self._async_recompute(entity_channels, trigger))
        self._schedule_save()
        self._notify()

    @callback
    def _base_changed(self, event: Event, channels: set[Channel]) -> None:
        if self.writer.should_ignore(event):
            return
        new_state = event.data.get("new_state")
        for channel in channels:
            self._base_values[channel] = self._read_state_value(new_state, channel)
        self.hass.async_create_task(self._async_recompute(channels, "base_state_change"))

    async def _async_recompute(self, channels: set[Channel], trigger: str) -> None:
        def render(value: Any) -> Any:
            if isinstance(value, Template):
                return value.async_render(parse_result=True)
            if isinstance(value, str) and ("{{" in value or "{%" in value):
                template = Template(value, self.hass)
                return template.async_render(parse_result=True)
            return value

        outputs: dict[Channel, Any] = {}
        for channel in channels:
            source, modifiers = self.registry.active_layers_for(channel)
            base = self.base_value(channel)
            output = resolve_channel(base, source, modifiers, channel, render)
            self.composites[channel] = output
            _LOGGER.debug(
                "recompute channel=%s trigger=%s layers=%s inputs=%s output=%s",
                channel.key,
                trigger,
                [
                    (item.id, item.priority, str(item.role))
                    for item in ([source] if source else []) + modifiers
                ],
                {"base": base, "source": source.value_for(channel) if source else None},
                output,
            )
            if output is not None:
                outputs[channel] = output
        if outputs:
            await self.writer.apply_many(outputs)
        self._notify()

    def _set_status(self, layer_id: str, state: str, reason: str) -> None:
        self.layer_status.setdefault(layer_id, {}).update(state=state, reason=reason)
        self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def _schedule_save(self) -> None:
        self.hass.async_create_task(self._async_save())

    async def _async_save(self) -> None:
        records = []
        for channel in self.registry.channels:
            source, modifiers = self.registry.active_layers_for(channel)
            for layer in ([source] if source else []) + modifiers:
                records.append(
                    serialize_active(
                        layer,
                        channel,
                        self.lifecycle.expires_at(layer.id, channel),
                        base_value=self.base_value(channel),
                    )
                )
        await self.store.async_save(self.set_id, records, aliases={self.entry_id})
