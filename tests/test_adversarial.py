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


def test_airborne_silhouette_mutations_have_no_budget() -> None:
    """Airborne has max_silhouette=None — hop/mirror/slide are not gated today."""
    frames = adversarial.real_frames("airborne")
    for mutate in (adversarial.hop, adversarial.wrong_pose, adversarial.slide):
        result = S.coherence_split(mutate(frames), motion_class="airborne")
        assert result.get("silhouette_budget") is None
