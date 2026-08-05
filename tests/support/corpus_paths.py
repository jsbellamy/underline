"""Corpus path constants for the test suite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "prototype" / "strip-coherence"
INBOX = CORPUS_ROOT / "inbox"
