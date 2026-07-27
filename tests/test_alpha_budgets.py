"""α-Budget derivation — worked examples from issue #28."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype" / "strip-coherence"))

from alpha_budgets import (  # noqa: E402
    ALPHA,
    _required_separated_promotion_ids,
    derive_separated_budget,
)
from numeric_policy import canonical_metric  # noqa: E402


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


def test_required_separated_promotion_ids_counts_seventeen_provider_controls() -> None:
    required = _required_separated_promotion_ids()
    assert len(required) == 17
    assert "promo--walk--loop_closure_pass" in required
    assert "promo--swing--silhouette_budget" in required


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
