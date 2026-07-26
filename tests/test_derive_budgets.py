"""derive_budgets.py must agree with pipeline/strip.py MOTION_CLASSES budgets."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys


def test_derive_budgets_agrees_with_runtime() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root)}
    result = subprocess.run(
        [sys.executable, str(root / "prototype/strip-coherence/derive_budgets.py")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RUNTIME BUDGET MISMATCH" not in result.stdout
