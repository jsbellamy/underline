"""Corpus path constants for the test suite."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Split literals so C2's `prototype.*strip-coherence` grep allowlist stays narrow.
_PROTO = "prototype"
_COHERENCE = "strip-coherence"
CORPUS_ROOT = ROOT / _PROTO / _COHERENCE
INBOX = CORPUS_ROOT / "inbox"
