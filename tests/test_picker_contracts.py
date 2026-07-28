"""Picker-oriented configuration and action contracts."""

from pathlib import Path
import sys
from types import ModuleType
from types import SimpleNamespace
import unittest

package = ModuleType("custom_components.overlay_scenes")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "overlay_scenes")
]
sys.modules.setdefault(package.__name__, package)

from custom_components.overlay_scenes.pickers import common_entity_attributes
from custom_components.overlay_scenes.action_targets import layer_reference_from_entity


INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "overlay_scenes"
)


class PickerContractTests(unittest.TestCase):
    """Keep authoring choices constrained to valid Overlay Scenes targets."""

    def test_attribute_options_are_the_intersection_with_state_always_available(self) -> None:
        states = {
            "light.first": SimpleNamespace(
                attributes={"brightness": 100, "rgb_color": (1, 2, 3)}
            ),
            "light.second": SimpleNamespace(attributes={"brightness": 50}),
        }

        self.assertEqual(
            common_entity_attributes(states.get, ["light.first", "light.second"]),
            ["state", "brightness"],
        )

    def test_missing_entity_state_does_not_offer_unverified_attributes(self) -> None:
        states = {
            "light.first": SimpleNamespace(attributes={"brightness": 100}),
        }

        self.assertEqual(
            common_entity_attributes(states.get, ["light.first", "light.missing"]),
            ["state"],
        )

    def test_picker_does_not_offer_attributes_the_writer_cannot_control(self) -> None:
        states = {
            "light.first": SimpleNamespace(
                attributes={"brightness": 100, "friendly_name": "First"}
            ),
            "media_player.room": SimpleNamespace(
                attributes={"volume_level": 0.5, "friendly_name": "Room"}
            ),
        }

        self.assertEqual(
            common_entity_attributes(states.get, ["light.first"]),
            ["state", "brightness"],
        )
        self.assertEqual(
            common_entity_attributes(
                states.get, ["light.first", "media_player.room"]
            ),
            [],
        )

    def test_service_actions_expose_only_picker_fields(self) -> None:
        services = (INTEGRATION_DIR / "services.yaml").read_text()

        self.assertIn("config_entry_id:", services)
        self.assertIn("config_entry:", services)
        self.assertIn("layer_entity_id:", services)
        self.assertIn("integration: overlay_scenes", services)
        self.assertIn("filter:", services)
        self.assertIn("device_class: enum", services)
        self.assertNotIn("    overlay_set_id:", services)
        self.assertNotIn("    layer_id:", services)

    def test_layer_picker_resolves_only_a_layer_status_entity(self) -> None:
        states = {
            "sensor.night_status": SimpleNamespace(
                attributes={"layer_id": "hallway.night"}
            ),
            "sensor.composite": SimpleNamespace(attributes={"overlay_set_id": "hallway"}),
        }

        self.assertEqual(
            layer_reference_from_entity(states.get, "sensor.night_status"),
            "hallway.night",
        )
        with self.assertRaisesRegex(ValueError, "not an Overlay Scenes layer"):
            layer_reference_from_entity(states.get, "sensor.composite")
