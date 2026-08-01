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

from pipeline.strip import ALPHA, derive_separated_budget  # noqa: E402
from numeric_policy import canonical_metric  # noqa: E402
import alpha_budgets as ab  # noqa: E402


class _CallResult:
    """Mimics the subprocess.CompletedProcess fields the tests assert on."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_alpha_budgets(
    gate_controls: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> _CallResult:
    """In-process equivalent of spawning `alpha_budgets.py` as a child process.

    Shares the session strip-read memoization installed by conftest.py instead of
    spawning a child process that can't see it. `alpha_budgets.main` never catches
    its own failures, so a blocked call surfaces as an uncaught `SystemExit` (the
    script's own explicit checks) or `ValueError` (checks inside `pipeline.strip`
    propagating up) — both map to the nonzero exit code a spawned process would
    have produced, with the failure text carried on the exception itself rather
    than a printed traceback.
    """
    try:
        code = ab.main(gate_controls=gate_controls)
    except (SystemExit, ValueError) as exc:
        captured = capsys.readouterr()
        message = exc.code if isinstance(exc, SystemExit) else None
        text = message if isinstance(message, str) else str(exc)
        return _CallResult(1, captured.out, captured.err + text)
    captured = capsys.readouterr()
    return _CallResult(code, captured.out, captured.err)


def _gate_controls_copy(tmp_path: pathlib.Path) -> pathlib.Path:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    return gate_controls


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
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    manifest_path = gate_controls / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    for promo in doc["promotions"]:
        if promo["id"] == "promo--walk--loop_closure_pass":
            promo["status"] = "PENDING_VERIFICATION"
            break
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    assert "not ACTIVE" in result.stdout + result.stderr
    assert "promo--walk--loop_closure_pass" in result.stdout + result.stderr


def test_alpha_budgets_blocks_when_promotion_invalidated(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    manifest_path = gate_controls / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    for promo in doc["promotions"]:
        if promo["id"] == "promo--walk--loop_closure_pass":
            promo["status"] = "INVALIDATED"
            break
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    assert "not ACTIVE" in result.stdout + result.stderr


def test_alpha_budgets_blocks_when_profile_row_missing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    del doc["profiles"]["walk"]["gates"]["loop_closure_pass"]
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    assert "missing Acceptance status for walk/loop_closure_pass" in (
        result.stdout + result.stderr
    )


def test_alpha_budgets_blocks_missing_promotion(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    manifest_path = gate_controls / "manifest.json"
    doc = json.loads(manifest_path.read_text())
    doc["promotions"] = [
        promo
        for promo in doc["promotions"]
        if promo["id"] != "promo--walk--loop_closure_pass"
    ]
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "missing Promotion" in output or "not ACTIVE" in output


def test_alpha_budgets_blocks_mismatched_promotion_reference(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    doc["profiles"]["walk"]["gates"]["loop_closure_pass"]["active_promotion"] = (
        "promo--walk--silhouette_budget"
    )
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    assert "alternate Promotion" in result.stdout + result.stderr


def test_alpha_budgets_blocks_invalid_measurement_evidence(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    manifest_path = gate_controls / "manifest.json"
    bad_rel = "gate-controls/reports/test-invalid-measurement.json"
    bad_path = ROOT / bad_rel
    bad_path.write_text(json.dumps({"gates": {}}))
    doc = json.loads(manifest_path.read_text())
    for promo in doc["promotions"]:
        if promo["id"] == "promo--walk--loop_closure_pass":
            promo["measurement_path"] = bad_rel
            break
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    bad_path.unlink(missing_ok=True)
    assert result.returncode != 0
    assert "invalid Measurement evidence" in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("mutator", "needle"),
    [
        (
            lambda doc: doc["profiles"]["walk"]["gates"]["silhouette_budget"].update(
                {"status": "UNSEPARATED"}
            ),
            "runtime projection mismatch",
        ),
        (
            lambda doc: doc["profiles"]["walk"]["gates"]["silhouette_budget"].update(
                {"budget": 9.9999}
            ),
            "runtime projection mismatch",
        ),
        (
            lambda doc: doc["profiles"]["walk"]["gates"]["silhouette_budget"].update(
                {"hard_fail": 9.9999}
            ),
            "runtime projection mismatch",
        ),
        (
            lambda doc: doc["profiles"]["walk"]["gates"]["silhouette_budget"].update(
                {"budget": 9.9998}
            ),
            "runtime projection mismatch",
        ),
        (
            lambda doc: doc["profiles"]["walk"]["gates"].pop("silhouette_budget"),
            "missing Acceptance status for walk/silhouette_budget",
        ),
    ],
)
def test_alpha_budgets_blocks_runtime_projection_mismatch(
    tmp_path: pathlib.Path, mutator, needle: str, capsys: pytest.CaptureFixture[str]
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    mutator(doc)
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")
    result = _run_alpha_budgets(gate_controls, capsys)
    assert result.returncode != 0
    assert needle in result.stdout + result.stderr


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
