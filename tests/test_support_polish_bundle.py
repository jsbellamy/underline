"""Behavioral proof for tests.support.polish_bundle (issue #248)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.final_polish import check_bundle
from pipeline.final_polish_cli import main as final_polish_cli_main
from tests.support import polish_bundle as pb

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
WALK_STRIP = INBOX / "05-miner-walk.png"


def test_support_polish_bundle_exposes_prepared_attempt_surface() -> None:
    import tests.support.polish_bundle  # noqa: F401

    assert hasattr(tests.support.polish_bundle, "PreparedAttempt")
    assert hasattr(tests.support.polish_bundle, "prepare")
    assert hasattr(tests.support.polish_bundle, "init_bundle")
    assert hasattr(tests.support.polish_bundle, "init_argv")
    assert hasattr(tests.support.polish_bundle, "acquisition_store_env")
    assert hasattr(tests.support.polish_bundle, "bundle_store_env")
    assert hasattr(tests.support.polish_bundle, "bundle_store_env_context")
    assert hasattr(tests.support.polish_bundle, "bundle_store_root")
    assert hasattr(tests.support.polish_bundle, "record_store_attempt")


def test_prepare_idle_attempt_is_text_to_image_without_identity_paths(tmp_path: Path) -> None:
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)

    assert attempt.edit_source is None
    assert attempt.identity_reference is None
    provenance = json.loads(attempt.provenance.read_text(encoding="utf-8"))
    assert provenance["generation_mode"] == "text-to-image"


def test_prepare_walk_dwarf_miner_attempt_is_image_edit_with_edit_source(tmp_path: Path) -> None:
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="dwarf-miner")

    assert attempt.edit_source is not None
    assert attempt.identity_reference is not None
    provenance = json.loads(attempt.provenance.read_text(encoding="utf-8"))
    assert provenance["generation_mode"] == "image-edit"


def test_init_argv_builds_strip_polish_init_vector_without_initializing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    argv = pb.init_argv(attempt, bundle)

    assert argv[:2] == ["init", str(attempt.provider)]
    assert "--motion-class" in argv and argv[argv.index("--motion-class") + 1] == "idle"
    assert "--out" in argv and argv[argv.index("--out") + 1] == str(bundle)
    assert "--provenance" in argv and argv[argv.index("--provenance") + 1] == str(attempt.provenance)
    assert not bundle.exists()

    with patch.dict("os.environ", attempt.env):
        returncode = final_polish_cli_main(argv)
    captured = capsys.readouterr()
    assert returncode == 0, captured.err
    assert bundle.is_dir()


def test_init_argv_json_flag_appended_when_requested(tmp_path: Path) -> None:
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    argv = pb.init_argv(attempt, tmp_path / "bundle", json_mode=True)

    assert argv[-1] == "--json"


def test_init_argv_includes_polish_profile_when_prepared(tmp_path: Path) -> None:
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="dwarf-miner")
    argv = pb.init_argv(attempt, tmp_path / "bundle")

    assert "--polish-profile" in argv
    assert argv[argv.index("--polish-profile") + 1] == "dwarf-miner"


def test_init_bundle_on_idle_attempt_yields_passing_polish_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)

    pb.init_bundle(attempt, bundle)

    with patch.dict("os.environ", attempt.env):
        result = check_bundle(bundle)
    assert result.outcome == "PASS"


def test_init_argv_never_initializes_a_polish_bundle(tmp_path: Path) -> None:
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    bundle = tmp_path / "bundle"

    with patch("tests.support.polish_bundle.initialize_bundle") as init_mock:
        argv = pb.init_argv(attempt, bundle)

    init_mock.assert_not_called()
    assert not bundle.exists()
    assert argv[0] == "init"
    assert not hasattr(pb, "attempt_from_argv")


def test_init_bundle_on_dwarf_miner_walk_uses_ingest_patch_when_strip_differs(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="dwarf-miner")

    assert attempt.ingest_source != attempt.provider

    pb.init_bundle(attempt, bundle)

    assert bundle.is_dir()


def test_prepared_attempt_initialization_centralizes_ingest_strip_provider_patch() -> None:
    result = subprocess.run(
        [
            "grep",
            "-rn",
            'patch("pipeline.final_polish.ingest_strip_provider"',
            "tests/support/",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1


def test_acquisition_store_env_sets_controls_root(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"

    assert pb.acquisition_store_env(store_root) == {
        "UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root),
    }


def test_bundle_store_root_absent_without_attempts_ledger(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle.parent / "acquisition-controls").mkdir()

    assert pb.bundle_store_root(bundle) is None


def test_bundle_store_root_present_when_attempts_ledger_exists(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    store_root = bundle.parent / "acquisition-controls"
    store_root.mkdir()
    (store_root / "attempts.jsonl").write_text("{}\n", encoding="utf-8")

    assert pb.bundle_store_root(bundle) == store_root


def test_bundle_store_env_matches_store_root_presence(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    store_root = bundle.parent / "acquisition-controls"
    store_root.mkdir()

    assert pb.bundle_store_env(bundle) is None

    (store_root / "attempts.jsonl").write_text("{}\n", encoding="utf-8")
    assert pb.bundle_store_env(bundle) == pb.acquisition_store_env(store_root)


def test_record_store_attempt_returns_row_and_stored_provider_path(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"

    row, provider_path = pb.record_store_attempt(
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

    with pb.bundle_store_env_context(bundle):
        import os

        assert os.environ["UNDERLINE_ACQUISITION_CONTROLS_ROOT"] == str(store_root)
