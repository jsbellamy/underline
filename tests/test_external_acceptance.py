"""Unit tests for the external-acceptance CI helper (issue #232).

Covers Contract C2 (dual-verdict comparison), C3 (label-aware exit policy),
and C4 (bundle discovery) as pure functions over fixture payloads and fixture
trees -- no subprocess, no git, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.external_acceptance import (
    Divergence,
    compare_verdict,
    discover_bundles,
    exit_code_for_divergences,
)


def _verdict(outcome: str, fingerprint: str = "fp-1") -> dict[str, object]:
    return {"outcome": outcome, "fingerprint": fingerprint}


# --- C2: dual-verdict comparison -------------------------------------------------


def test_identical_verdicts_report_no_divergence() -> None:
    main = _verdict("PASS", fingerprint="abc123")
    candidate = _verdict("PASS", fingerprint="abc123")

    result = compare_verdict("first-room/dwarf/walk", main, candidate)

    assert result is None


def test_differing_outcomes_report_a_divergence_naming_both_values() -> None:
    main = _verdict("PASS", fingerprint="main-fp")
    candidate = _verdict("FAIL", fingerprint="candidate-fp")

    result = compare_verdict("first-room/dwarf/walk", main, candidate)

    assert result == Divergence(
        bundle="first-room/dwarf/walk",
        main_outcome="PASS",
        candidate_outcome="FAIL",
        main_fingerprint="main-fp",
        candidate_fingerprint="candidate-fp",
    )
    message = result.message()
    assert "first-room/dwarf/walk" in message
    assert "PASS" in message
    assert "FAIL" in message
    assert "main-fp" in message
    assert "candidate-fp" in message


# --- C3: label-aware exit policy -------------------------------------------------


def test_no_divergences_passes_regardless_of_the_label() -> None:
    exit_code, messages = exit_code_for_divergences([], evaluator_change=False)

    assert exit_code == 0
    assert messages == []


def test_a_divergence_without_the_label_fails() -> None:
    divergence = Divergence(
        bundle="first-room/lantern",
        main_outcome="PASS",
        candidate_outcome="FAIL",
        main_fingerprint="m",
        candidate_fingerprint="c",
    )

    exit_code, messages = exit_code_for_divergences([divergence], evaluator_change=False)

    assert exit_code != 0
    assert len(messages) == 1
    assert "first-room/lantern" in messages[0]


def test_the_same_divergence_with_the_label_passes_as_an_annotation() -> None:
    divergence = Divergence(
        bundle="first-room/lantern",
        main_outcome="PASS",
        candidate_outcome="FAIL",
        main_fingerprint="m",
        candidate_fingerprint="c",
    )

    exit_code, messages = exit_code_for_divergences([divergence], evaluator_change=True)

    assert exit_code == 0
    assert len(messages) == 1
    assert "first-room/lantern" in messages[0]


# --- C4: bundle discovery --------------------------------------------------------


def _write_manifest(path: Path, schema: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": schema}), encoding="utf-8")


def test_discovery_finds_top_level_and_nested_bundles_but_skips_non_bundles(
    tmp_path: Path,
) -> None:
    assets_root = tmp_path / "assets"
    _write_manifest(assets_root / "bundle-one" / "manifest.json", "final-polish-bundle/2")
    _write_manifest(assets_root / "bundle-two" / "manifest.json", "final-polish-bundle/1")
    # Non-bundle directory: a manifest.json that is not a Polish Bundle schema.
    _write_manifest(assets_root / "not-a-bundle" / "manifest.json", "asset-pack/0")
    # A bundle nested a level deeper than the top-level ones.
    _write_manifest(
        assets_root / "group" / "nested-bundle" / "manifest.json", "final-polish-bundle/1"
    )

    bundles = discover_bundles(assets_root)

    assert sorted(p.relative_to(assets_root).as_posix() for p in bundles) == [
        "bundle-one",
        "bundle-two",
        "group/nested-bundle",
    ]


def test_discovery_over_an_empty_or_missing_root_finds_nothing(tmp_path: Path) -> None:
    assert discover_bundles(tmp_path / "assets") == []

    empty_root = tmp_path / "empty-assets"
    empty_root.mkdir()
    assert discover_bundles(empty_root) == []


def test_discovery_ignores_a_directory_with_no_manifest_at_all(tmp_path: Path) -> None:
    assets_root = tmp_path / "assets"
    (assets_root / "no-manifest").mkdir(parents=True)
    _write_manifest(assets_root / "real-bundle" / "manifest.json", "final-polish-bundle/2")

    bundles = discover_bundles(assets_root)

    assert [p.relative_to(assets_root).as_posix() for p in bundles] == ["real-bundle"]
