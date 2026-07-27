"""Production Gate-control scorer tests (issue #64)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import gate_control as gc
from pipeline.gate_evidence import EvidenceError

ROOT = Path(__file__).resolve().parents[1]
IDLE_CONTROL = ROOT / "gate-controls/raw/idle--silhouette_budget--001.png"

REQUIRED_FIELDS = {
    "schema",
    "attempt_id",
    "recorded_at",
    "scorer_commit",
    "raw",
    "raw_sha256",
    "scorer_gate_config_sha256",
    "motion_class",
    "target_gate",
    "applicable_gates",
    "structural",
    "gates",
    "numeric_policy",
    "isolation",
    "caveats",
    "blockers",
    "primary_failure",
    "retry_action",
}


def _gate_controls_copy(tmp_path: Path) -> Path:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    return gate_controls


def _coh_idle_silhouette_fail() -> dict:
    return {
        "dimension_parity": True,
        "baseline_row_stable": True,
        "baseline_row_inapplicable": False,
        "silhouette_adjacent": [
            {"pair": [0, 1], "changed_cells": 3, "union_opaque": 10, "frac": 0.3}
        ],
        "silhouette_adjacent_max": 0.3,
        "loop_closure": {
            "pair": [3, 0],
            "changed_cells": 1,
            "union_opaque": 8,
            "frac": 0.1292,
        },
        "silhouette_pairwise": {"min_pair": 0.0302},
        "worst_palette_drift": 0.105,
        "displacement_pass": None,
        "gate_outcomes": {
            "silhouette_budget": {
                "acceptance_status": "SEPARATED",
                "metric": 0.3,
                "budget": 0.2239,
                "hard_fail": 0.3,
                "outcome": "REVIEW",
            },
            "loop_closure_pass": {
                "acceptance_status": "UNSEPARATED",
                "metric": 0.1292,
                "budget": 0.3,
                "hard_fail": None,
                "outcome": "PASS",
            },
            "min_pair_cohort_pass": {
                "acceptance_status": "UNSEPARATED",
                "metric": 0.0302,
                "budget": 0.07,
                "hard_fail": None,
                "outcome": "PASS",
            },
            "palette_drift_pass": {
                "acceptance_status": "SEPARATED",
                "metric": 0.105,
                "budget": 0.1974,
                "hard_fail": 0.2793,
                "outcome": "PASS",
            },
        },
        "budgets": {
            "silhouette": 0.2239,
            "loop": 0.3,
            "palette_drift": 0.1974,
            "min_pair": 0.07,
        },
    }


def test_canonical_score_command_emits_equivalent_json() -> None:
    assert IDLE_CONTROL.is_file()
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT)}
    prod = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.gate_control",
            str(IDLE_CONTROL),
            "--motion-class",
            "idle",
            "--target-gate",
            "silhouette_budget",
            "--recorded-at",
            "2026-07-27T12:00:00+00:00",
            "--scorer-commit",
            "testcommit",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    npm = subprocess.run(
        [
            "npm",
            "run",
            "-s",
            "gate-control:score",
            "--",
            str(IDLE_CONTROL),
            "--motion-class",
            "idle",
            "--target-gate",
            "silhouette_budget",
            "--recorded-at",
            "2026-07-27T12:00:00+00:00",
            "--scorer-commit",
            "testcommit",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(npm.stdout) == json.loads(prod.stdout)


def test_canonical_score_command_help_exits_zero() -> None:
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        ["npm", "run", "-s", "gate-control:score", "--", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--motion-class" in result.stdout
    assert "--target-gate" in result.stdout


def test_prototype_scorer_shim_documents_production_replacement() -> None:
    import importlib.util

    path = ROOT / "prototype/strip-coherence/gate_control.py"
    spec = importlib.util.spec_from_file_location("prototype_gate_control_doc", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    doc = path.read_text()
    assert "DEPRECATED" in doc
    assert "pipeline.gate_control" in doc
    assert "gate-control:score" in doc


def test_production_and_compatibility_cli_emit_equivalent_json() -> None:
    assert IDLE_CONTROL.is_file()
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT)}
    prod = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.gate_control",
            str(IDLE_CONTROL),
            "--motion-class",
            "idle",
            "--target-gate",
            "silhouette_budget",
            "--recorded-at",
            "2026-07-27T12:00:00+00:00",
            "--scorer-commit",
            "testcommit",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    compat = subprocess.run(
        [
            sys.executable,
            str(ROOT / "prototype/strip-coherence/gate_control.py"),
            str(IDLE_CONTROL),
            "--motion-class",
            "idle",
            "--target-gate",
            "silhouette_budget",
            "--recorded-at",
            "2026-07-27T12:00:00+00:00",
            "--scorer-commit",
            "testcommit",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    prod_run = json.loads(prod.stdout)
    compat_run = json.loads(compat.stdout)
    assert prod_run == compat_run


@pytest.mark.parametrize(
    ("motion_class", "target_gate"),
    [
        ("swing", "loop_closure_pass"),
        ("airborne", "silhouette_budget"),
        ("idle", "dimension_parity"),
        ("idle", "baseline_row_stable"),
    ],
)
def test_invalid_target_raises_specification_error_without_persistence(
    motion_class: str,
    target_gate: str,
    tmp_path: Path,
) -> None:
    with patch.object(gc, "persist_measurement_run") as persist:
        with pytest.raises(gc.SpecificationError):
            gc.measure(
                IDLE_CONTROL,
                motion_class,
                target_gate,
                recorded_at="2026-07-27T12:00:00+00:00",
                scorer_commit="test",
            )
        persist.assert_not_called()


def test_isolated_target_fail_collateral_pass() -> None:
    coh = _coh_idle_silhouette_fail()
    applicable = {
        "dimension_parity": "structural",
        "baseline_row_stable": "grounded: true",
        "silhouette_budget": "max_silhouette=0.2239",
        "loop_closure_pass": "max_loop=0.3",
        "min_pair_cohort_pass": "max_min_pair=0.07",
        "palette_drift_pass": "always",
    }
    gates = {
        gate: gc.gate_row_from_coherence(coh, gate, why)
        for gate, why in applicable.items()
    }
    isolation, blockers, caveats = gc.classify_isolation(gates, "silhouette_budget")
    assert isolation == "ISOLATED"
    assert blockers == []
    assert caveats == []


def test_collateral_failure_not_isolated() -> None:
    coh = _coh_idle_silhouette_fail()
    coh["gate_outcomes"]["palette_drift_pass"]["outcome"] = "FAIL"
    coh["gate_outcomes"]["palette_drift_pass"]["metric"] = 0.5
    applicable = {
        "silhouette_budget": "max_silhouette=0.2239",
        "palette_drift_pass": "always",
    }
    gates = {
        gate: gc.gate_row_from_coherence(coh, gate, why)
        for gate, why in applicable.items()
    }
    isolation, blockers, _ = gc.classify_isolation(gates, "silhouette_budget")
    assert isolation == "NOT_ISOLATED"
    assert "collateral failure: palette_drift_pass" in blockers


def test_target_undecidable_is_indeterminate() -> None:
    coh = {
        "displacement_pass": None,
        "displacement_reason": "alignment sharpness below floor",
        "gate_outcomes": {},
    }
    row = gc.gate_row_from_coherence(coh, "displacement_pass", "grounded: false")
    gates = {"displacement_pass": row}
    isolation, blockers, _ = gc.classify_isolation(gates, "displacement_pass")
    assert row["outcome"] == "undecidable"
    assert isolation == "INDETERMINATE"
    assert blockers == ["target gate displacement_pass is undecidable"]


def test_non_target_undecidable_records_caveat_not_blocker() -> None:
    coh = _coh_idle_silhouette_fail()
    coh["displacement_pass"] = None
    coh["displacement_reason"] = "alignment sharpness below floor"
    applicable = {
        "silhouette_budget": "max_silhouette=0.2239",
        "displacement_pass": "grounded: false",
    }
    gates = {
        gate: gc.gate_row_from_coherence(coh, gate, why)
        for gate, why in applicable.items()
    }
    isolation, blockers, caveats = gc.classify_isolation(gates, "silhouette_budget")
    assert isolation == "ISOLATED"
    assert blockers == []
    assert caveats == [
        "displacement_pass is undecidable — this control does not evidence that dimension"
    ]


def test_primary_failure_prefers_structural_then_target_then_gate_order() -> None:
    run = {
        "isolation": "NOT_ISOLATED",
        "target_gate": "silhouette_budget",
        "structural": {"recovered": False, "reason": "pitch-fail"},
        "gates": {},
    }
    pf = gc.primary_failure(run)
    assert pf == {
        "code": "STRUCTURAL_RECOVERY_FAILED",
        "gate": None,
        "rationale": "pitch-fail",
    }

    run = {
        "isolation": "INDETERMINATE",
        "target_gate": "displacement_pass",
        "structural": {"recovered": True},
        "gates": {
            "displacement_pass": {
                "outcome": "undecidable",
                "reason": "alignment sharpness below floor",
            }
        },
    }
    pf = gc.primary_failure(run)
    assert pf["code"] == "GATE_UNDECIDABLE"

    run = {
        "isolation": "NOT_ISOLATED",
        "target_gate": "silhouette_budget",
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "pass",
                "metric": 0.1,
                "budget": 0.2239,
            }
        },
    }
    pf = gc.primary_failure(run)
    assert pf["code"] == "TARGET_DEFECT_TOO_WEAK"

    run = {
        "isolation": "NOT_ISOLATED",
        "target_gate": "silhouette_budget",
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {"outcome": "fail", "metric": 0.3, "budget": 0.2239},
            "palette_drift_pass": {"outcome": "fail", "metric": 0.5, "budget": 0.1974},
            "loop_closure_pass": {"outcome": "fail", "metric": 0.5, "budget": 0.3},
        },
    }
    pf = gc.primary_failure(run)
    assert pf == {
        "code": "COLLATERAL_GATE_FAILED",
        "gate": "loop_closure_pass",
        "rationale": "loop_closure_pass measured 0.5 over budget 0.3",
    }
    retry = gc.retry_action({**run, "primary_failure": pf})
    assert retry == {
        "reason_code": "COLLATERAL_GATE_FAILED",
        "gate": "loop_closure_pass",
        "intent": "hold the collateral dimension fixed",
        "one_prompt_delta": True,
        "direction": "decrease",
        "metric_now": 0.5,
        "must_fall_below": 0.3,
    }


def test_measurement_schema_fields_and_fraction_evidence() -> None:
    run = gc.measure(
        IDLE_CONTROL,
        "idle",
        "silhouette_budget",
        recorded_at="2026-07-27T12:00:00+00:00",
        scorer_commit="testcommit",
    )
    assert REQUIRED_FIELDS <= set(run)
    assert run["schema"] == gc.MEASUREMENT_SCHEMA
    sil = run["gates"]["silhouette_budget"]
    assert sil["numerator"] == 72
    assert sil["denominator"] == 240
    assert sil["metric"] == 0.3


def test_gate_config_hash_changes_with_each_component(tmp_path: Path) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    base = gc.gate_config_hash(repo_root=tmp_path)

    profiles_path = gate_controls / "acceptance-profiles.json"
    profiles = json.loads(profiles_path.read_text())
    profiles["profiles"]["idle"]["gates"]["silhouette_budget"]["budget"] = 0.9999
    profiles_path.write_text(json.dumps(profiles, indent=2) + "\n")
    assert gc.gate_config_hash(repo_root=tmp_path) != base

    gate_controls2 = _gate_controls_copy(tmp_path / "copy2")
    manifest_path = gate_controls2 / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["promotions"][0]["status"] = "INVALIDATED"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    assert gc.gate_config_hash(repo_root=tmp_path / "copy2") != base

    gate_controls3 = _gate_controls_copy(tmp_path / "copy3")
    with patch.dict(gc.NUMERIC_POLICY, {"precision_decimal_places": 3}):
        assert gc.gate_config_hash(repo_root=tmp_path / "copy3") != base


def test_persist_measurement_run_is_append_only(tmp_path: Path) -> None:
    path = tmp_path / "measurement.json"
    payload = {"schema": gc.MEASUREMENT_SCHEMA, "isolation": "ISOLATED"}
    gc.persist_measurement_run(path, payload)
    original = path.read_bytes()
    with pytest.raises(EvidenceError, match="refusing to mutate"):
        gc.persist_measurement_run(path, {"schema": gc.MEASUREMENT_SCHEMA, "isolation": "X"})
    assert path.read_bytes() == original


def test_prototype_forwards_production_measure() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prototype_gate_control",
        ROOT / "prototype/strip-coherence/gate_control.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.measure is gc.measure
    assert module.primary_failure is gc.primary_failure
    assert module.GATE_ORDER is gc.GATE_ORDER


def test_measure_does_not_mutate_manifest(tmp_path: Path) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    manifest_path = gate_controls / "manifest.json"
    before = manifest_path.read_bytes()
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(gate_controls)}):
        gc.measure(
            IDLE_CONTROL,
            "idle",
            "silhouette_budget",
            recorded_at="2026-07-27T12:00:00+00:00",
            scorer_commit="test",
            repo_root=tmp_path,
        )
    assert manifest_path.read_bytes() == before
