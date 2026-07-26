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


@pytest.mark.parametrize(
    "motion_class,mutation",
    [
        (motion_class, mutation)
        for motion_class, gaps in adversarial.KNOWN_GAPS.items()
        for mutation in gaps
    ],
)
def test_known_gap_passes_ungated(motion_class: str, mutation: str) -> None:
    """Documented holes — mutation passes; do not treat as covered."""
    frames = adversarial.real_frames(motion_class)
    mutated = adversarial._MUTATORS[mutation](frames)
    result = S.coherence_split(mutated, motion_class=motion_class)
    assert result["pass"] is True


def test_strip_gaps_04_displacement_undecidable() -> None:
    assert adversarial.STRIP_GAPS["04-bat-flap"].keys() == {"hop", "slide"}
    assert "degenerate alignment" in adversarial.STRIP_GAPS["04-bat-flap"]["hop"]


def test_airborne_hop_on_04_still_ungated_via_strip_gap() -> None:
    frames = adversarial.real_frames("airborne")
    mutated = adversarial.hop(frames)
    result = S.coherence_split(mutated, motion_class="airborne")
    assert result["displacement_pass"] is None
    assert result["pass"] is True
