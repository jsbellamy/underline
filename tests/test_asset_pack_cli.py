"""Subprocess proof for pipeline.asset_pack_cli (issue #106)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pipeline.gate_evidence import sha256_file
from tests.support.asset_pack import pack_doc, write_pack

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / ".pytest-asset-pack"


@pytest.fixture
def pack_fixture_dir(tmp_path: Path) -> Path:
    root = FIXTURE_ROOT / tmp_path.name
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _run_module(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.asset_pack_cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _json_stdout(stdout: str) -> dict[str, object]:
    line = stdout.strip().splitlines()[-1]
    return json.loads(line)


def _run_npm(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npm", "run", "asset:pack", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_npm_check_valid_pack_exit_0_json(pack_fixture_dir: Path) -> None:
    pack = write_pack(pack_fixture_dir)
    result = _run_npm(["check", str(pack), "--json"])
    assert result.returncode == 0, result.stderr
    payload = _json_stdout(result.stdout)
    assert payload["valid"] is True
    assert payload["outcome"] == "PASS"
    assert payload["manifest"] == str(pack.resolve())


def test_npm_check_invalid_pack_exit_2_json(pack_fixture_dir: Path) -> None:
    doc = pack_doc(pack_fixture_dir)
    doc["assets"][0]["releases"][0]["sha256"] = "0" * 64
    pack = write_pack(pack_fixture_dir, doc)
    result = _run_npm(["check", str(pack), "--json"])
    assert result.returncode == 2, result.stderr
    payload = _json_stdout(result.stdout)
    assert payload["valid"] is False
    assert "error" in payload


def test_npm_preview_writes_outputs_json(pack_fixture_dir: Path) -> None:
    pack = write_pack(pack_fixture_dir)
    out = pack_fixture_dir / "preview-out"
    result = _run_npm(["preview", str(pack), "--out", str(out), "--json"])
    assert result.returncode == 0, result.stderr
    payload = _json_stdout(result.stdout)
    assert payload["native_path"] == str((out / "native.png").resolve())
    assert payload["scale4x_path"] == str((out / "4x.png").resolve())
    assert (out / "native.png").is_file()
    assert (out / "4x.png").is_file()
    with Image.open(out / "native.png") as native:
        assert native.size == (320, 180)


def test_module_check_human_output(pack_fixture_dir: Path) -> None:
    pack = write_pack(pack_fixture_dir)
    result = _run_module(["check", str(pack)])
    assert result.returncode == 0, result.stderr
    assert "PASS" in result.stdout
    assert "first-room" in result.stdout


def test_module_preview_invalid_exit_2(pack_fixture_dir: Path) -> None:
    doc = pack_doc(pack_fixture_dir)
    doc["assets"][0]["final_report"]["sha256"] = "0" * 64
    pack = write_pack(pack_fixture_dir, doc)
    out = pack_fixture_dir / "preview-out"
    result = _run_module(["preview", str(pack), "--out", str(out)])
    assert result.returncode == 2, result.stdout
    assert not out.exists() or not (out / "native.png").exists()
