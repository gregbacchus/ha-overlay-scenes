"""Lifecycle contract tests are exercised with Home Assistant's event loop."""

from datetime import timedelta

from custom_components.overlay_scenes.models import LifetimeSpec


def test_duration_spec_preserves_fractional_seconds() -> None:
    spec = LifetimeSpec(mode="duration", duration=timedelta(seconds=0.5))
    assert spec.duration.total_seconds() == 0.5
