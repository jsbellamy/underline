"""Named verdict vocabularies from CONTEXT.md."""

from __future__ import annotations

from typing import Literal

__all__ = [
    "GATE_OUTCOMES",
    "GATE_REVIEW_VERDICTS",
    "GateOutcome",
    "GateReviewVerdict",
    "ISOLATION_VERDICTS",
    "IsolationVerdict",
]

# Gate outcome
GateOutcome = Literal["PASS", "REVIEW", "FAIL"]
GATE_OUTCOMES: frozenset[str] = frozenset({"PASS", "REVIEW", "FAIL"})

# Gate review
GateReviewVerdict = Literal["APPROVE", "REJECT", "UNCERTAIN"]
GATE_REVIEW_VERDICTS: frozenset[str] = frozenset({"APPROVE", "REJECT", "UNCERTAIN"})

# Isolation verdict
IsolationVerdict = Literal["ISOLATED", "NOT_ISOLATED", "INDETERMINATE"]
ISOLATION_VERDICTS: frozenset[str] = frozenset(
    {"ISOLATED", "NOT_ISOLATED", "INDETERMINATE"}
)
