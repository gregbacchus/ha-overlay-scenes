"""Per-channel active layer registry."""

from __future__ import annotations

from collections.abc import Callable

from .const import LayerRole
from .models import Channel, ChannelState, EvictionEvent, Layer


class ChannelRegistry:
    """Track source exclusivity and modifiers independently per channel."""

    def __init__(self, on_change: Callable[[set[Channel], str], None] | None = None) -> None:
        self._state: dict[Channel, ChannelState] = {}
        self._on_change = on_change

    def activate(self, layer: Layer) -> list[EvictionEvent]:
        """Activate a layer and return any per-channel source evictions."""
        evictions: list[EvictionEvent] = []
        affected: set[Channel] = set()
        for channel in layer.channels:
            state = self._state.setdefault(channel, ChannelState())
            if layer.role == LayerRole.SOURCE or layer.role == "source":
                if state.source is not None and state.source.id != layer.id:
                    evictions.append(EvictionEvent(layer, state.source, channel))
                state.source = layer
            elif all(active.id != layer.id for active in state.modifiers):
                state.modifiers.append(layer)
            affected.add(channel)
        self._notify(affected, f"activate:{layer.id}")
        return evictions

    def deactivate(
        self, layer_id: str, reason: str, channel: Channel | None = None
    ) -> set[Channel]:
        """Remove a layer globally, or from a single channel."""
        affected: set[Channel] = set()
        channels = [channel] if channel is not None else list(self._state)
        for candidate in channels:
            state = self._state.get(candidate)
            if state is None:
                continue
            changed = False
            if state.source is not None and state.source.id == layer_id:
                state.source = None
                changed = True
            modifiers = [item for item in state.modifiers if item.id != layer_id]
            if len(modifiers) != len(state.modifiers):
                state.modifiers = modifiers
                changed = True
            if changed:
                affected.add(candidate)
            if state.source is None and not state.modifiers:
                self._state.pop(candidate, None)
        self._notify(affected, f"deactivate:{layer_id}:{reason}")
        return affected

    def active_layers_for(self, channel: Channel) -> tuple[Layer | None, list[Layer]]:
        """Return the source and modifiers in fold order."""
        state = self._state.get(channel, ChannelState())
        return state.source, sorted(state.modifiers, key=lambda layer: layer.priority)

    def channels_for(self, layer_id: str) -> set[Channel]:
        """Return channels currently occupied by a layer."""
        return {
            channel
            for channel, state in self._state.items()
            if (state.source and state.source.id == layer_id)
            or any(layer.id == layer_id for layer in state.modifiers)
        }

    @property
    def channels(self) -> set[Channel]:
        """Return all active channels."""
        return set(self._state)

    def _notify(self, channels: set[Channel], trigger: str) -> None:
        if channels and self._on_change is not None:
            self._on_change(channels, trigger)
