"""Compatibility-safe cleanup of legacy Overlay Set devices."""

from __future__ import annotations

from typing import Protocol


class DeviceEntry(Protocol):
    """Minimum device entry contract used during cleanup."""

    id: str


class DeviceRegistry(Protocol):
    """Stable Home Assistant device-registry cleanup contract."""

    def async_get_device(
        self,
        identifiers: set[tuple[str, str]],
        connections: set[tuple[str, str]] | None = None,
    ) -> DeviceEntry | None:
        """Return a device matching its identifiers or connections."""

    def async_remove_device(self, device_id: str) -> None:
        """Remove a device by registry ID."""


def remove_legacy_overlay_set_device(
    device_registry: DeviceRegistry, domain: str, entry_id: str
) -> None:
    """Remove the redundant service device created by an earlier release."""
    legacy_device = device_registry.async_get_device(
        identifiers={(domain, entry_id)}
    )
    if legacy_device is not None:
        device_registry.async_remove_device(legacy_device.id)
