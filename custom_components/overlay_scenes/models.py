"""Data models used by Overlay Scenes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .const import DEFAULT_OPACITY, DEFAULT_PRIORITY, LifetimeMode, LayerRole


def parse_layer_reference(reference: str) -> tuple[str, str]:
    """Parse an exact ``<overlay_set_id>.<layer_id>`` reference."""
    set_id, separator, layer_id = reference.partition(".")
    if not separator or not set_id or not layer_id or "." in layer_id:
        raise ValueError("Layer references must use <overlay_set_id>.<layer_id>")
    return set_id, layer_id


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
    include_in_set_actions: bool = True

    def __post_init__(self) -> None:
        """Validate the layer's single-attribute contract."""
        attributes = {channel.attribute for channel in self.channels}
        if len(attributes) != 1 or any(
            not attribute.strip() or "," in attribute for attribute in attributes
        ):
            raise ValueError("A layer must target exactly one attribute")

    @property
    def qualified_id(self) -> str:
        """Return the public, Overlay Set-namespaced layer reference."""
        return f"{self.overlay_set_id}.{self.id}"

    def value_for(self, channel: Channel) -> Any:
        """Return the layer value shared by every targeted entity channel."""
        return self.value


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
