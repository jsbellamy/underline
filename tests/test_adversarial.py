"""Adversarial gate checks using corpus adversarial helpers."""

from __future__ import annotations

import adversarial
import pytest
from pipeline import strip as S

ALL_CLASSES = tuple(adversarial.CLASS_BASELINES)
MUTATION_CASES = [
    (motion_class, mutation)
    for motion_class, mutations in adversarial.MUST_FAIL.items()
    for mutation in sorted(mutations)
]
STRIP_GAP_CASES = [
    (strip_id, mutation)
    for strip_id, gaps in adversarial.STRIP_GAPS.items()
    for mutation in gaps
]


@pytest.mark.parametrize("motion_class", ALL_CLASSES)
def test_untouched_passes_per_class(motion_class: str) -> None:
    frames = adversarial.real_frames(motion_class)
    result = S.coherence_split(frames, motion_class=motion_class)
    want = adversarial.BASELINE_OUTCOME.get(motion_class, "PASS")
    assert result["outcome"] == want
    if motion_class == "swing":
        assert result["gate_outcomes"]["static_silhouette_pass"]["outcome"] == "PASS"


@pytest.mark.parametrize("motion_class,mutation", MUTATION_CASES)
def test_required_mutation_not_automatically_accepted(
    motion_class: str, mutation: str
) -> None:
    frames = adversarial.real_frames(motion_class)
    mutated = adversarial.mutate(motion_class, mutation, frames)
    result = S.coherence_split(mutated, motion_class=motion_class)
    assert result["outcome"] != "PASS"


def test_swing_hold_pose_trips_static_silhouette() -> None:
    frames = adversarial.real_frames("swing")
    mutated = adversarial.hold_pose(frames)
    result = S.coherence_split(mutated, motion_class="swing")
    assert result["outcome"] == "REVIEW"
    gate = result["gate_outcomes"]["static_silhouette_pass"]
    assert gate["outcome"] == "REVIEW"
    assert gate["metric"] == 1.0


def test_blob_idle_slide_review_or_fail() -> None:
    frames = adversarial.real_frames("blob_idle")
    mutated = adversarial.mutate("blob_idle", "slide", frames)
    result = S.coherence_split(mutated, motion_class="blob_idle")
    assert result["outcome"] in ("REVIEW", "FAIL")
    assert result["gate_outcomes"]["silhouette_budget"]["outcome"] in ("REVIEW", "FAIL")


def test_emissive_mirror_review_or_fail() -> None:
    frames = adversarial.real_frames("emissive")
    mutated = adversarial.mutate("emissive", "wrong_pose", frames)
    result = S.coherence_split(mutated, motion_class="emissive")
    assert result["outcome"] in ("REVIEW", "FAIL")
    assert result["gate_outcomes"]["loop_closure_pass"]["outcome"] == "REVIEW"


def test_idle_recolour_fails_hard() -> None:
    frames = adversarial.real_frames("idle")
    mutated = adversarial.recolour(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["outcome"] == "FAIL"


def test_idle_mirror_review_not_pass() -> None:
    frames = adversarial.real_frames("idle")
    mutated = adversarial.wrong_pose(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["outcome"] == "REVIEW"
    assert result["gate_outcomes"]["silhouette_budget"]["outcome"] == "REVIEW"


@pytest.mark.parametrize("strip_id,mutation", STRIP_GAP_CASES)
def test_strip_gap_passes_ungated(strip_id: str, mutation: str) -> None:
    """Documented per-strip holes — mutation still passes; closing a gate forces removal."""
    motion_class = adversarial.motion_class_for_strip(strip_id)
    frames = adversarial.frames_for_strip(strip_id)
    mutated = adversarial._MUTATORS[mutation](frames)
    result = S.coherence_split(mutated, motion_class=motion_class)
    assert result["outcome"] == "PASS"


def test_strip_gaps_04_displacement_undecidable() -> None:
    assert adversarial.STRIP_GAPS["04-bat-flap"].keys() == {"hop", "slide"}
    assert "degenerate alignment" in adversarial.STRIP_GAPS["04-bat-flap"]["hop"]


def test_known_gaps_empty() -> None:
    assert adversarial.KNOWN_GAPS == {}


def test_adversarial_report_prints_exactly_two_gaps(capsys) -> None:
    adversarial.main()
    captured = capsys.readouterr()
    gap_lines = [line for line in captured.out.splitlines() if line.startswith("GAP")]
    assert len(gap_lines) == 2
    assert all("04-bat-flap" in line or "airborne" in line for line in gap_lines)
