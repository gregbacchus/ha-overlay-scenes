"""Tests for every compositor operation."""

from custom_components.overlay_scenes.compositor import apply_op


def test_numeric_ops() -> None:
    assert apply_op("override", 10, 20, 0.5) == 15
    assert apply_op("add", 10, 3) == 13
    assert apply_op("clamp_min", 5, 10) == 10
    assert apply_op("clamp_max", 15, 10) == 10
    assert apply_op("average", 10, 20) == 15


def test_boolean_ops() -> None:
    assert apply_op("override", False, True) is True
    assert apply_op("or", False, True) is True
    assert apply_op("and", True, False) is False
    assert apply_op("nand", True, True) is False
    assert apply_op("nor", False, False) is True
    assert apply_op("xor", True, False) is True
    assert apply_op("xnor", True, True) is True


def test_color_ops() -> None:
    assert apply_op("override", (0, 0, 0), (100, 200, 50), 0.5) == (50, 100, 25)
    assert apply_op("multiply", (255, 128, 0), (128, 255, 255)) == (128, 128, 0)
    assert apply_op("screen", (0, 128, 255), (128, 128, 0)) == (128, 192, 255)
