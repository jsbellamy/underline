"""static_silhouette_pass metric and registration (issue #173)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import strip as S
from pipeline.final_polish import _load_frame_sequence
from pipeline.strip import (
    GatePolicy,
    build_runtime_acceptance_policy,
    evaluate_continuous_gate_outcome,
    validate_separated_promotions,
)

ROOT = Path(__file__).resolve().parents[1]
DWARF = ROOT / "assets" / "first-room" / "dwarf"
PROFILES = ROOT / "gate-controls" / "acceptance-profiles.json"
MANIFEST = ROOT / "gate-controls" / "manifest.json"
TOLERANCE = 0.002

C1_TABLE = {
    "idle": {
        "rgba": (0.7422, 0.6979, 0.7005),
        "alpha": (0.0964, 0.0443, 0.0469),
    },
    "walk": {
        "rgba": (0.4245, 0.4115, 0.4089),
        "alpha": (0.0625, 0.0651, 0.0573),
    },
    "swing": {
        "rgba": (0.5859, 0.4896, 0.4349),
        "alpha": (0.3177, 0.1851, 0.1354),
    },
}


def _rgba_churn(a: list[list[S.Cell]], b: list[list[S.Cell]]) -> float:
    frame_h = len(a)
    frame_w = len(a[0])
    total = frame_w * frame_h
    changed = sum(1 for y in range(frame_h) for x in range(frame_w) if a[y][x] != b[y][x])
    return round(changed / total, 4)


def _alpha_churn(a: list[list[S.Cell]], b: list[list[S.Cell]]) -> float:
    return round(1.0 - S.static_silhouette_pair_fraction(a, b), 4)


def _load_polished(motion: str) -> list[list[list[S.Cell]]]:
    return _load_frame_sequence(DWARF / motion, "polished")


@pytest.mark.parametrize("motion", ["idle", "walk", "swing"])
def test_rgba_churn_anti_correlates_with_alpha_on_polished_frames(motion: str) -> None:
    frames = _load_polished(motion)
    rgba_pairs = tuple(_rgba_churn(frames[i], frames[i + 1]) for i in range(len(frames) - 1))
    alpha_pairs = tuple(_alpha_churn(frames[i], frames[i + 1]) for i in range(len(frames) - 1))
    want = C1_TABLE[motion]
    assert rgba_pairs == pytest.approx(want["rgba"], abs=TOLERANCE)
    assert alpha_pairs == pytest.approx(want["alpha"], abs=TOLERANCE)
    if motion == "idle":
        assert max(rgba_pairs) > max(C1_TABLE["swing"]["rgba"])


def test_static_silhouette_pair_fraction_identical_and_disjoint() -> None:
    opaque = [[(1, 2, 3)]]
    transparent = [[None]]
    identical = [[(1, 2, 3), (4, 5, 6)], [(7, 8, 9), None]]
    full_opaque = [[(1, 2, 3)], [(4, 5, 6)]]
    full_transparent = [[None], [None]]
    assert S.static_silhouette_pair_fraction(identical, identical) == 1.0
    assert S.static_silhouette_pair_fraction(opaque, transparent) == 0.0
    assert S.static_silhouette_pair_fraction(full_opaque, full_transparent) == 0.0


def test_static_silhouette_adjacent_max_uses_stillest_transition() -> None:
    frames = [
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
        [[None, (3, 3, 3)], [(4, 4, 4), None]],
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
    ]
    pair_fracs = [
        S.static_silhouette_pair_fraction(frames[i], frames[i + 1]) for i in range(3)
    ]
    assert S.static_silhouette_adjacent_max(frames) == max(pair_fracs)


def test_swing_profile_registers_unseparated_budget() -> None:
    doc = json.loads(PROFILES.read_text())
    gate = doc["profiles"]["swing"]["gates"]["static_silhouette_pass"]
    assert gate["status"] == "UNSEPARATED"
    assert gate["budget"] == 0.86
    assert "hard_fail" not in gate
    assert "active_promotion" not in gate

    policy = build_runtime_acceptance_policy(
        profiles_path=PROFILES,
        manifest_path=MANIFEST,
    )
    assert policy.for_class("swing").max_static_silhouette == 0.86


def test_unseparated_static_silhouette_boundary_and_review() -> None:
    policy = GatePolicy(status="UNSEPARATED", budget=0.86, hard_fail=None)
    assert evaluate_continuous_gate_outcome(policy, 0.86) == "PASS"
    assert evaluate_continuous_gate_outcome(policy, 0.95) == "REVIEW"


def test_reference_swing_polished_per_pair_table() -> None:
    frames = _load_polished("swing")
    pairs = [
        S.static_silhouette_pair_fraction(frames[i], frames[i + 1])
        for i in range(len(frames) - 1)
    ]
    assert pairs == pytest.approx((0.6823, 0.8151, 0.8646), abs=TOLERANCE)
    assert round(max(pairs), 2) == 0.86
    policy = GatePolicy(status="UNSEPARATED", budget=0.86, hard_fail=None)
    assert evaluate_continuous_gate_outcome(policy, 0.86) == "PASS"


def test_cell_authored_swing_prototype_yields_review() -> None:
    layout = S.DEFAULT_LAYOUT
    provider = S.load_provider_frames(
        DWARF / "swing" / "provider" / "source.png",
        S.provider_probe_layout(layout),
    )
    pairs = [
        S.static_silhouette_pair_fraction(provider[i], provider[i + 1])
        for i in range(len(provider) - 1)
    ]
    assert pairs == pytest.approx((0.8227, 0.8968, 0.9244), abs=TOLERANCE)
    assert round(max(pairs), 2) == 0.92
    result = S.coherence_split(provider, motion_class="swing")
    gate = result["gate_outcomes"]["static_silhouette_pass"]
    assert gate["outcome"] == "REVIEW"
    assert gate["metric"] > 0.86


def test_validate_separated_promotions_requires_no_promotion_for_static_silhouette() -> None:
    policy = build_runtime_acceptance_policy(
        profiles_path=PROFILES,
        manifest_path=MANIFEST,
    )
    validate_separated_promotions(policy.acceptance_gates, manifest_path=MANIFEST)


def test_walk_and_idle_polished_are_inapplicable() -> None:
    for motion in ("idle", "walk"):
        frames = _load_polished(motion)
        result = S.coherence_split(frames, motion_class=motion)
        assert "static_silhouette_pass" not in result["gate_outcomes"]
