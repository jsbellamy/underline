"""Agent routing docs describe the shipped TypeScript game (#483)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_MD = ROOT / "docs" / "agents" / "domain.md"
CODE_STYLE_MD = ROOT / "docs" / "agents" / "code-style.md"
AGENTS_MD = ROOT / "AGENTS.md"
README = ROOT / "README.md"

STALE_PHRASES = (
    "src/ does not exist yet",
    "No TypeScript exists yet",
    "no browser or native harness",
)

AGENT_DOC_PATHS = (DOMAIN_MD, CODE_STYLE_MD, AGENTS_MD, README)


@pytest.mark.parametrize("doc_path", AGENT_DOC_PATHS)
def test_agent_docs_do_not_claim_game_is_absent(doc_path: Path) -> None:
    text = doc_path.read_text()
    for phrase in STALE_PHRASES:
        assert phrase not in text, f"{doc_path.name} still contains stale phrase: {phrase!r}"


def test_agents_md_does_not_defer_typescript_tests() -> None:
    text = AGENTS_MD.read_text()
    assert "TS tests as they land" not in text


def test_readme_documents_game_dev_command() -> None:
    text = README.read_text()
    assert "npm run dev" in text


def test_agents_md_documents_tauri_shell() -> None:
    text = AGENTS_MD.read_text()
    assert "src-tauri" in text
