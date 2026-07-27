"""Per-channel lifecycle management."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import LifetimeMode
from .models import Channel, Layer
from .registry import ChannelRegistry

_LOGGER = logging.getLogger(__name__)
_FALSE_STATES = {
    "",
    "0",
    "0.0",
    "off",
    "false",
    "no",
    "closed",
    "not_home",
    "unknown",
    "unavailable",
    "none",
    "null",
}


def state_is_truthy(value: object) -> bool:
    """Interpret a Home Assistant state using explicit false-state semantics."""
    normalized = str(value).strip().lower()
    if normalized in _FALSE_STATES:
        return False
    try:
        return float(normalized) != 0
    except ValueError:
        return True


class LifecycleManager:
    """Own timers and condition listeners for active layer channels."""

    def __init__(self, hass: HomeAssistant, registry: ChannelRegistry, save: Callable[[], None]) -> None:
        self.hass = hass
        self.registry = registry
        self._save = save
        self._timers: dict[tuple[str, Channel], asyncio.TimerHandle] = {}
        self._expires: dict[tuple[str, Channel], datetime] = {}
        self._condition_unsubs: dict[str, Callable[[], None]] = {}

    def start(
        self,
        layer: Layer,
        duration_override: timedelta | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        """Start or refresh lifecycle bookkeeping for every occupied channel."""
        mode = layer.lifetime.mode
        if mode == LifetimeMode.DURATION or mode == "duration":
            duration = duration_override or layer.lifetime.duration
            if expires_at is None and duration is None:
                raise ValueError(f"Duration layer {layer.id} has no duration")
            active_channels = self.registry.channels_for(layer.id)
            for channel in layer.channels:
                if channel not in active_channels:
                    continue
                self._schedule(layer, channel, expires_at or datetime.now(UTC) + duration)
        elif mode == LifetimeMode.WHILE_CONDITION or mode == "while_condition":
            self._subscribe_condition(layer)
        _LOGGER.debug("lifecycle layer=%s transition=activate reason=service_call", layer.id)
        self._save()

    def refresh(self, layer: Layer, duration_override: timedelta | None = None) -> None:
        """Reset a duration layer's timers."""
        self.start(layer, duration_override)
        _LOGGER.debug("lifecycle layer=%s transition=refresh reason=service_call", layer.id)

    def cancel(self, layer: Layer, channel: Channel, reason: str) -> None:
        """Cancel lifecycle bookkeeping for one channel only."""
        key = (layer.id, channel)
        if handle := self._timers.pop(key, None):
            handle.cancel()
        expiry = self._expires.pop(key, None)
        _LOGGER.debug(
            "lifecycle layer=%s channel=%s transition=cancel reason=%s expiry=%s",
            layer.id,
            channel.key,
            reason,
            expiry,
        )
        self._save()

    def cancel_layer(self, layer_id: str, reason: str) -> None:
        """Cancel all lifecycle resources for a layer."""
        for (candidate, channel) in list(self._timers):
            if candidate == layer_id:
                source, modifiers = self.registry.active_layers_for(channel)
                layer = source if source and source.id == layer_id else next(
                    (item for item in modifiers if item.id == layer_id), None
                )
                if layer:
                    self.cancel(layer, channel, reason)
                else:
                    self._timers.pop((candidate, channel)).cancel()
                    self._expires.pop((candidate, channel), None)

    def expires_at(self, layer_id: str, channel: Channel | None = None) -> datetime | None:
        """Return the latest expiry for a layer or a particular channel."""
        if channel is not None:
            return self._expires.get((layer_id, channel))
        values = [expiry for (candidate, _), expiry in self._expires.items() if candidate == layer_id]
        return max(values, default=None)

    def shutdown(self) -> None:
        """Cancel all in-memory callbacks."""
        for handle in self._timers.values():
            handle.cancel()
        self._timers.clear()
        self._expires.clear()
        for unsub in self._condition_unsubs.values():
            unsub()
        self._condition_unsubs.clear()

    def _schedule(self, layer: Layer, channel: Channel, expires_at: datetime) -> None:
        key = (layer.id, channel)
        if old := self._timers.pop(key, None):
            old.cancel()
        delay = max(0.0, (expires_at - datetime.now(UTC)).total_seconds())

        @callback
        def expire() -> None:
            self._timers.pop(key, None)
            self._expires.pop(key, None)
            self.registry.deactivate(layer.id, "duration_elapsed", channel)
            _LOGGER.debug(
                "lifecycle layer=%s channel=%s transition=expire reason=duration_elapsed",
                layer.id,
                channel.key,
            )
            self._save()

        self._timers[key] = self.hass.loop.call_later(delay, expire)
        self._expires[key] = expires_at

    def _subscribe_condition(self, layer: Layer) -> None:
        entity_id = layer.lifetime.condition_entity
        if not entity_id or layer.id in self._condition_unsubs:
            return

        @callback
        def condition_changed(event: Event) -> None:
            new_state = event.data.get("new_state")
            if new_state is not None and state_is_truthy(new_state.state):
                evictions = self.registry.activate(layer)
                for eviction in evictions:
                    self.cancel(
                        eviction.evicted,
                        eviction.channel,
                        f"evicted_by:{layer.id}",
                    )
                _LOGGER.debug(
                    "lifecycle layer=%s transition=activate reason=condition_true", layer.id
                )
            else:
                self.registry.deactivate(layer.id, "condition_false")
                _LOGGER.debug(
                    "lifecycle layer=%s transition=deactivate reason=condition_false", layer.id
                )

        self._condition_unsubs[layer.id] = async_track_state_change_event(
            self.hass, [entity_id], condition_changed
        )
