"""Recovery module export contract — vendored Nightglass primitives."""

from __future__ import annotations

import pathlib

import pipeline.recovery as recovery


def test_recovery_exports_exactly_seven_public_symbols() -> None:
    expected = {
        "MAGENTA",
        "MIN_GRID_SCORE",
        "key",
        "raw_gates",
        "raw_clipping",
        "detect_pitch",
        "sample_cells",
    }
    assert set(recovery.__all__) == expected


def test_recovery_constants_match_vendored_values() -> None:
    assert recovery.MAGENTA == (255, 0, 255)
    assert recovery.MIN_GRID_SCORE == 0.04


def test_recovery_provenance_docstring_records_nightglass_sha() -> None:
    doc = recovery.__doc__ or ""
    assert "nightglass/pipeline/acquire.py" in doc
    assert "7047b2a28565d28598a4420b8762c7f49b1898f5" in doc
    assert "re-vendored" in doc.lower() or "re-vendor" in doc.lower()


def test_key_is_public_not_underscore() -> None:
    assert callable(recovery.key)
    assert not hasattr(recovery, "_key")


def test_key_recovers_magenta_strip(tmp_path: pathlib.Path) -> None:
    from PIL import Image

    from pipeline.strip import DEFAULT_LAYOUT, render_logical_strip

    path = tmp_path / "strip.png"
    render_logical_strip(DEFAULT_LAYOUT, "pass").save(path)
    src, fg, bbox = recovery.key(path)
    assert src.size[0] > 0
    assert fg.shape == (src.size[1], src.size[0])
    assert len(bbox) == 4
