"""Per-class Frame geometry resolver and DEFAULT_LAYOUT equivalence (issue #209)."""

from __future__ import annotations

import pytest

from pipeline.strip import (
    DEFAULT_LAYOUT,
    MOTION_CLASSES,
    layout_for_motion_class,
    resolve_class_frame_geometry,
)


@pytest.mark.parametrize("motion_class", sorted(MOTION_CLASSES))
def test_every_motion_class_keeps_the_release_frame_geometry(motion_class: str) -> None:
    geometry = resolve_class_frame_geometry(motion_class)
    assert geometry.frame_w == 16
    assert geometry.frame_h == 24
    assert geometry.canonical_origin == (0, 0)


@pytest.mark.parametrize("motion_class", sorted(MOTION_CLASSES))
def test_motion_class_layout_matches_global_default_layout(motion_class: str) -> None:
    per_class = layout_for_motion_class(motion_class)
    assert per_class.frame_w == DEFAULT_LAYOUT.frame_w
    assert per_class.frame_h == DEFAULT_LAYOUT.frame_h
    assert per_class.frame_count == DEFAULT_LAYOUT.frame_count
    assert per_class.gutter == DEFAULT_LAYOUT.gutter
    assert per_class.pitch_px == DEFAULT_LAYOUT.pitch_px
    assert per_class.margin_cells == DEFAULT_LAYOUT.margin_cells
    assert per_class.grounded == DEFAULT_LAYOUT.grounded
