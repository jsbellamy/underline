"""Resolve frozen recorded corpus paths against the live corpus location."""

from __future__ import annotations

from pathlib import Path

CORPUS_ROOT: Path = Path("corpus/strip-coherence")

LEGACY_CORPUS_PREFIXES: tuple[str, ...] = ("prototype/strip-coherence",)


def resolve_recorded_path(recorded: str, *, root: Path) -> Path:
    """Map a recorded repo-relative path onto the filesystem under ``root``."""
    for prefix in LEGACY_CORPUS_PREFIXES:
        if recorded == prefix or recorded.startswith(f"{prefix}/"):
            remainder = recorded[len(prefix):].lstrip("/")
            return root / CORPUS_ROOT / remainder
    return root / recorded
