"""Data models used by Overlay Scenes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .const import DEFAULT_OPACITY, DEFAULT_PRIORITY, LifetimeMode, LayerRole


@dataclass(frozen=True, slots=True, order=True)
class Channel:
    """A composited entity state or attribute."""

    entity_id: str
    attribute: str

    @property
    def key(self) -> str:
        """Return a stable serialization key."""
        return f"{self.entity_id}|{self.attribute}"

    @classmethod
    def from_key(cls, key: str) -> "Channel":
        """Create a channel from its storage key."""
        entity_id, attribute = key.rsplit("|", 1)
        return cls(entity_id, attribute)


@dataclass(slots=True)
class LifetimeSpec:
    """Rules controlling how long a layer remains active."""

    mode: LifetimeMode | str = LifetimeMode.UNTIL_TRIGGER
    duration: timedelta | None = None
    condition_entity: str | None = None


@dataclass(slots=True)
class Layer:
    """A configured source or modifier layer."""

    id: str
    overlay_set_id: str
    role: LayerRole | str
    channels: list[Channel]
    value: Any
    op: str = "override"
    priority: int = DEFAULT_PRIORITY
    opacity: float = DEFAULT_OPACITY
    lifetime: LifetimeSpec = field(default_factory=LifetimeSpec)

    def value_for(self, channel: Channel) -> Any:
        """Return a channel-specific value when a mapping was configured."""
        if not isinstance(self.value, dict):
            return self.value
        return self.value.get(
            channel.key,
            self.value.get(channel.attribute, self.value.get(channel.entity_id)),
        )


@dataclass(frozen=True, slots=True)
class EvictionEvent:
    """A source displacement on one channel."""

    source: Layer
    evicted: Layer
    channel: Channel


@dataclass(slots=True)
class ChannelState:
    """Active registry state for a channel."""

    source: Layer | None = None
    modifiers: list[Layer] = field(default_factory=list)

