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


def test_polish_bundle_module_is_importable() -> None:
    import tests.support.polish_bundle  # noqa: F401


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


def test_init_bundle_does_not_reconstruct_attempt_from_argv(tmp_path: Path) -> None:
    """C5: PreparedAttempt is built from typed fields, never from argv positions."""
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    argv = pb.init_argv(attempt, bundle)

    source = Path(pb.__file__).read_text(encoding="utf-8")
    assert "PreparedAttempt(" not in source or "argv" not in source.split("PreparedAttempt(", 1)[-1].split(")", 1)[0]
    assert argv[0] == "init"
    assert not hasattr(pb, "attempt_from_argv")


def test_support_tree_has_single_ingest_patch_site() -> None:
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


def test_init_argv_never_calls_initialize_bundle(tmp_path: Path) -> None:
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    bundle = tmp_path / "bundle"

    with patch("tests.support.polish_bundle.initialize_bundle") as init_mock:
        pb.init_argv(attempt, bundle)

    init_mock.assert_not_called()
