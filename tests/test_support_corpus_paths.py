"""Tests for tests.support.corpus_paths — single corpus path constants."""

from __future__ import annotations

import subprocess

from tests.support.corpus_paths import CORPUS_ROOT, INBOX, ROOT

_ALLOWED_INLINE_CORPUS_PATH_FILES = frozenset(
    {
        "tests/test_afk_operational_docs.py",
        "tests/test_ci_surfaces.py",
        "tests/test_select_changed_tests.py",
    }
)


def test_corpus_root_is_strip_coherence_directory() -> None:
    assert CORPUS_ROOT.is_dir()
    assert CORPUS_ROOT.name == "strip-coherence"
    assert CORPUS_ROOT.parent.name == "prototype"


def test_inbox_is_corpus_inbox_directory() -> None:
    assert INBOX == CORPUS_ROOT / "inbox"
    assert INBOX.is_dir()


def test_no_inline_prototype_strip_coherence_paths_outside_allowlist() -> None:
    result = subprocess.run(
        ["git", "grep", "-l", r"prototype.*strip-coherence", "--", "tests/"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    matched = frozenset(
        line for line in result.stdout.splitlines() if line.strip()
    ) - {"tests/test_support_corpus_paths.py"}
    assert matched == _ALLOWED_INLINE_CORPUS_PATH_FILES
