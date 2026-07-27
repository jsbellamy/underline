"""Historical pre-α Budget estimator — independently worked proofs of C1–C3."""

from __future__ import annotations

import math
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DERIVE_BUDGETS = ROOT / "prototype" / "strip-coherence" / "derive_budgets.py"
sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))

from derive_budgets import _derive  # noqa: E402


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


def test_derive_budgets_emits_historical_pre_alpha_baseline() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        [sys.executable, str(DERIVE_BUDGETS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "pre-α" in out or "pre-alpha" in out
    assert "historical" in out.lower()
    assert "RUNTIME BUDGET MISMATCH" not in out
    assert "Not a runtime policy check" in out
    # C1 corpus pin: blob_idle loop worst-good 0.330 → historical baseline 0.35
    assert "blob_idle" in out
    assert "loop=0.330 -> 0.35" in out
