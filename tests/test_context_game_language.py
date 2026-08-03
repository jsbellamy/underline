"""Behavioral proof for CONTEXT.md § Game language colony-growth vocabulary (#328)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "CONTEXT.md"


def _game_language_section() -> str:
    text = CONTEXT.read_text(encoding="utf-8")
    match = re.search(r"^## Game language\n", text, flags=re.MULTILINE)
    assert match is not None
    start = match.start()
    next_section = re.search(r"^## ", text[start + 1 :], flags=re.MULTILINE)
    end = start + 1 + next_section.start() if next_section else len(text)
    return text[start:end]


def _entry_body(section: str, term: str) -> str:
    match = re.search(
        rf"\*\*{re.escape(term)}\*\*:\n(.*?)(?=\n\*\*[A-Za-z][^*]*\*\*:|\Z)",
        section,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def test_game_language_upgrade_names_two_colony_purchases() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Upgrade")
    assert "Dig Rate Upgrade" in body
    assert "Smelter Upgrade" in body
    assert "Singular by design" not in body
    assert "single-type" not in body.lower()


def test_game_language_dig_rate_upgrade_raises_dig_rate() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Dig Rate")
    assert "Dig Rate Upgrade" in body
    assert "the one thing an Upgrade raises" not in body
    assert "visibly faster Dwarf on the Pane" in body


def test_game_language_hardness_derived_from_advance_bands() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Hardness")
    assert "Advance" in body
    assert "fixed bands" in body
    assert "Constant for the slice" not in body
    assert "shaft" not in body.lower()


def test_game_language_smelter_throughput_raised_by_upgrade() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Smelter")
    assert "Smelter Upgrade" in body
    assert "fixed for the slice" not in body.lower()
    assert "status on the Colony surface" in body
