"""Tests for antisymmetric displacement tamper detection."""

from __future__ import annotations

import json
import pathlib

import adversarial
import corpus
from pipeline import strip as S

INBOX = (
    pathlib.Path(__file__).resolve().parents[1]
    / "prototype"
    / "strip-coherence"
    / "inbox"
)
LAYOUT = S.StripLayout(
    frame_w=S.DEFAULT_LAYOUT.frame_w,
    frame_h=S.DEFAULT_LAYOUT.frame_h,
    frame_count=S.DEFAULT_LAYOUT.frame_count,
    gutter=S.DEFAULT_LAYOUT.gutter,
    pitch_px=S.DEFAULT_LAYOUT.pitch_px,
    margin_cells=0,
)


def _load_frames(sample_id: str):
    path = corpus.find_png(sample_id)
    assert path is not None
    cells, _ = S.recover_strip_cells(path, LAYOUT)
    return S.slice_frames_pitch(cells, frame_count=LAYOUT.frame_count)[0]


def _coherence(frames, motion_class: str = "airborne"):
    return S.coherence_split(frames, motion_class=motion_class)


def test_registration_and_displacement_spans_differ() -> None:
    assert S.REGISTRATION_SPAN == 1
    assert S.DISPLACEMENT_PROBE_SPAN == 4
    assert S.DISPLACEMENT_PROBE_SPAN > S.REGISTRATION_SPAN
    assert S.DISPLACEMENT_PAIR_TOLERANCE == 1
    assert S.MIN_ALIGNMENT_SHARPNESS_AIRBORNE == 0.015


def test_shifts_antisymmetric_exact_and_tolerance() -> None:
    assert S.shifts_antisymmetric(0, -2, 0, 2)
    assert S.shifts_antisymmetric(3, 1, -3, -1)
    assert S.shifts_antisymmetric(3, 1, -2, -1, tolerance=1)
    assert not S.shifts_antisymmetric(3, 1, -1, 0, tolerance=1)


def test_bat_flap_sharpness_degenerate_at_loop_closure() -> None:
    frames = _load_frames("04-bat-flap")
    q, anchor = S.quantize_motion_frames(frames, "airborne")
    report = S.alignment_sharpness_report(q, loops=True, anchor=anchor)
    assert report["min_margin"] == 0.0
    assert report["worst_pair"] == [3, 0]


def test_bat_flap_displacement_inapplicable() -> None:
    frames = adversarial.real_frames("airborne")
    coh = _coherence(frames)
    assert coh["displacement_pass"] is None
    assert coh["displacement_inapplicable"] is True
    assert "3→0" in coh["displacement_reason"]
    assert coh["pass"] is True


def test_moth_flap_displacement_applicable_and_clean() -> None:
    frames = _load_frames("16-moth-flap")
    coh = _coherence(frames)
    assert coh["displacement_pass"] is True
    assert not coh["displacement_inapplicable"]
    sharp = coh["alignment_sharpness"]
    assert sharp["min_margin"] >= S.MIN_ALIGNMENT_SHARPNESS_AIRBORNE


def test_moth_flap_hop_fails_displacement_gate() -> None:
    frames = _load_frames("16-moth-flap")
    mutated = adversarial.hop(frames)
    coh = _coherence(mutated)
    assert coh["displacement_pass"] is False
    assert coh["pass"] is False


def test_wisp_float_slide_fails_displacement_gate() -> None:
    frames = _load_frames("17-wisp-float")
    mutated = adversarial.slide(frames)
    coh = _coherence(mutated)
    assert coh["displacement_pass"] is False


def test_airborne_mirror_invisible_to_displacement() -> None:
    base = _load_frames("16-moth-flap")
    mirror = adversarial.wrong_pose(base)
    q, anchor = S.quantize_motion_frames(mirror, "airborne")
    assert not S.antisymmetric_displacement_flags(q, loops=True, anchor=anchor)


def test_swing_clean_large_shift_without_return_pair() -> None:
    base = adversarial.real_frames("swing")
    q, anchor = S.quantize_motion_frames(base, "swing")
    assert not S.antisymmetric_displacement_flags(q, loops=False, anchor=anchor)


def test_facing_class_property() -> None:
    assert S.MOTION_CLASSES["walk"].facing == "fixed"
    assert S.MOTION_CLASSES["swing"].facing == "fixed"
    assert S.MOTION_CLASSES["airborne"].facing == "free"
    assert S.MOTION_CLASSES["blob_idle"].facing == "free"


def test_airborne_good_corpus_displacement_falsification() -> None:
    """Applicable airborne strips must pass; inapplicable must report None."""
    manifest = json.loads(
        (
            pathlib.Path(__file__).resolve().parents[1]
            / "prototype/strip-coherence/prompts/manifest.json"
        ).read_text()
    )
    for sample in manifest["samples"]:
        if sample.get("contract_expect") != "PASS":
            continue
        if sample["motion_class"] != "airborne":
            continue
        frames = _load_frames(sample["id"])
        coh = _coherence(frames)
        if sample["id"] == "04-bat-flap":
            assert coh["displacement_pass"] is None
            assert coh["displacement_inapplicable"]
        else:
            assert coh["displacement_pass"] is True
            assert not coh["displacement_inapplicable"]
