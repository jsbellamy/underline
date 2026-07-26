"""Adversarial gate checks using prototype/strip-coherence/adversarial helpers."""

from __future__ import annotations

import adversarial
import strip as S


def test_untouched_real_strip_passes() -> None:
    frames = adversarial.real_frames()
    result = S.coherence_split(frames, motion_class="idle")
    assert result["pass"] is True


def test_recolour_fails() -> None:
    frames = adversarial.real_frames()
    mutated = adversarial.recolour(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["pass"] is False


def test_hop_fails() -> None:
    frames = adversarial.real_frames()
    mutated = adversarial.hop(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["pass"] is False


def test_wrong_pose_fails() -> None:
    frames = adversarial.real_frames()
    mutated = adversarial.wrong_pose(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["pass"] is False


def test_slide_fails() -> None:
    frames = adversarial.real_frames()
    mutated = adversarial.slide(frames)
    result = S.coherence_split(mutated, motion_class="idle")
    assert result["pass"] is False
