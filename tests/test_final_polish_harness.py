"""Behavioral proof for tests.final_polish_harness (issue #242)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.final_polish_harness import (
    acquisition_store_env,
    bundle_store_env,
    bundle_store_env_context,
    bundle_store_root,
    record_store_attempt,
)

ROOT = Path(__file__).resolve().parents[1]
PASS_STRIP = ROOT / "prototype" / "strip-coherence" / "inbox" / "01-miner-idle.png"


def test_acquisition_store_env_sets_controls_root(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"

    assert acquisition_store_env(store_root) == {
        "UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root),
    }


def test_bundle_store_root_absent_without_attempts_ledger(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle.parent / "acquisition-controls").mkdir()

    assert bundle_store_root(bundle) is None


def test_bundle_store_root_present_when_attempts_ledger_exists(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    store_root = bundle.parent / "acquisition-controls"
    store_root.mkdir()
    (store_root / "attempts.jsonl").write_text("{}\n", encoding="utf-8")

    assert bundle_store_root(bundle) == store_root


def test_bundle_store_env_matches_store_root_presence(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    store_root = bundle.parent / "acquisition-controls"
    store_root.mkdir()

    assert bundle_store_env(bundle) is None

    (store_root / "attempts.jsonl").write_text("{}\n", encoding="utf-8")
    assert bundle_store_env(bundle) == acquisition_store_env(store_root)


def test_record_store_attempt_returns_row_and_stored_provider_path(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"

    row, provider_path = record_store_attempt(
        store_root,
        PASS_STRIP,
        "test/idle",
        motion_class="idle",
        generation_mode="text-to-image",
        acquiring_agent="pytest",
        prompt_text="underline harness test prompt",
        repo_root=tmp_path,
    )

    assert row["raw_path"]
    assert provider_path == store_root / row["raw_path"]
    assert provider_path.is_file()


def test_bundle_store_env_context_applies_controls_root(tmp_path: Path, monkeypatch) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    store_root = bundle.parent / "acquisition-controls"
    store_root.mkdir()
    (store_root / "attempts.jsonl").write_text("{}\n", encoding="utf-8")
    monkeypatch.delenv("UNDERLINE_ACQUISITION_CONTROLS_ROOT", raising=False)

    with bundle_store_env_context(bundle):
        import os

        assert os.environ["UNDERLINE_ACQUISITION_CONTROLS_ROOT"] == str(store_root)
