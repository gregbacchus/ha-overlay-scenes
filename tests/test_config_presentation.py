"""Config entry and layer presentation contract tests."""

import json
from pathlib import Path
import sys
from types import ModuleType
import unittest


package = ModuleType("custom_components.overlay_scenes")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "overlay_scenes")
]
sys.modules.setdefault(package.__name__, package)

from custom_components.overlay_scenes.presentation import (
    layer_title,
    overlay_set_title,
)


class ConfigPresentationTests(unittest.TestCase):
    """Keep native Home Assistant labels useful and addressable."""

    def test_overlay_set_title_includes_name_and_set_id(self) -> None:
        self.assertEqual(
            overlay_set_title("Hallway Lights", "hallway_lights"),
            "Hallway Lights · ID: hallway_lights",
        )

    def test_layer_title_includes_full_id_attribute_and_entities(self) -> None:
        self.assertEqual(
            layer_title(
                "hallway_lights",
                {
                    "layer_id": "hallway_night_dimness",
                    "entities": ["light.hallway_1", "light.hallway_2"],
                    "attribute": "brightness",
                },
            ),
            (
                "hallway_lights.hallway_night_dimness · brightness · "
                "light.hallway_1, light.hallway_2"
            ),
        )

    def test_layer_title_normalizes_single_entity_selector_value(self) -> None:
        self.assertEqual(
            layer_title(
                "hallway_lights",
                {
                    "layer_id": "hallway_power",
                    "entities": "light.hallway",
                    "attribute": "state",
                },
            ),
            "hallway_lights.hallway_power · state · light.hallway",
        )

    def test_native_entry_types_name_overlay_sets_and_layers(self) -> None:
        integration_dir = (
            Path(__file__).parents[1] / "custom_components" / "overlay_scenes"
        )
        for path in (
            integration_dir / "strings.json",
            integration_dir / "translations" / "en.json",
        ):
            with self.subTest(path=path):
                translations = json.loads(path.read_text())
                self.assertEqual(translations["config"]["entry_type"], "Overlay Set")
                self.assertEqual(
                    translations["config_subentries"]["layer"]["entry_type"],
                    "Layer",
                )
                self.assertEqual(
                    translations["config"]["initiate_flow"]["user"],
                    "Add Overlay Set",
                )
                self.assertEqual(
                    translations["config_subentries"]["layer"]["initiate_flow"][
                        "user"
                    ],
                    "Add Layer",
                )
                self.assertEqual(
                    translations["config_subentries"]["layer"]["initiate_flow"][
                        "reconfigure"
                    ],
                    "Edit Layer",
                )
