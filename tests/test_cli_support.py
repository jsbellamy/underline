"""Proof tests for pipeline.cli_support (issue #487 C1–C2)."""

from __future__ import annotations

import json

import pytest

from pipeline import cli_support


def test_emit_json_prints_compact_json(capsys) -> None:
    cli_support.emit_json({"ok": True, "count": 2})

    captured = capsys.readouterr()
    assert captured.out == json.dumps({"ok": True, "count": 2}, separators=(",", ":")) + "\n"


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("PASS", 0),
        ("FAIL", 1),
        ("REVIEW", 3),
    ],
)
def test_exit_code_maps_known_outcomes(outcome: str, expected: int) -> None:
    assert cli_support.exit_code(outcome) == expected


def test_exit_code_raises_on_unknown_outcome() -> None:
    with pytest.raises(ValueError, match="unknown outcome 'BROKEN'"):
        cli_support.exit_code("BROKEN")
