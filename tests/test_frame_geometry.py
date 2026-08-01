"""Per-class Frame geometry resolver and DEFAULT_LAYOUT equivalence (issue #209)."""

from __future__ import annotations

import pytest

from pipeline.strip import (
    DEFAULT_LAYOUT,
    MOTION_CLASSES,
    layout_for_motion_class,
    resolve_class_frame_geometry,
)


_EXPECTED_GEOMETRY: dict[str, tuple[int, int, tuple[int, int]]] = {
    "swing": (24, 24, (4, 0)),
}
_DEFAULT_GEOMETRY = (16, 24, (0, 0))


@pytest.mark.parametrize("motion_class", sorted(MOTION_CLASSES))
def test_every_motion_class_resolves_frame_geometry(motion_class: str) -> None:
    expected_w, expected_h, expected_origin = _EXPECTED_GEOMETRY.get(
        motion_class,
        _DEFAULT_GEOMETRY,
    )
    geometry = resolve_class_frame_geometry(motion_class)
    assert geometry.frame_w == expected_w
    assert geometry.frame_h == expected_h
    assert geometry.canonical_origin == expected_origin


@pytest.mark.parametrize(
    "motion_class",
    sorted(motion_class for motion_class in MOTION_CLASSES if motion_class != "swing"),
)
def test_non_swing_layout_matches_global_default_layout(motion_class: str) -> None:
    per_class = layout_for_motion_class(motion_class)
    assert per_class.frame_w == DEFAULT_LAYOUT.frame_w
    assert per_class.frame_h == DEFAULT_LAYOUT.frame_h
    assert per_class.frame_count == DEFAULT_LAYOUT.frame_count
    assert per_class.gutter == DEFAULT_LAYOUT.gutter
    assert per_class.pitch_px == DEFAULT_LAYOUT.pitch_px
    assert per_class.margin_cells == DEFAULT_LAYOUT.margin_cells
    assert per_class.grounded == DEFAULT_LAYOUT.grounded


def test_swing_layout_uses_wider_frame_width() -> None:
    swing = layout_for_motion_class("swing")
    assert swing.frame_w == 24
    assert swing.frame_h == DEFAULT_LAYOUT.frame_h
    assert swing.frame_count == DEFAULT_LAYOUT.frame_count
    assert swing.gutter == DEFAULT_LAYOUT.gutter
