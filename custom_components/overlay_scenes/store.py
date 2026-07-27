"""Persistence helpers for Overlay Scenes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION
from .models import Channel, Layer, LifetimeSpec


class LayerStore:
    """Persist configured and active layer state."""

    def __init__(self, hass: HomeAssistant) -> None:
        coordinator = hass.data.get(f"{DOMAIN}_store")
        if coordinator is None:
            coordinator = {
                "store": Store(hass, STORAGE_VERSION, STORAGE_KEY),
                "lock": asyncio.Lock(),
                "data": None,
            }
            hass.data[f"{DOMAIN}_store"] = coordinator
        self._coordinator = coordinator

    async def async_load(self) -> dict[str, Any]:
        """Load stored state."""
        async with self._coordinator["lock"]:
            return await self._async_load_locked()

    async def _async_load_locked(self) -> dict[str, Any]:
        if self._coordinator["data"] is None:
            self._coordinator["data"] = (
                await self._coordinator["store"].async_load() or {"active": []}
            )
        return self._coordinator["data"]

    async def async_save(
        self, overlay_set_id: str, records: list[dict[str, Any]]
    ) -> None:
        """Persist one set without discarding other Overlay Sets."""
        async with self._coordinator["lock"]:
            current = await self._async_load_locked()
            retained = [
                record
                for record in current.get("active", [])
                if record.get("layer", {}).get("overlay_set_id") != overlay_set_id
            ]
            updated = {"active": retained + records}
            await self._coordinator["store"].async_save(updated)
            self._coordinator["data"] = updated


def serialize_active(
    layer: Layer,
    channel: Channel,
    expires_at: datetime | None,
    *,
    base_value: Any,
) -> dict[str, Any]:
    """Serialize one active `(layer, channel)` pair."""
    return {
        "layer": serialize_layer(layer),
        "channel": channel.key,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "base_value": base_value,
    }


def serialize_layer(layer: Layer) -> dict[str, Any]:
    """Serialize a layer."""
    return {
        "id": layer.id,
        "overlay_set_id": layer.overlay_set_id,
        "role": str(layer.role),
        "priority": layer.priority,
        "channels": [channel.key for channel in layer.channels],
        "value": str(layer.value) if hasattr(layer.value, "async_render") else layer.value,
        "op": layer.op,
        "opacity": layer.opacity,
        "lifetime": {
            "mode": str(layer.lifetime.mode),
            "duration": layer.lifetime.duration.total_seconds() if layer.lifetime.duration else None,
            "condition_entity": layer.lifetime.condition_entity,
        },
    }


def deserialize_layer(data: dict[str, Any]) -> Layer:
    """Deserialize a stored layer."""
    lifetime = data["lifetime"]
    return Layer(
        id=data["id"],
        overlay_set_id=data["overlay_set_id"],
        role=data["role"],
        priority=data.get("priority", 0),
        channels=[Channel.from_key(key) for key in data["channels"]],
        value=data["value"],
        op=data.get("op", "override"),
        opacity=data.get("opacity", 1.0),
        lifetime=LifetimeSpec(
            mode=lifetime["mode"],
            duration=timedelta(seconds=lifetime["duration"]) if lifetime.get("duration") else None,
            condition_entity=lifetime.get("condition_entity"),
        ),
    )


def parse_expiry(value: str | None) -> datetime | None:
    """Parse a persisted UTC expiry."""
    if not value:
        return None
    result = datetime.fromisoformat(value)
    return result.astimezone(UTC)
