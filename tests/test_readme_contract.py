"""Reader-facing README contract checks."""

from pathlib import Path


README = (Path(__file__).parents[1] / "README.md").read_text()
NORMALIZED_README = " ".join(README.split())


def test_readme_uses_picker_backed_action_targets() -> None:
    """Document the picker-backed automation action contract."""
    assert "config_entry_id:" in README
    assert "layer_entity_id:" in README
    assert "data:\n    layer_id:" not in README


def test_readme_uses_one_duration_format() -> None:
    """Keep configured and per-activation duration examples consistent."""
    assert "Duration in seconds" not in README
    assert "Duration: 00:01:00" in README
    assert 'duration_override: "00:02:30"' in README


def test_readme_warns_against_overlapping_sets() -> None:
    """Prevent independent compositors from being presented as one registry."""
    assert "A channel should normally be owned by one Overlay Set" in NORMALIZED_README
    assert "Separate sets have independent compositors" in NORMALIZED_README
