"""Registry eviction tests."""

from custom_components.overlay_scenes.models import Channel, Layer, LifetimeSpec
from custom_components.overlay_scenes.registry import ChannelRegistry


def layer(layer_id: str, channels: list[Channel]) -> Layer:
    return Layer(layer_id, "set", "source", channels, True, lifetime=LifetimeSpec())


def test_source_eviction_is_per_channel() -> None:
    state = Channel("light.hall", "state")
    brightness = Channel("light.hall", "brightness")
    registry = ChannelRegistry()
    first = layer("first", [state, brightness])
    second = layer("second", [brightness])
    registry.activate(first)
    events = registry.activate(second)
    assert [(event.evicted.id, event.channel) for event in events] == [("first", brightness)]
    assert registry.active_layers_for(state)[0] is first
    assert registry.active_layers_for(brightness)[0] is second
