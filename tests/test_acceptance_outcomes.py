"""Gate-seam PASS / REVIEW / FAIL outcomes and runtime Acceptance policy (#62)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import strip as S
from pipeline.numeric_policy import canonical_metric
from pipeline.strip import GatePolicy, build_runtime_acceptance_policy, evaluate_continuous_gate_outcome

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ROOT / "gate-controls" / "acceptance-profiles.json"
MANIFEST = ROOT / "gate-controls" / "manifest.json"


def _idle_silhouette_policy() -> GatePolicy:
    return GatePolicy(status="SEPARATED", budget=0.2239, hard_fail=0.3, active_promotion="promo--idle--silhouette_budget")


def _idle_loop_policy() -> GatePolicy:
    return GatePolicy(status="UNSEPARATED", budget=0.3, hard_fail=None, active_promotion=None)


def test_canonical_metric_matches_production_and_prototype_imports() -> None:
    value = 0.2795
    from pipeline.numeric_policy import canonical_metric as production

    assert production(value) == 0.2795
    import sys

    sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))
    from numeric_policy import canonical_metric as prototype  # noqa: WPS433

    assert prototype(value) == production(value)


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        (0.20, "PASS"),
        (0.2239, "PASS"),
        (0.25, "REVIEW"),
        (0.3, "FAIL"),
        (0.35, "FAIL"),
    ],
)
def test_separated_gate_outcome_at_budget_and_hard_fail(metric: float, expected: str) -> None:
    policy = _idle_silhouette_policy()
    assert evaluate_continuous_gate_outcome(policy, metric) == expected


@pytest.mark.parametrize(
    ("metric", "expected"),
    [
        (0.29, "PASS"),
        (0.3, "PASS"),
        (0.31, "REVIEW"),
        (0.5, "REVIEW"),
    ],
)
def test_unseparated_gate_never_autonomous_fail(metric: float, expected: str) -> None:
    policy = _idle_loop_policy()
    assert evaluate_continuous_gate_outcome(policy, metric) == expected


def test_runtime_policy_projects_every_profile_budget() -> None:
    motion_classes, gate_policies = build_runtime_acceptance_policy(
        profiles_path=PROFILES,
        manifest_path=MANIFEST,
    )
    profiles = json.loads(PROFILES.read_text())["profiles"]
    gate_attr = {
        "silhouette_budget": "max_silhouette",
        "loop_closure_pass": "max_loop",
        "palette_drift_pass": "max_drift",
        "min_pair_cohort_pass": "max_min_pair",
    }
    for motion_class, profile in profiles.items():
        budget = motion_classes[motion_class]
        for gate_name, row in profile["gates"].items():
            if gate_name not in gate_attr:
                continue
            expected = row["budget"]
            if row["status"] == "INAPPLICABLE":
                assert getattr(budget, gate_attr[gate_name]) is None
            else:
                assert getattr(budget, gate_attr[gate_name]) == expected
            policy = gate_policies[motion_class][gate_name]
            assert policy.status == row["status"]
            assert policy.budget == expected
            assert policy.hard_fail == row.get("hard_fail")


def test_runtime_policy_rejects_non_active_separated_promotion(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    doc = json.loads(MANIFEST.read_text())
    for promo in doc["promotions"]:
        if promo["id"] == "promo--walk--loop_closure_pass":
            promo["status"] = "PENDING_VERIFICATION"
            break
    manifest_path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="not ACTIVE"):
        build_runtime_acceptance_policy(
            profiles_path=PROFILES,
            manifest_path=manifest_path,
        )


def test_runtime_policy_rejects_missing_separated_promotion(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    doc = json.loads(MANIFEST.read_text())
    doc["promotions"] = [
        promo for promo in doc["promotions"] if promo["id"] != "promo--walk--loop_closure_pass"
    ]
    manifest_path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="missing Promotion"):
        build_runtime_acceptance_policy(
            profiles_path=PROFILES,
            manifest_path=manifest_path,
        )


def test_recovery_failure_yields_structural_fail() -> None:
    path = ROOT / "prototype" / "strip-coherence" / "inbox" / "09-NEG-no-gutter.png"
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    with pytest.raises(ValueError):
        S.ingest_strip_provider(path, layout, motion_class="idle")


def test_runtime_policy_rejects_alternate_promotion_reference(tmp_path: Path) -> None:
    profiles_path = tmp_path / "acceptance-profiles.json"
    doc = json.loads(PROFILES.read_text())
    doc["profiles"]["walk"]["gates"]["loop_closure_pass"]["active_promotion"] = (
        "promo--walk--silhouette_budget"
    )
    profiles_path.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="alternate Promotion"):
        build_runtime_acceptance_policy(
            profiles_path=profiles_path,
            manifest_path=MANIFEST,
        )


def _solid_frame(rgb: tuple[int, int, int] = (100, 120, 80)) -> list[list[S.Cell]]:
    return [[rgb for _ in range(4)] for _ in range(6)]


def test_inapplicable_gates_omitted_from_gate_outcomes() -> None:
    frames = [_solid_frame() for _ in range(4)]
    coh = S.coherence_split(frames, motion_class="swing")
    outcomes = coh["gate_outcomes"]
    assert "loop_closure_pass" not in outcomes
    assert "min_pair_cohort_pass" not in outcomes
    assert coh["loop_closure_pass"] is None
    assert coh["min_pair_cohort_pass"] is None


def test_airborne_displacement_undecidable_records_caveat_without_gate_outcome() -> None:
    path = ROOT / "prototype" / "strip-coherence" / "inbox" / "04-bat-flap.png"
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    result = S.ingest_strip_provider(path, layout, motion_class="airborne")
    coh = result.coherence
    assert coh["displacement_pass"] is None
    assert "displacement_pass" not in coh["gate_outcomes"]
    assert any("undecidable" in caveat for caveat in coh["caveats"])
    assert coh["outcome"] == "PASS"
    assert result.pass_ is True


def test_airborne_displacement_false_yields_review_not_fail() -> None:
    import sys

    import adversarial
    import corpus

    sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))
    path = corpus.find_png("16-moth-flap")
    assert path is not None
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    cells, _ = S.recover_strip_cells(path, layout)
    frames = S.slice_frames_pitch(cells, frame_count=4)[0]
    assert frames is not None
    mutated = adversarial.hop(frames)
    coh = S.coherence_split(mutated, motion_class="airborne")
    disp = coh["gate_outcomes"]["displacement_pass"]
    assert disp["outcome"] == "REVIEW"
    assert coh["outcome"] == "REVIEW"
    assert coh["pass"] is False


def test_structural_dimension_mismatch_fails_over_review_band() -> None:
    small = _solid_frame((90, 100, 70))
    wide = [[cell for cell in row for _ in range(2)] for row in small]
    frames = [small, wide]
    coh = S.coherence_split(frames, motion_class="idle")
    assert coh["dimension_parity"] is False
    assert coh["outcome"] == "FAIL"
    assert coh["pass"] is False


def test_palette_drift_at_hard_fail_boundary_is_fail() -> None:
    path = ROOT / "prototype" / "strip-coherence" / "inbox" / "07-NEG-palette-drift.png"
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    result = S.ingest_strip_provider(path, layout, motion_class="idle")
    drift = result.coherence["gate_outcomes"]["palette_drift_pass"]
    assert drift["outcome"] == "FAIL"
    assert canonical_metric(result.coherence["worst_palette_drift"]) == drift["hard_fail"]
    assert result.coherence["outcome"] == "FAIL"
    assert result.pass_ is False


def test_unseparated_loop_above_budget_yields_review_without_autonomous_fail() -> None:
    assert evaluate_continuous_gate_outcome(_idle_loop_policy(), 0.31) == "REVIEW"
