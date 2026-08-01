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
    resolve_class_frame_geometry,
    validate_separated_promotions,
)

ROOT = Path(__file__).resolve().parents[1]
DWARF = ROOT / "assets" / "first-room" / "dwarf"
PROFILES = ROOT / "gate-controls" / "acceptance-profiles.json"
MANIFEST = ROOT / "gate-controls" / "manifest.json"
TOLERANCE = 0.002

C1_TABLE = {
    "idle": {
        "rgba": (0.4193, 0.2292, 0.3333),
        "alpha": (0.1289, 0.0623, 0.0664),
    },
    "walk": {
        "rgba": (0.3438, 0.2656, 0.2917),
        "alpha": (0.1472, 0.1582, 0.1401),
    },
    "swing": {
        "rgba": (0.3229, 0.2431, 0.2118),
        "alpha": (0.5422, 0.3777, 0.3114),
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
    """C1 characterization for polished-frame churn (#173).

    Walk rgba baselines moved in #177 when polished Frames were requantized onto
    the Master Palette; alpha churn is unchanged because alpha masks were preserved.
    """
    frames = _load_polished(motion)
    rgba_pairs = tuple(_rgba_churn(frames[i], frames[i + 1]) for i in range(len(frames) - 1))
    alpha_pairs = tuple(_alpha_churn(frames[i], frames[i + 1]) for i in range(len(frames) - 1))
    want = C1_TABLE[motion]
    assert rgba_pairs == pytest.approx(want["rgba"], abs=TOLERANCE)
    assert alpha_pairs == pytest.approx(want["alpha"], abs=TOLERANCE)
    if motion == "idle":
        assert max(rgba_pairs) > max(alpha_pairs)


def test_static_silhouette_pair_fraction_identical_and_disjoint() -> None:
    opaque = [[(1, 2, 3)]]
    transparent = [[None]]
    identical = [[(1, 2, 3), (4, 5, 6)], [(7, 8, 9), None]]
    full_opaque = [[(1, 2, 3)], [(4, 5, 6)]]
    full_transparent = [[None], [None]]
    assert S.static_silhouette_pair_fraction(identical, identical) == 1.0
    assert S.static_silhouette_pair_fraction(opaque, transparent) == 0.0
    assert S.static_silhouette_pair_fraction(full_opaque, full_transparent) == 0.0


def test_static_silhouette_pair_fraction_zero_union_returns_one() -> None:
    all_transparent = [[None, None], [None, None]]
    assert S.static_silhouette_pair_fraction(all_transparent, all_transparent) == 1.0


def test_static_silhouette_pair_fraction_normalizes_by_union_not_area() -> None:
    """C2: matches the union-normalized convention of cell_diff / silhouette_diff.

    Two Cells occupied only in `a`, one only in `b`: union_opaque = 3, all three
    differ in occupancy status relative to the other frame, so changed = 3 and
    the pair fraction is 0.0 regardless of the surrounding canvas area.
    """
    a = [[(1, 1, 1), (2, 2, 2), None, None]]
    b = [[None, None, (3, 3, 3), None]]
    assert S.static_silhouette_pair_fraction(a, b) == 0.0


def test_static_silhouette_pair_fraction_disjoint_opaque_regions_partial() -> None:
    # union_opaque = 3 (columns 0,1,2), changed = 2 (columns 0,1 flip), column 2
    # matches (opaque in both) -> 1 - 2/3 = 0.3333
    a = [[(1, 1, 1), (2, 2, 2), (3, 3, 3), None]]
    b = [[None, None, (3, 3, 3), None]]
    assert S.static_silhouette_pair_fraction(a, b) == pytest.approx(0.3333, abs=TOLERANCE)


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


def _embed_in_wider_canvas(
    frames: list[list[list[S.Cell]]], *, canvas_w: int, left_pad: int
) -> list[list[list[S.Cell]]]:
    frame_h = len(frames[0])
    out = []
    for frame in frames:
        canvas: list[list[S.Cell]] = [[None] * canvas_w for _ in range(frame_h)]
        for y, row in enumerate(frame):
            for x, cell in enumerate(row):
                canvas[y][left_pad + x] = cell
        out.append(canvas)
    return out


def test_static_silhouette_adjacent_max_is_canvas_invariant() -> None:
    """C1/C6: re-canvassing at a wider width and fixed column offset must not
    change static_silhouette_adjacent_max — no pixel of motion changed."""
    frames = _load_polished("swing")
    native_max = S.static_silhouette_adjacent_max(frames)
    swing_geometry = resolve_class_frame_geometry("swing")
    origin_x, _ = swing_geometry.canonical_origin
    anchor_w = S.DEFAULT_LAYOUT.frame_w
    anchor_frames = [
        [row[origin_x : origin_x + anchor_w] for row in frame] for frame in frames
    ]
    wide_16 = _embed_in_wider_canvas(
        anchor_frames,
        canvas_w=swing_geometry.frame_w,
        left_pad=origin_x,
    )
    wide_32 = _embed_in_wider_canvas(anchor_frames, canvas_w=32, left_pad=origin_x * 2)
    assert S.static_silhouette_adjacent_max(wide_16) == pytest.approx(native_max, abs=TOLERANCE)
    assert S.static_silhouette_adjacent_max(wide_32) == pytest.approx(native_max, abs=TOLERANCE)


def test_swing_profile_registers_unseparated_budget() -> None:
    doc = json.loads(PROFILES.read_text())
    gate = doc["profiles"]["swing"]["gates"]["static_silhouette_pass"]
    assert gate["status"] == "UNSEPARATED"
    assert gate["budget"] == 0.88
    assert "hard_fail" not in gate
    assert "active_promotion" not in gate

    policy = build_runtime_acceptance_policy(
        profiles_path=PROFILES,
        manifest_path=MANIFEST,
    )
    assert policy.for_class("swing").max_static_silhouette == 0.88


def test_unseparated_static_silhouette_boundary_and_review() -> None:
    policy = GatePolicy(status="UNSEPARATED", budget=0.88, hard_fail=None)
    assert evaluate_continuous_gate_outcome(policy, 0.88) == "PASS"
    assert evaluate_continuous_gate_outcome(policy, 0.95) == "REVIEW"


def test_reference_swing_polished_per_pair_table() -> None:
    """C1/C4: union-normalized per-pair table for the production reference.

    Re-canvassing the same reference Frames at 16x24, 24x24, and 32x24 scores
    0.4578/0.6223/0.6886 under union normalization on every canvas (C1) — this
    is the 16x24 shipped-Frame row of that table.
    """
    frames = _load_polished("swing")
    pairs = [
        S.static_silhouette_pair_fraction(frames[i], frames[i + 1])
        for i in range(len(frames) - 1)
    ]
    assert pairs == pytest.approx((0.4578, 0.6223, 0.6886), abs=TOLERANCE)
    assert round(max(pairs), 2) == 0.69
    policy = GatePolicy(status="UNSEPARATED", budget=0.88, hard_fail=None)
    assert evaluate_continuous_gate_outcome(policy, max(pairs)) == "PASS"


def test_cell_authored_swing_prototype_matches_production_after_identity_lock() -> None:
    """C4 separation table, re-derived (issue #208 wants fresh measurement, not
    the issue's own table carried verbatim — see C5's derivation rule).

    The provider Strip this test measures predates the #178 palette-exact
    migration's alpha-mask contract: Polished Frames now share the Draft alpha
    mask exactly (`docs/strip-acquisition-contract.md` § final polish, point 2),
    and this metric is alpha-only. So the provider and the Polished reference
    now measure identically — both PASS at 0.88, not the 0.93 REVIEW the issue's
    table describes. `test_swing_hold_pose_trips_static_silhouette`
    (`tests/test_adversarial.py`) remains the REVIEW evidence for this budget.
    """
    layout = S.DEFAULT_LAYOUT
    provider = S.load_provider_frames(
        DWARF / "swing" / "provider" / "source.png",
        S.provider_probe_layout(layout),
    )
    pairs = [
        S.static_silhouette_pair_fraction(provider[i], provider[i + 1])
        for i in range(len(provider) - 1)
    ]
    assert pairs == pytest.approx((0.4578, 0.6223, 0.6886), abs=TOLERANCE)
    assert round(max(pairs), 2) == 0.69
    result = S.coherence_split(provider, motion_class="swing")
    gate = result["gate_outcomes"]["static_silhouette_pass"]
    assert gate["outcome"] == "PASS"
    assert gate["metric"] == pytest.approx(0.6886, abs=TOLERANCE)


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
