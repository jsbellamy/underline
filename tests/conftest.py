"""Pytest configuration for the underline prototype."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
STRIP_COHERENCE = ROOT / "prototype" / "strip-coherence"
for path in (ROOT, STRIP_COHERENCE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
