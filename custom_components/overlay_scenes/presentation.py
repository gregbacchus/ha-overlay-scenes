"""Native Home Assistant config entry presentation helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def overlay_set_title(name: str, set_id: str) -> str:
    """Return an Overlay Set title that exposes its service-facing ID."""
    return f"{name} · ID: {set_id}"


def layer_title(overlay_set_id: str, data: Mapping[str, Any]) -> str:
    """Return a Layer title with its address and controlled channels."""
    configured_entities = data["entities"]
    entities = (
        [configured_entities]
        if isinstance(configured_entities, str)
        else configured_entities
    )
    targets = ", ".join(entities)
    return (
        f"{overlay_set_id}.{data['layer_id']} · {data['attribute'].strip()} · {targets}"
    )
