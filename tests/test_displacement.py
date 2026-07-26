"""Tests for antisymmetric displacement tamper detection."""

from __future__ import annotations

import adversarial
import strip as S


def _quantize(motion_class: str, frames):
    return S.quantize_motion_frames(frames, motion_class)


def _flags(motion_class: str, frames):
    q, anchor = _quantize(motion_class, frames)
    loops = motion_class == "airborne"
    return S.antisymmetric_displacement_flags(q, loops=loops, anchor=anchor)


def test_registration_and_displacement_spans_differ() -> None:
    assert S.REGISTRATION_SPAN == 1
    assert S.DISPLACEMENT_PROBE_SPAN == 4
    assert S.DISPLACEMENT_PROBE_SPAN > S.REGISTRATION_SPAN
    assert S.DISPLACEMENT_PAIR_TOLERANCE == 1


def test_shifts_antisymmetric_exact_and_tolerance() -> None:
    assert S.shifts_antisymmetric(0, -2, 0, 2)
    assert S.shifts_antisymmetric(3, 1, -3, -1)
    assert S.shifts_antisymmetric(3, 1, -2, -1, tolerance=1)
    assert not S.shifts_antisymmetric(3, 1, -1, 0, tolerance=1)


def test_airborne_hop_triggers_antisymmetric_flag() -> None:
    base = adversarial.real_frames("airborne")
    mutated = adversarial.hop(base)
    flags = _flags("airborne", mutated)
    assert any(f["frame"] == 2 for f in flags)


def test_airborne_slide_triggers_antisymmetric_flag() -> None:
    base = adversarial.real_frames("airborne")
    mutated = adversarial.slide(base)
    flags = _flags("airborne", mutated)
    assert any(f["frame"] == 2 for f in flags)


def test_loops_scan_range() -> None:
    assert list(S.displacement_frame_indices(4, loops=True)) == [0, 1, 2, 3]
    assert list(S.displacement_frame_indices(4, loops=False)) == [1, 2]


def test_airborne_wraparound_scans_frame_zero() -> None:
    base = adversarial.real_frames("airborne")
    mutated = adversarial.hop(base, idx=0, dy=3)
    flags = _flags("airborne", mutated)
    assert 0 in S.displacement_frame_indices(4, loops=True)
    assert all(f["frame"] in range(4) for f in flags)


def test_airborne_mirror_invisible_to_displacement() -> None:
    base = adversarial.real_frames("airborne")
    clean_q, anchor = _quantize("airborne", base)
    mirror_q, _ = _quantize("airborne", adversarial.wrong_pose(base))
    clean_trans = S.adjacent_transition_shifts(clean_q, anchor=anchor)
    mirror_trans = S.adjacent_transition_shifts(mirror_q, anchor=anchor)
    assert clean_trans == mirror_trans
    assert not S.antisymmetric_displacement_flags(
        mirror_q, loops=True, anchor=anchor
    )


def test_airborne_clean_no_antisymmetric_flag() -> None:
    base = adversarial.real_frames("airborne")
    assert _flags("airborne", base) == []


def test_swing_clean_large_shift_without_return_pair() -> None:
    base = adversarial.real_frames("swing")
    q, anchor = _quantize("swing", base)
    transitions = S.adjacent_transition_shifts(q, anchor=anchor)
    assert any(t["magnitude"] >= 3 for t in transitions)
    assert not S.antisymmetric_displacement_flags(
        q, loops=False, anchor=anchor
    )


def test_facing_class_property() -> None:
    assert S.MOTION_CLASSES["walk"].facing == "fixed"
    assert S.MOTION_CLASSES["swing"].facing == "fixed"
    assert S.MOTION_CLASSES["airborne"].facing == "free"
    assert S.MOTION_CLASSES["blob_idle"].facing == "free"


def test_airborne_good_corpus_has_no_displacement_false_positives() -> None:
    """Falsification bar — airborne good strips only, loops=True."""
    import json
    import pathlib

    import corpus

    manifest = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[1]
            / "prototype/strip-coherence/prompts/manifest.json"
        ).read_text()
    )
    layout = S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=S.DEFAULT_LAYOUT.pitch_px,
        margin_cells=0,
    )
    for sample in manifest["samples"]:
        if sample.get("contract_expect") != "PASS":
            continue
        if sample["motion_class"] != "airborne":
            continue
        path = corpus.find_png(sample["id"])
        if path is None:
            continue
        cells, _ = S.recover_strip_cells(path, layout)
        frames, _ = S.slice_frames_pitch(cells, frame_count=layout.frame_count)
        q, anchor = S.quantize_motion_frames(frames, "airborne")
        flags = S.antisymmetric_displacement_flags(q, loops=True, anchor=anchor)
        assert flags == [], f"{sample['id']} falsely flagged: {flags}"
