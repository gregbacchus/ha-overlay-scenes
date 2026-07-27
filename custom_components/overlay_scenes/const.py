"""Constants for Overlay Scenes."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "overlay_scenes"
PLATFORMS = ["sensor"]
STORAGE_KEY = f"{DOMAIN}.layers"
STORAGE_VERSION = 1

SERVICE_ACTIVATE_LAYER = "activate_layer"
SERVICE_DEACTIVATE_LAYER = "deactivate_layer"

DATA_RUNTIMES = "runtimes"
SUBENTRY_TYPE_LAYER = "layer"

DEFAULT_PRIORITY = 0
DEFAULT_OPACITY = 1.0
PENDING_CONTEXT_TTL = 10.0


class LayerRole(StrEnum):
    """Layer roles."""

    SOURCE = "source"
    MODIFIER = "modifier"


class LifetimeMode(StrEnum):
    """Supported lifetime modes."""

    DURATION = "duration"
    UNTIL_TRIGGER = "until_trigger"
    WHILE_CONDITION = "while_condition"


NUMERIC_OPS = ("override", "add", "clamp_min", "clamp_max", "average")
BOOLEAN_OPS = ("override", "or", "and", "nand", "nor", "xor", "xnor")
COLOR_OPS = ("override", "screen", "multiply")
ALL_OPS = NUMERIC_OPS + BOOLEAN_OPS + COLOR_OPS

