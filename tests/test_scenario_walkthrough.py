"""Acceptance-level walkthrough from the implementation design."""

from custom_components.overlay_scenes.compositor import resolve_channel
from custom_components.overlay_scenes.models import Channel, Layer, LifetimeSpec
from custom_components.overlay_scenes.registry import ChannelRegistry


def make(layer_id, role, channels, value, op="override", priority=0):
    return Layer(layer_id, "hall", role, channels, value, op, priority, lifetime=LifetimeSpec())


def test_worked_scenario() -> None:
    state1, bright1 = Channel("light.hallway_1", "state"), Channel("light.hallway_1", "brightness")
    state2, bright2 = Channel("light.hallway_2", "state"), Channel("light.hallway_2", "brightness")
    registry = ChannelRegistry()
    sunset_state = make("sunset_state", "source", [state1, state2], True)
    sunset_brightness = make("sunset_brightness", "source", [bright1, bright2], 100)
    registry.activate(sunset_state)
    registry.activate(sunset_brightness)
    assert resolve_channel(False, *registry.active_layers_for(state1), state1) is True
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 100

    night = make("night_max", "modifier", [bright1, bright2], 50, "clamp_max", 10)
    registry.activate(night)
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 50
    assert resolve_channel(0, *registry.active_layers_for(bright2), bright2) == 50

    boost = make("front_door_boost", "modifier", [bright1], 100, "override", 20)
    registry.activate(boost)
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 100
    assert resolve_channel(0, *registry.active_layers_for(bright2), bright2) == 50
    registry.deactivate(boost.id, "duration_elapsed")
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 50

    night_light = make("hallway_night_light", "modifier", [state1, state2], True, "or", 10)
    floor = make("hallway_night_floor", "modifier", [bright1, bright2], 10, "clamp_min", 5)
    registry.activate(night_light)
    registry.activate(floor)
    assert resolve_channel(False, *registry.active_layers_for(state1), state1) is True
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 50

    registry.deactivate(sunset_state.id, "duration_elapsed")
    registry.deactivate(sunset_brightness.id, "duration_elapsed")
    assert resolve_channel(False, *registry.active_layers_for(state1), state1) is True
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 10

    switch_on_state = make("switch_on_state", "source", [state1, state2], True)
    switch_on_brightness = make("switch_on_brightness", "source", [bright1, bright2], 100)
    registry.activate(switch_on_state)
    registry.activate(switch_on_brightness)
    assert resolve_channel(0, *registry.active_layers_for(bright1), bright1) == 50
    switch_off = make("switch_off", "source", [state1, state2], False)
    events = registry.activate(switch_off)
    assert {event.evicted.id for event in events} == {"switch_on_state"}
    assert resolve_channel(True, *registry.active_layers_for(state1), state1) is False
