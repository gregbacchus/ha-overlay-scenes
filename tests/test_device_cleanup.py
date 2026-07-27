"""Device-registry compatibility regression tests."""

from pathlib import Path
import sys
from types import ModuleType
import unittest


package = ModuleType("custom_components.overlay_scenes")
package.__path__ = [
    str(Path(__file__).parents[1] / "custom_components" / "overlay_scenes")
]
sys.modules.setdefault(package.__name__, package)

from custom_components.overlay_scenes.device_cleanup import (
    remove_legacy_overlay_set_device,
)


class DeviceCleanupTests(unittest.TestCase):
    """Cover the device-registry API available in Home Assistant 2026.7."""

    def test_removes_matching_device_without_new_identifier_lookup_api(self) -> None:
        class Device:
            id = "legacy-device"

        class StableDeviceRegistry:
            def __init__(self) -> None:
                self.lookup: (
                    tuple[set[tuple[str, str]], set[tuple[str, str]] | None]
                    | None
                ) = None
                self.removed: list[str] = []

            def async_get_device(
                self,
                identifiers: set[tuple[str, str]],
                connections: set[tuple[str, str]] | None = None,
            ) -> Device:
                self.lookup = (identifiers, connections)
                return Device()

            def async_remove_device(self, device_id: str) -> None:
                self.removed.append(device_id)

        registry = StableDeviceRegistry()

        remove_legacy_overlay_set_device(registry, "overlay_scenes", "entry-1")

        self.assertEqual(
            registry.lookup, ({("overlay_scenes", "entry-1")}, None)
        )
        self.assertEqual(registry.removed, ["legacy-device"])

    def test_missing_legacy_device_is_a_noop(self) -> None:
        class EmptyDeviceRegistry:
            def async_get_device(
                self,
                identifiers: set[tuple[str, str]],
                connections: set[tuple[str, str]] | None = None,
            ) -> None:
                return None

            def async_remove_device(self, device_id: str) -> None:
                raise AssertionError("No device should be removed")

        remove_legacy_overlay_set_device(
            EmptyDeviceRegistry(), "overlay_scenes", "entry-1"
        )
