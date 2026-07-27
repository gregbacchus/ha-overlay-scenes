"""Regression coverage for the adversarial implementation review."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


def _install_home_assistant_stubs() -> None:
    """Install minimal stubs only when Home Assistant is unavailable."""
    if importlib.util.find_spec("homeassistant") is not None:
        return

    package = ModuleType("custom_components.overlay_scenes")
    package.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "overlay_scenes")]
    sys.modules[package.__name__] = package

    homeassistant = ModuleType("homeassistant")
    core = ModuleType("homeassistant.core")
    core.Context = lambda: SimpleNamespace(id="generated", parent_id=None)
    core.Event = object
    core.HomeAssistant = object
    core.callback = lambda function: function
    constants = ModuleType("homeassistant.const")
    constants.ATTR_ENTITY_ID = "entity_id"
    constants.SERVICE_TURN_OFF = "turn_off"
    constants.SERVICE_TURN_ON = "turn_on"
    constants.STATE_OFF = "off"
    constants.STATE_ON = "on"
    helpers = ModuleType("homeassistant.helpers")
    event = ModuleType("homeassistant.helpers.event")
    event.async_track_state_change_event = lambda hass, entity_ids, callback: hass.track(
        entity_ids, callback
    )
    template = ModuleType("homeassistant.helpers.template")
    template.Template = type("Template", (), {})
    storage = ModuleType("homeassistant.helpers.storage")
    storage.Store = object
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.core": core,
            "homeassistant.const": constants,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.event": event,
            "homeassistant.helpers.template": template,
            "homeassistant.helpers.storage": storage,
        }
    )


_install_home_assistant_stubs()

from custom_components.overlay_scenes.compositor import apply_op, resolve_channel
from custom_components.overlay_scenes.lifecycle import LifecycleManager
from custom_components.overlay_scenes.models import Channel, Layer, LifetimeSpec
from custom_components.overlay_scenes.registry import ChannelRegistry
from custom_components.overlay_scenes.runtime import OverlayRuntime
from custom_components.overlay_scenes.store import (
    deserialize_layer,
    parse_expiry,
    serialize_active,
    serialize_layer,
)
import importlib

store_module = importlib.import_module("custom_components.overlay_scenes.store")
runtime_module = importlib.import_module("custom_components.overlay_scenes.runtime")
from custom_components.overlay_scenes.writethrough import WriteThroughHandler


class _Loop:
    def __init__(self) -> None:
        self.handles = []

    def call_later(self, delay, callback):
        handle = SimpleNamespace(delay=delay, callback=callback, cancelled=False)
        handle.cancel = lambda: setattr(handle, "cancelled", True)
        self.handles.append(handle)
        return handle


class _ConditionHass:
    def __init__(self) -> None:
        self.loop = _Loop()
        self.callback = None
        self.unsubscribe_count = 0

    def track(self, entity_ids, callback):
        self.callback = callback

        def unsubscribe():
            self.unsubscribe_count += 1

        return unsubscribe


class ReviewRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_modifier_priority_controls_fold_order(self) -> None:
        channel = Channel("light.hall", "brightness")
        override = Layer(
            "override", "set", "modifier", [channel], 100, "override", priority=20
        )
        ceiling = Layer(
            "ceiling", "set", "modifier", [channel], 50, "clamp_max", priority=10
        )
        self.assertEqual(
            resolve_channel(80, None, [override, ceiling], channel),
            100,
        )

    def test_explicit_false_source_is_not_reenabled_by_modifier(self) -> None:
        channel = Channel("light.hall", "state")
        source = Layer("switch_off", "set", "source", [channel], False)
        motion = Layer("motion", "set", "modifier", [channel], True, "or")
        self.assertIs(resolve_channel(True, source, [motion], channel), False)

    def test_override_opacity_boundaries(self) -> None:
        self.assertEqual(apply_op("override", 10, 30, 0), 10)
        self.assertEqual(apply_op("override", 10, 30, 1), 30)
        self.assertEqual(apply_op("override", (0, 100, 200), (100, 200, 0), 0.5), (50, 150, 100))

    def test_missing_numeric_base_is_zero_for_modifier_fold(self) -> None:
        channel = Channel("light.hall", "brightness")
        modifier = Layer(
            "floor", "set", "modifier", [channel], 10, "clamp_min", lifetime=LifetimeSpec()
        )
        self.assertEqual(resolve_channel(None, None, [modifier], channel), 10)

    def test_native_light_brightness_is_normalized_to_percentage(self) -> None:
        state = SimpleNamespace(state="on", attributes={"brightness": 128})
        value = OverlayRuntime._read_state_value(
            state, Channel("light.hall", "brightness")
        )
        self.assertAlmostEqual(value, 50.196, places=3)

    def test_off_light_brightness_base_is_zero_even_when_attribute_is_retained(self) -> None:
        state = SimpleNamespace(state="off", attributes={"brightness": 128})
        value = OverlayRuntime._read_state_value(
            state, Channel("light.hall", "brightness")
        )
        self.assertEqual(value, 0)

    def test_condition_false_keeps_listener_armed_for_next_true(self) -> None:
        hass = _ConditionHass()
        registry = ChannelRegistry()
        channel = Channel("light.hall", "brightness")
        layer = Layer(
            "night",
            "set",
            "modifier",
            [channel],
            50,
            "clamp_max",
            lifetime=LifetimeSpec("while_condition", condition_entity="input_boolean.night"),
        )
        registry.activate(layer)
        manager = LifecycleManager(hass, registry, lambda: None)
        manager.start(layer)
        hass.callback(SimpleNamespace(data={"new_state": SimpleNamespace(state="off")}))
        self.assertEqual(hass.unsubscribe_count, 0)
        hass.callback(SimpleNamespace(data={"new_state": SimpleNamespace(state="on")}))
        self.assertTrue(registry.channels_for(layer.id))

    def test_nonzero_numeric_condition_state_is_truthy(self) -> None:
        hass = _ConditionHass()
        registry = ChannelRegistry()
        channel = Channel("light.hall", "brightness")
        layer = Layer(
            "night",
            "set",
            "modifier",
            [channel],
            50,
            "clamp_max",
            lifetime=LifetimeSpec("while_condition", condition_entity="sensor.night_level"),
        )
        manager = LifecycleManager(hass, registry, lambda: None)
        manager.start(layer)
        hass.callback(SimpleNamespace(data={"new_state": SimpleNamespace(state="2")}))
        self.assertTrue(registry.channels_for(layer.id))

    def test_restore_schedules_only_the_record_channel(self) -> None:
        hass = _ConditionHass()
        registry = ChannelRegistry()
        first = Channel("light.hall", "state")
        second = Channel("light.hall", "brightness")
        configured = Layer(
            "source",
            "set",
            "source",
            [first, second],
            True,
            lifetime=LifetimeSpec("duration", timedelta(minutes=5)),
        )
        registry.activate(configured)
        manager = LifecycleManager(hass, registry, lambda: None)
        scoped = Layer(
            configured.id,
            configured.overlay_set_id,
            configured.role,
            [first],
            configured.value,
            lifetime=configured.lifetime,
        )
        manager.start(scoped, expires_at=datetime.now(UTC) + timedelta(minutes=1))
        self.assertIsNotNone(manager.expires_at(configured.id, first))
        self.assertIsNone(manager.expires_at(configured.id, second))

    def test_duration_expiry_deactivates_only_its_channel(self) -> None:
        hass = _ConditionHass()
        registry = ChannelRegistry()
        first = Channel("light.hall", "state")
        second = Channel("light.hall", "brightness")
        layer = Layer(
            "source",
            "set",
            "source",
            [first, second],
            True,
            lifetime=LifetimeSpec("duration", timedelta(minutes=1)),
        )
        registry.activate(layer)
        manager = LifecycleManager(hass, registry, lambda: None)
        manager.start(layer)
        first_handle = manager._timers[(layer.id, first)]
        first_handle.callback()
        self.assertNotIn(first, registry.channels_for(layer.id))
        self.assertIn(second, registry.channels_for(layer.id))

    def test_duration_refresh_cancels_and_replaces_timer(self) -> None:
        hass = _ConditionHass()
        registry = ChannelRegistry()
        channel = Channel("light.hall", "brightness")
        layer = Layer(
            "boost",
            "set",
            "modifier",
            [channel],
            100,
            lifetime=LifetimeSpec("duration", timedelta(seconds=60)),
        )
        registry.activate(layer)
        manager = LifecycleManager(hass, registry, lambda: None)
        manager.start(layer)
        original = manager._timers[(layer.id, channel)]
        manager.refresh(layer, timedelta(seconds=120))
        replacement = manager._timers[(layer.id, channel)]
        self.assertTrue(original.cancelled)
        self.assertIsNot(original, replacement)
        self.assertGreater(replacement.delay, 119)

    def test_active_record_persists_external_base(self) -> None:
        channel = Channel("light.hall", "brightness")
        layer = Layer("night", "set", "modifier", [channel], 50, lifetime=LifetimeSpec())
        record = serialize_active(layer, channel, None, base_value=100)
        self.assertEqual(record["base_value"], 100)

    def test_layer_storage_round_trip_preserves_contract_fields(self) -> None:
        channel = Channel("light.hall", "brightness")
        original = Layer(
            "night",
            "set",
            "modifier",
            [channel],
            50,
            "clamp_max",
            7,
            0.75,
            LifetimeSpec("duration", timedelta(seconds=30)),
        )
        restored = deserialize_layer(serialize_layer(original))
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.channels, original.channels)
        self.assertEqual(restored.value, original.value)
        self.assertEqual(restored.op, original.op)
        self.assertEqual(restored.priority, original.priority)
        self.assertEqual(restored.opacity, original.opacity)
        self.assertEqual(restored.lifetime.duration, original.lifetime.duration)

    def test_expiry_parser_normalizes_offsets_to_utc(self) -> None:
        self.assertEqual(
            parse_expiry("2026-07-27T20:00:00+12:00"),
            datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
        )

    async def test_brightness_is_written_as_percentage(self) -> None:
        calls = []

        async def async_call(domain, service, data, **kwargs):
            calls.append((domain, service, data))

        hass = SimpleNamespace(
            loop=_Loop(), services=SimpleNamespace(async_call=async_call)
        )
        writer = WriteThroughHandler(hass)
        await writer.apply(Channel("light.hall", "brightness"), 50)
        self.assertEqual(calls[0][2]["brightness_pct"], 50)
        self.assertNotIn("brightness", calls[0][2])

    async def test_entity_channels_are_written_atomically_with_off_precedence(self) -> None:
        calls = []

        async def async_call(domain, service, data, **kwargs):
            calls.append((domain, service, data))

        hass = SimpleNamespace(
            loop=_Loop(), services=SimpleNamespace(async_call=async_call)
        )
        writer = WriteThroughHandler(hass)
        await writer.apply_many(
            {
                Channel("light.hall", "state"): False,
                Channel("light.hall", "brightness"): 0,
            }
        )
        self.assertEqual(calls, [("light", "turn_off", {"entity_id": "light.hall"})])

    async def test_light_on_combines_state_brightness_and_color(self) -> None:
        calls = []

        async def async_call(domain, service, data, **kwargs):
            calls.append((domain, service, data))

        hass = SimpleNamespace(loop=_Loop(), services=SimpleNamespace(async_call=async_call))
        writer = WriteThroughHandler(hass)
        await writer.apply_many(
            {
                Channel("light.hall", "state"): True,
                Channel("light.hall", "brightness"): 75,
                Channel("light.hall", "rgb_color"): (10, 20, 30),
            }
        )
        self.assertEqual(
            calls,
            [
                (
                    "light",
                    "turn_on",
                    {
                        "entity_id": "light.hall",
                        "brightness_pct": 75.0,
                        "rgb_color": (10, 20, 30),
                    },
                )
            ],
        )

    async def test_switch_and_media_player_dispatch(self) -> None:
        calls = []

        async def async_call(domain, service, data, **kwargs):
            calls.append((domain, service, data))

        hass = SimpleNamespace(loop=_Loop(), services=SimpleNamespace(async_call=async_call))
        writer = WriteThroughHandler(hass)
        await writer.apply_many(
            {
                Channel("switch.pump", "state"): False,
                Channel("media_player.lounge", "volume_level"): 0.35,
            }
        )
        self.assertEqual(
            calls,
            [
                ("switch", "turn_off", {"entity_id": "switch.pump"}),
                (
                    "media_player",
                    "volume_set",
                    {"entity_id": "media_player.lounge", "volume_level": 0.35},
                ),
            ],
        )

    async def test_out_of_range_brightness_is_rejected_without_service_call(self) -> None:
        calls = []

        async def async_call(*args, **kwargs):
            calls.append(args)

        hass = SimpleNamespace(loop=_Loop(), services=SimpleNamespace(async_call=async_call))
        writer = WriteThroughHandler(hass)
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            await writer.apply(Channel("light.hall", "brightness"), 101)
        self.assertEqual(calls, [])

    def test_feedback_context_expires(self) -> None:
        hass = SimpleNamespace(loop=_Loop())
        writer = WriteThroughHandler(hass)
        writer._remember("ours")
        event = SimpleNamespace(context=SimpleNamespace(id="ours", parent_id=None))
        self.assertTrue(writer.should_ignore(event))
        hass.loop.handles[0].callback()
        self.assertFalse(writer.should_ignore(event))

    async def test_concurrent_overlay_set_saves_do_not_overwrite_each_other(self) -> None:
        class FakeStore:
            data = {"active": []}

            def __init__(self, *args):
                pass

            async def async_load(self):
                await asyncio.sleep(0)
                return {"active": list(type(self).data["active"])}

            async def async_save(self, data):
                await asyncio.sleep(0)
                type(self).data = data

        original = store_module.Store
        store_module.Store = FakeStore
        try:
            hass = SimpleNamespace(data={})
            first = store_module.LayerStore(hass)
            second = store_module.LayerStore(hass)
            record_a = {"layer": {"overlay_set_id": "a"}}
            record_b = {"layer": {"overlay_set_id": "b"}}
            await asyncio.gather(
                first.async_save("a", [record_a]),
                second.async_save("b", [record_b]),
            )
            self.assertEqual(
                {item["layer"]["overlay_set_id"] for item in FakeStore.data["active"]},
                {"a", "b"},
            )
        finally:
            store_module.Store = original

    async def test_runtime_recompute_batches_all_entity_channels(self) -> None:
        state = Channel("light.hall", "state")
        brightness = Channel("light.hall", "brightness")
        source = Layer(
            "scene",
            "set",
            "source",
            [state, brightness],
            {"state": True, "brightness": 80},
        )
        registry = ChannelRegistry()
        registry.activate(source)

        class RecordingWriter:
            def __init__(self):
                self.calls = []

            async def apply_many(self, values):
                self.calls.append(values)

        runtime = OverlayRuntime.__new__(OverlayRuntime)
        runtime.registry = registry
        runtime._base_values = {state: False, brightness: 0}
        runtime.composites = {}
        runtime.writer = RecordingWriter()
        runtime._listeners = []
        runtime.hass = SimpleNamespace()
        await runtime._async_recompute({state, brightness}, "test")
        self.assertEqual(
            runtime.writer.calls,
            [{state: True, brightness: 80}],
        )

    async def test_single_channel_registry_change_recomputes_full_entity(self) -> None:
        state = Channel("light.hall", "state")
        brightness = Channel("light.hall", "brightness")
        configured = Layer(
            "scene",
            "set",
            "source",
            [state, brightness],
            {"state": False, "brightness": 0},
        )

        class RecordingWriter:
            def __init__(self):
                self.calls = []

            async def apply_many(self, values):
                self.calls.append(values)

        runtime = OverlayRuntime.__new__(OverlayRuntime)
        runtime.layers = {configured.id: configured}
        runtime.registry = ChannelRegistry()
        runtime._base_values = {state: False, brightness: 0}
        runtime.composites = {}
        runtime.writer = RecordingWriter()
        runtime._listeners = []
        runtime._schedule_save = lambda: None
        runtime.hass = SimpleNamespace(async_create_task=asyncio.create_task)
        runtime._registry_changed({brightness}, "test")
        await asyncio.sleep(0)
        self.assertEqual(
            runtime.writer.calls,
            [{state: False, brightness: 0}],
        )

    async def test_source_eviction_cancels_only_evicted_channel_timer(self) -> None:
        hass = _ConditionHass()
        state = Channel("light.hall", "state")
        brightness = Channel("light.hall", "brightness")
        original = Layer(
            "sunset",
            "set",
            "source",
            [state, brightness],
            {"state": True, "brightness": 100},
            lifetime=LifetimeSpec("duration", timedelta(minutes=30)),
        )
        replacement = Layer(
            "switch",
            "set",
            "source",
            [brightness],
            80,
            lifetime=LifetimeSpec("until_trigger"),
        )
        runtime = OverlayRuntime.__new__(OverlayRuntime)
        runtime.layers = {original.id: original, replacement.id: replacement}
        runtime.registry = ChannelRegistry()
        runtime.lifecycle = LifecycleManager(hass, runtime.registry, lambda: None)
        runtime.layer_status = {
            original.id: {"state": "idle", "reason": None},
            replacement.id: {"state": "idle", "reason": None},
        }
        runtime._listeners = []
        await runtime.async_activate(original.id)
        original_state_timer = runtime.lifecycle._timers[(original.id, state)]
        original_brightness_timer = runtime.lifecycle._timers[(original.id, brightness)]
        await runtime.async_activate(replacement.id)
        self.assertFalse(original_state_timer.cancelled)
        self.assertTrue(original_brightness_timer.cancelled)
        self.assertEqual(runtime.registry.active_layers_for(state)[0].id, original.id)
        self.assertEqual(
            runtime.registry.active_layers_for(brightness)[0].id,
            replacement.id,
        )

    async def test_restart_restores_external_base_then_expiry_reasserts_it(self) -> None:
        channel = Channel("light.hall", "brightness")
        layer = Layer(
            "night",
            "set",
            "modifier",
            [channel],
            50,
            "clamp_max",
            lifetime=LifetimeSpec("duration", timedelta(minutes=1)),
        )
        expiry = datetime.now(UTC) + timedelta(minutes=1)
        stored = {
            "active": [
                serialize_active(layer, channel, expiry, base_value=100)
            ]
        }

        class FakeLayerStore:
            def __init__(self, hass):
                pass

            async def async_load(self):
                return stored

            async def async_save(self, overlay_set_id, records):
                stored["active"] = records

        service_calls = []

        async def async_call(domain, service, data, **kwargs):
            service_calls.append((domain, service, data))

        physical_state = SimpleNamespace(state="on", attributes={"brightness": 128})
        hass = SimpleNamespace(
            loop=asyncio.get_running_loop(),
            states=SimpleNamespace(get=lambda entity_id: physical_state),
            services=SimpleNamespace(async_call=async_call),
            track=lambda entity_ids, callback: lambda: None,
            async_create_task=asyncio.create_task,
        )
        original_store = runtime_module.LayerStore
        runtime_module.LayerStore = FakeLayerStore
        try:
            runtime = OverlayRuntime(hass, "set", {layer.id: layer})
            await runtime.async_start()
            await asyncio.sleep(0)
            self.assertEqual(runtime.base_value(channel), 100)
            self.assertEqual(runtime.composites[channel], 50)
            runtime.lifecycle._timers[(layer.id, channel)]._callback()
            await asyncio.sleep(0)
            self.assertEqual(runtime.composites[channel], 100)
            self.assertEqual(service_calls[-1][2]["brightness_pct"], 100.0)
            await runtime.async_stop()
        finally:
            runtime_module.LayerStore = original_store

    async def test_restart_deactivates_restored_layer_when_condition_is_false(self) -> None:
        channel = Channel("light.hall", "brightness")
        layer = Layer(
            "night",
            "set",
            "modifier",
            [channel],
            50,
            "clamp_max",
            lifetime=LifetimeSpec(
                "while_condition", condition_entity="input_boolean.night"
            ),
        )
        stored = {
            "active": [serialize_active(layer, channel, None, base_value=100)]
        }

        class FakeLayerStore:
            def __init__(self, hass):
                pass

            async def async_load(self):
                return stored

            async def async_save(self, overlay_set_id, records):
                stored["active"] = records

        states = {
            "light.hall": SimpleNamespace(state="on", attributes={"brightness": 128}),
            "input_boolean.night": SimpleNamespace(state="off", attributes={}),
        }

        async def async_call(*args, **kwargs):
            pass

        hass = SimpleNamespace(
            loop=asyncio.get_running_loop(),
            states=SimpleNamespace(get=states.get),
            services=SimpleNamespace(async_call=async_call),
            track=lambda entity_ids, callback: lambda: None,
            async_create_task=asyncio.create_task,
        )
        original_store = runtime_module.LayerStore
        runtime_module.LayerStore = FakeLayerStore
        try:
            runtime = OverlayRuntime(hass, "set", {layer.id: layer})
            await runtime.async_start()
            await asyncio.sleep(0)
            self.assertFalse(runtime.registry.channels_for(layer.id))
            await runtime.async_stop()
        finally:
            runtime_module.LayerStore = original_store


if __name__ == "__main__":
    unittest.main()
