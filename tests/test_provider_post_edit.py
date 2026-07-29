"""Provider post-edit integrity — magenta wipe + edit-source continuity."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.identity_lock import (
    MAGENTA_WIPE_MIN_PROVIDER_FRACTION,
    evaluate_edit_source_continuity,
    evaluate_provider_post_edit,
    exact_magenta_fraction,
    load_canonical_cells,
)
from pipeline.strip import DEFAULT_LAYOUT, StripLayout, canonicalize_frame, load_provider_frames

ROOT = Path(__file__).resolve().parents[1]
IDLE_PROVIDER = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
WALK_STRIP = ROOT / "prototype" / "strip-coherence" / "inbox" / "05-miner-walk.png"


def _layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _wipe_near_magenta_to_exact(src: Path, dest: Path) -> Path:
    image = Image.open(src).convert("RGBA")
    arr = np.asarray(image).copy()
    near = (
        (np.abs(arr[:, :, 0].astype(np.int16) - 255) <= 40)
        & (np.abs(arr[:, :, 1].astype(np.int16) - 0) <= 40)
        & (np.abs(arr[:, :, 2].astype(np.int16) - 255) <= 40)
    )
    arr[near] = (255, 0, 255, 255)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(dest)
    return dest


def test_idle_provider_has_negligible_exact_magenta() -> None:
    fraction = exact_magenta_fraction(IDLE_PROVIDER)
    assert fraction < 0.001


def test_magenta_wipe_of_idle_is_detected(tmp_path: Path) -> None:
    wiped = _wipe_near_magenta_to_exact(IDLE_PROVIDER, tmp_path / "wiped.png")
    assert exact_magenta_fraction(wiped) >= MAGENTA_WIPE_MIN_PROVIDER_FRACTION
    result = evaluate_provider_post_edit(
        wiped,
        IDLE_PROVIDER,
        motion_class="swing",
    )
    assert result.outcome == "FAIL"
    assert result.reason_code == "provider_magenta_wipe"
    assert result.magenta_wipe["provider_exact_fraction"] >= MAGENTA_WIPE_MIN_PROVIDER_FRACTION


def test_unmodified_idle_vs_itself_passes_post_edit() -> None:
    result = evaluate_provider_post_edit(
        IDLE_PROVIDER,
        IDLE_PROVIDER,
        motion_class="swing",
    )
    assert result.outcome == "PASS"
    assert result.reason_code is None


def test_edit_source_continuity_passes_for_idle_vs_itself() -> None:
    frames = load_provider_frames(IDLE_PROVIDER, _layout())
    assert frames is not None
    canonical = [
        canonicalize_frame(frame, frame_w=16, frame_h=24) for frame in frames
    ]
    result = evaluate_edit_source_continuity(canonical, canonical, "swing")
    assert result.outcome == "PASS"


def test_edit_source_continuity_fails_when_lock_cell_erased() -> None:
    frames = load_provider_frames(IDLE_PROVIDER, _layout())
    assert frames is not None
    edit_frames = [
        canonicalize_frame(frame, frame_w=16, frame_h=24) for frame in frames
    ]
    provider_frames = [[row[:] for row in frame] for frame in edit_frames]
    identity = load_canonical_cells(IDENTITY_PNG, (16, 24))
    erased = 0
    for y in range(1, 11):
        for x in range(5, 13):
            if identity[y][x] is None:
                continue
            for frame in provider_frames:
                frame[y][x] = None
            erased += 1
    assert erased >= 20
    result = evaluate_edit_source_continuity(provider_frames, edit_frames, "swing")
    assert result.outcome == "FAIL"
    assert result.reason_code == "edit_source_continuity_fail"


def test_corpus_walk_without_wipe_does_not_trip_magenta_gate() -> None:
    result = evaluate_provider_post_edit(
        WALK_STRIP,
        IDLE_PROVIDER,
        motion_class="walk",
    )
    # Continuity may fail (corpus walk ≠ idle seed), but magenta wipe must not fire.
    assert result.magenta_wipe["outcome"] == "PASS"
    assert result.reason_code != "provider_magenta_wipe"
