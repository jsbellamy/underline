"""Pytest configuration for the underline prototype."""

from __future__ import annotations

import pathlib
import sys

STRIP_COHERENCE = pathlib.Path(__file__).resolve().parents[1] / "prototype" / "strip-coherence"
if str(STRIP_COHERENCE) not in sys.path:
    sys.path.insert(0, str(STRIP_COHERENCE))
