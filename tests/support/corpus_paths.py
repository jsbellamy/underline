"""Corpus path constants for the test suite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_PROTO = "corpus"
_COHERENCE = "strip-coherence"
CORPUS_ROOT = ROOT / _PROTO / _COHERENCE
INBOX = CORPUS_ROOT / "inbox"
