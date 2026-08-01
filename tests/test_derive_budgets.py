"""Historical pre-α Budget estimator — independently worked proofs of C1–C3."""

from __future__ import annotations

import math
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))

from derive_budgets import _derive  # noqa: E402
import derive_budgets  # noqa: E402


class _CallResult:
    """Mimics the subprocess.CompletedProcess fields the tests assert on."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_derive_budgets(capsys: pytest.CaptureFixture[str]) -> _CallResult:
    code = derive_budgets.main()
    captured = capsys.readouterr()
    return _CallResult(code, captured.out, captured.err)


def _hand_derive(worst: float) -> float:
    """Historical pre-α estimator: ceil_to_0.01(worst) + 0.02 (worked independently)."""
    return round(math.ceil(worst * 100) / 100 + 0.02, 2)


def test_pre_alpha_estimator_matches_independently_worked_values() -> None:
    # Hand-worked continuous-gate cases from the historical estimator formula.
    cases = [
        (0.330, 0.35),  # blob_idle loop baseline (worst Manifest-good loop)
        (0.337, 0.36),  # blob_idle silhouette
        (0.196, 0.22),  # blob_idle drift
        (0.103, 0.13),  # blob_idle min_pair
        (0.148, 0.17),  # idle silhouette
        (0.273, 0.30),  # idle loop
    ]
    for worst, expected in cases:
        assert _hand_derive(worst) == expected
        assert _derive(worst) == expected


@pytest.mark.slow
def test_derive_budgets_emits_historical_pre_alpha_baseline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_derive_budgets(capsys)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "pre-α" in out or "pre-alpha" in out
    assert "historical" in out.lower()
    assert "RUNTIME BUDGET MISMATCH" not in out
    assert "Not a runtime policy check" in out
    # C1 corpus pin: blob_idle loop worst-good 0.330 → historical baseline 0.35
    assert "blob_idle" in out
    assert "loop=0.330 -> 0.35" in out

    npm = subprocess.run(
        ["npm", "run", "-s", "prototype:strip:derive-budgets"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert npm.returncode == 0, npm.stdout + npm.stderr
    npm_out = npm.stdout
    assert "pre-α" in npm_out or "pre-alpha" in npm_out
    assert "historical" in npm_out.lower()
    assert "RUNTIME BUDGET MISMATCH" not in npm_out
    assert "Not a runtime policy check" in npm_out
    assert "blob_idle" in npm_out
    assert "loop=0.330 -> 0.35" in npm_out
