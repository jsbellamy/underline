"""Shared CLI outcome reporting helpers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def emit_json(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")))


def exit_code(outcome: str) -> int:
    if outcome == "PASS":
        return 0
    if outcome == "FAIL":
        return 1
    if outcome == "REVIEW":
        return 3
    raise ValueError(f"unknown outcome {outcome!r}")
