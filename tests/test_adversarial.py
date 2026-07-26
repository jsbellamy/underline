"""Adversarial gate checks using prototype/strip-coherence/adversarial helpers."""

from __future__ import annotations

import adversarial
import pytest
import strip as S

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
    assert result["pass"] is True


@pytest.mark.parametrize("motion_class,mutation", MUTATION_CASES)
def test_required_mutation_fails_per_class(motion_class: str, mutation: str) -> None:
    frames = adversarial.real_frames(motion_class)
    mutated = adversarial._MUTATORS[mutation](frames)
    result = S.coherence_split(mutated, motion_class=motion_class)
    assert result["pass"] is False


@pytest.mark.parametrize("strip_id,mutation", STRIP_GAP_CASES)
def test_strip_gap_passes_ungated(strip_id: str, mutation: str) -> None:
    """Documented per-strip holes — mutation still passes; closing a gate forces removal."""
    motion_class = adversarial.motion_class_for_strip(strip_id)
    frames = adversarial.frames_for_strip(strip_id)
    mutated = adversarial._MUTATORS[mutation](frames)
    result = S.coherence_split(mutated, motion_class=motion_class)
    assert result["pass"] is True


def test_strip_gaps_04_displacement_undecidable() -> None:
    assert adversarial.STRIP_GAPS["04-bat-flap"].keys() == {"hop", "slide"}
    assert "degenerate alignment" in adversarial.STRIP_GAPS["04-bat-flap"]["hop"]
