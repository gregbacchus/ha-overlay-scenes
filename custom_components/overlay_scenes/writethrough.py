"""Context-filtered writes to real Home Assistant entities."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_OFF
from homeassistant.core import Context, Event, HomeAssistant

from .const import PENDING_CONTEXT_TTL
from .models import Channel


class WriteThroughHandler:
    """Dispatch composite values and recognize the resulting state events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._pending_contexts: set[str] = set()
        self._expiry_handles: dict[str, asyncio.TimerHandle] = {}

    async def apply(self, channel: Channel, value: Any) -> None:
        """Write one resolved channel value."""
        await self.apply_many({channel: value})

    async def apply_many(self, values: dict[Channel, Any]) -> None:
        """Write resolved channels atomically per target entity."""
        by_entity: dict[str, dict[str, Any]] = defaultdict(dict)
        for channel, value in values.items():
            by_entity[channel.entity_id][channel.attribute] = value
        for entity_id, attributes in by_entity.items():
            await self._apply_entity(entity_id, attributes)

    async def _apply_entity(self, entity_id: str, values: dict[str, Any]) -> None:
        domain = entity_id.split(".", 1)[0]
        data: dict[str, Any] = {ATTR_ENTITY_ID: entity_id}
        if domain == "light":
            unsupported = set(values) - {"state", "brightness", "rgb_color"}
            if unsupported:
                raise ValueError(f"Unsupported light channels: {sorted(unsupported)}")
            if values.get("state") in (False, STATE_OFF, "off"):
                await self._call(domain, SERVICE_TURN_OFF, data)
                return
            service = SERVICE_TURN_ON
            if "brightness" in values:
                brightness = float(values["brightness"])
                if not 0 <= brightness <= 100:
                    raise ValueError("Light brightness percentage must be between 0 and 100")
                data["brightness_pct"] = brightness
            if "rgb_color" in values:
                data["rgb_color"] = values["rgb_color"]
        elif domain == "switch" and set(values) == {"state"}:
            service = (
                SERVICE_TURN_OFF
                if values["state"] in (False, STATE_OFF, "off")
                else SERVICE_TURN_ON
            )
        elif domain == "media_player" and set(values) == {"volume_level"}:
            service = "volume_set"
            data["volume_level"] = values["volume_level"]
        else:
            raise ValueError(f"Unsupported write-through channels: {entity_id} {sorted(values)}")

        await self._call(domain, service, data)

    async def _call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        context = Context()
        self._remember(context.id)
        await self.hass.services.async_call(domain, service, data, blocking=True, context=context)

    def should_ignore(self, event: Event) -> bool:
        """Return whether an event belongs to one of our recent writes."""
        context = event.context
        return bool(
            context
            and (context.id in self._pending_contexts or context.parent_id in self._pending_contexts)
        )

    def shutdown(self) -> None:
        """Cancel pending expiry callbacks."""
        for handle in self._expiry_handles.values():
            handle.cancel()
        self._expiry_handles.clear()
        self._pending_contexts.clear()

    def _remember(self, context_id: str) -> None:
        self._pending_contexts.add(context_id)
        if old := self._expiry_handles.pop(context_id, None):
            old.cancel()

        def forget() -> None:
            self._pending_contexts.discard(context_id)
            self._expiry_handles.pop(context_id, None)

        self._expiry_handles[context_id] = self.hass.loop.call_later(
            PENDING_CONTEXT_TTL, forget
        )
