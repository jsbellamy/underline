"""Tests for tests.support.corpus_paths — single corpus path constants."""

from __future__ import annotations

from pathlib import Path

from tests.support.corpus_paths import CORPUS_ROOT, INBOX, ROOT


def test_corpus_root_is_strip_coherence_directory() -> None:
    expected = ROOT / "prototype" / "strip-coherence"
    assert CORPUS_ROOT == expected
    assert CORPUS_ROOT.is_dir()


def test_inbox_is_corpus_inbox_directory() -> None:
    assert INBOX == CORPUS_ROOT / "inbox"
    assert INBOX.is_dir()
