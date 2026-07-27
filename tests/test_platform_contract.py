"""Home Assistant platform-module contract checks."""

from pathlib import Path
import runpy
import unittest


INTEGRATION_DIR = (
    Path(__file__).parents[1] / "custom_components" / "overlay_scenes"
)


class PlatformContractTests(unittest.TestCase):
    """Protect Home Assistant's forwarded-platform import convention."""

    def test_every_forwarded_platform_has_an_importable_module_path(self) -> None:
        """Each forwarded platform must exist at ``<integration>/<platform>.py``."""
        constants = runpy.run_path(INTEGRATION_DIR / "const.py")

        missing_modules = [
            platform
            for platform in constants["PLATFORMS"]
            if not (INTEGRATION_DIR / f"{platform}.py").is_file()
        ]

        self.assertEqual(missing_modules, [])
