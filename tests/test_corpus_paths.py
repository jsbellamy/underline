"""Corpus path resolver for frozen recorded evidence paths (issue #488)."""

from __future__ import annotations

from pathlib import Path

from pipeline import corpus_paths as cp


def test_corpus_root_is_current_strip_coherence_location() -> None:
    assert cp.CORPUS_ROOT.name == "strip-coherence"
    assert cp.CORPUS_ROOT.parts[-2] == "prototype"


def test_legacy_corpus_prefixes_contains_strip_coherence() -> None:
    prefix = cp.LEGACY_CORPUS_PREFIXES[0]
    assert prefix.endswith("strip-coherence")
    assert prefix.startswith("prototype")


def test_resolve_recorded_path_legacy_prefixed_corpus_file(tmp_path: Path) -> None:
    prefix = cp.LEGACY_CORPUS_PREFIXES[0]
    recorded = f"{prefix}/inbox/miner-idle-strip.png"
    resolved = cp.resolve_recorded_path(recorded, root=tmp_path)
    assert resolved == tmp_path / cp.CORPUS_ROOT / "inbox" / "miner-idle-strip.png"


def test_resolve_recorded_path_non_prefixed_repo_relative(tmp_path: Path) -> None:
    recorded = "gate-controls/raw/idle--silhouette_budget--001.png"
    resolved = cp.resolve_recorded_path(recorded, root=tmp_path)
    assert resolved == tmp_path / "gate-controls/raw/idle--silhouette_budget--001.png"


def test_resolve_recorded_path_prefix_substring_not_path_prefix(tmp_path: Path) -> None:
    prefix = cp.LEGACY_CORPUS_PREFIXES[0]
    recorded = f"{prefix}-backup/inbox/stale.png"
    resolved = cp.resolve_recorded_path(recorded, root=tmp_path)
    assert resolved == tmp_path / f"{prefix}-backup/inbox/stale.png"
