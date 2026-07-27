"""Registry eviction tests."""

from custom_components.overlay_scenes.models import Channel, Layer, LifetimeSpec
from custom_components.overlay_scenes.registry import ChannelRegistry


def layer(layer_id: str, channels: list[Channel]) -> Layer:
    return Layer(layer_id, "set", "source", channels, True, lifetime=LifetimeSpec())


def test_source_eviction_is_per_channel() -> None:
    first_light = Channel("light.hall_1", "brightness")
    second_light = Channel("light.hall_2", "brightness")
    registry = ChannelRegistry()
    first = layer("first", [first_light, second_light])
    second = layer("second", [second_light])
    registry.activate(first)
    events = registry.activate(second)
    assert [(event.evicted.id, event.channel) for event in events] == [("first", second_light)]
    assert registry.active_layers_for(first_light)[0] is first
    assert registry.active_layers_for(second_light)[0] is second
