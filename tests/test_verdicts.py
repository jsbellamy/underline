"""Verdict vocabulary aliases and membership sets (issue #144)."""

from __future__ import annotations

import inspect
from pathlib import Path

from pipeline import gate_evidence as ge
from pipeline import strip
from pipeline import verdicts

ROOT = Path(__file__).resolve().parents[1]


def test_gate_outcome_frozenset_matches_literal() -> None:
    assert verdicts.GATE_OUTCOMES == frozenset({"PASS", "REVIEW", "FAIL"})


def test_gate_review_verdict_frozenset_matches_literal() -> None:
    assert verdicts.GATE_REVIEW_VERDICTS == frozenset(
        {"APPROVE", "REJECT", "UNCERTAIN"}
    )


def test_isolation_verdict_frozenset_matches_literal() -> None:
    assert verdicts.ISOLATION_VERDICTS == frozenset(
        {"ISOLATED", "NOT_ISOLATED", "INDETERMINATE"}
    )


def test_strip_outcome_aliases_gate_outcome() -> None:
    assert strip.Outcome is verdicts.GateOutcome


def test_polish_profile_verdict_edit_not_in_verdict_module() -> None:
    source = inspect.getsource(verdicts)
    assert "EDIT" not in source


def test_checked_in_gate_controls_unchanged_after_verdict_imports(
    tmp_path: Path,
) -> None:
    before = ge.fingerprint_tree(ROOT / "gate-controls")
    tmp_path.joinpath("noop.txt").write_text("touch", encoding="utf-8")
    after = ge.fingerprint_tree(ROOT / "gate-controls")
    assert after == before
