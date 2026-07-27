"""α-Budget derivation — worked examples from issue #28."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))

from alpha_budgets import (  # noqa: E402
    ALPHA,
    _assert_runtime_equivalence,
    _load_acceptance_profiles,
    _promoted_controls,
    derive_separated_budget,
)
from numeric_policy import canonical_metric  # noqa: E402


def _run_alpha_budgets(gate_controls: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "UNDERLINE_GATE_CONTROLS_ROOT": str(gate_controls),
    }
    return subprocess.run(
        [sys.executable, str(ROOT / "prototype/strip-coherence/alpha_budgets.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_canonical_metric_preserves_exact_four_place_midpoint() -> None:
    # IEEE float makes 0.2795 * 10000 slightly above 2795; ceiling must stay 0.2795.
    assert canonical_metric(0.2795) == 0.2795


def test_derive_separated_budget_matches_issue_28_tightest_pairs() -> None:
    cases = [
        # (G, C, expected Budget) — from Choose alpha for separated Gate controls
        (0.3977, 0.4294, 0.4136),  # walk / silhouette_budget
        (0.1026, 0.1371, 0.1199),  # blob_idle / min_pair_cohort_pass
        (0.5652, 0.6067, 0.5860),  # swing / silhouette_budget
    ]
    for g, c, expected in cases:
        result = derive_separated_budget(g, c, alpha=ALPHA)
        assert result.budget == expected
        assert result.g == g
        assert result.c == c
        assert result.good_headroom == round(expected - g, 4)
        assert result.review_width == round(c - expected, 4)
        assert result.budget < result.c


def test_alpha_budgets_blocks_when_required_separated_promotion_not_active(
    tmp_path: pathlib.Path,
) -> None:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    manifest_path = gate_controls / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    for promo in doc["promotions"]:
        if promo["id"] == "promo--walk--loop_closure_pass":
            promo["status"] = "PENDING_VERIFICATION"
            break
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls)
    assert result.returncode != 0
    assert "not ACTIVE" in result.stdout + result.stderr
    assert "promo--walk--loop_closure_pass" in result.stdout + result.stderr


def test_alpha_budgets_blocks_when_profile_row_missing(
    tmp_path: pathlib.Path,
) -> None:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    del doc["profiles"]["walk"]["gates"]["loop_closure_pass"]
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls)
    assert result.returncode != 0
    assert "missing Acceptance status for walk/loop_closure_pass" in (
        result.stdout + result.stderr
    )


def test_promoted_controls_blocks_missing_promotion(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    manifest_path = gate_controls / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    doc["promotions"] = [
        promo
        for promo in doc["promotions"]
        if promo["id"] != "promo--walk--loop_closure_pass"
    ]
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    import alpha_budgets as ab

    monkeypatch.setattr(ab, "GC_MANIFEST", manifest_path)
    monkeypatch.setattr(
        ab, "ACCEPTANCE_PROFILES", gate_controls / "acceptance-profiles.json"
    )
    with pytest.raises(SystemExit, match="missing Promotion"):
        ab._promoted_controls()


def test_promoted_controls_blocks_mismatched_promotion_reference(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    doc["profiles"]["walk"]["gates"]["loop_closure_pass"]["active_promotion"] = (
        "promo--walk--silhouette_budget"
    )
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")
    import alpha_budgets as ab

    monkeypatch.setattr(ab, "ACCEPTANCE_PROFILES", profiles_path)
    monkeypatch.setattr(ab, "GC_MANIFEST", gate_controls / "manifest.json")
    with pytest.raises(SystemExit, match="mismatched Promotion"):
        ab._promoted_controls()


def test_promoted_controls_accepts_active_promotions() -> None:
    controls = _promoted_controls()
    assert controls[("walk", "loop_closure_pass")]["promotion"] == (
        "promo--walk--loop_closure_pass"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("budget", 9.9999),
        ("c", 9.9999),
    ],
)
def test_runtime_equivalence_blocks_derived_mismatch(field: str, value: float) -> None:
    profiles = _load_acceptance_profiles()
    separated_rows = [
        {
            "pair": "walk/silhouette_budget",
            "g": 0.3977,
            "c": 0.4294,
            "budget": 0.4136,
            "old": 0.4136,
            "delta": 0.0,
            "good_headroom": 0.0159,
            "review_width": 0.0158,
            "binding_good": "05-miner-walk",
            "control_attempt": "walk--silhouette_budget--002",
            "caveats": [],
        }
    ]
    separated_rows[0][field] = value
    with pytest.raises(SystemExit, match="runtime projection mismatch"):
        _assert_runtime_equivalence(profiles=profiles, separated_rows=separated_rows)


def test_runtime_equivalence_blocks_profile_status_mismatch() -> None:
    profiles = _load_acceptance_profiles()
    profiles = dict(profiles)
    profiles[("walk", "silhouette_budget")] = {
        **profiles[("walk", "silhouette_budget")],
        "status": "UNSEPARATED",
    }
    with pytest.raises(SystemExit, match="status profile='UNSEPARATED'"):
        _assert_runtime_equivalence(profiles=profiles, separated_rows=[])


@pytest.mark.slow
def test_alpha_budgets_command_emits_fragile_claims() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, str(ROOT / "prototype/strip-coherence/alpha_budgets.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FRAGILE CLAIMS" in result.stdout
    assert "walk/silhouette_budget" in result.stdout
    assert "0.4136" in result.stdout
    assert "Separated=17  Unseparated=4  Inapplicable=3" in result.stdout
