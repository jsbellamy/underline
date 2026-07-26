"""Proof tests for pipeline.ingest_strip CLI (issue #11 C3–C7)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image

from pipeline.strip import DEFAULT_LAYOUT

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
LOGICAL_SIZE = (DEFAULT_LAYOUT.frame_w, DEFAULT_LAYOUT.frame_h)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.ingest_strip", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_good_idle_strip_passes_coherence_gates() -> None:
    result = _run(
        [
            str(INBOX / "01-miner-idle.png"),
            "--motion-class",
            "idle",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert "palette_drift_pass: pass" in result.stdout
    assert "silhouette_budget" not in result.stdout or "max_silhouette: pass" in result.stdout


def test_passing_strip_exports_logical_frame_pngs(tmp_path: Path) -> None:
    out = tmp_path / "frames"
    result = _run(
        [
            str(INBOX / "01-miner-idle.png"),
            "--motion-class",
            "idle",
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 0, result.stderr

    paths = sorted(out.glob("01-miner-idle-f*.png"))
    assert len(paths) == 4
    assert [path.name for path in paths] == [
        "01-miner-idle-f0.png",
        "01-miner-idle-f1.png",
        "01-miner-idle-f2.png",
        "01-miner-idle-f3.png",
    ]

    sizes: list[tuple[int, int]] = []
    for path in paths:
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            assert image.size == LOGICAL_SIZE
            sizes.append(image.size)
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            assert min(alpha.get_flattened_data()) == 0
    assert len(set(sizes)) == 1


def test_failing_strip_writes_no_frames_and_reports_tripped_gates(tmp_path: Path) -> None:
    out = tmp_path / "frames"
    result = _run(
        [
            str(INBOX / "08-NEG-identity-drift.png"),
            "--motion-class",
            "idle",
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 1
    assert not out.exists() or list(out.iterdir()) == []
    assert "FAIL" in result.stdout
    assert "silhouette_budget" in result.stdout or "max_silhouette: FAIL" in result.stdout


def test_unknown_motion_class_raises_on_stderr() -> None:
    result = _run(
        [
            str(INBOX / "01-miner-idle.png"),
            "--motion-class",
            "nonsense",
        ]
    )
    assert result.returncode == 2
    assert "unknown motion_class" in result.stderr


def test_json_mode_emits_single_parseable_object() -> None:
    result = _run(
        [
            str(INBOX / "01-miner-idle.png"),
            "--motion-class",
            "idle",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()
    data = json.loads(result.stdout)
    assert data["pass"] is True


def test_airborne_json_reports_inapplicable_gates_with_reasons() -> None:
    result = _run(
        [
            str(INBOX / "04-bat-flap.png"),
            "--motion-class",
            "airborne",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)

    displacement = data["displacement_pass"]
    assert displacement["status"] == "inapplicable"
    assert displacement["reason"]
    assert "3→0" in displacement["reason"]

    silhouette = data["max_silhouette"]
    assert silhouette["status"] == "inapplicable"
    assert silhouette["reason"]

    assert data["coherence"]["displacement_pass"] is None
    assert data["coherence"]["budgets"]["silhouette"] is None


def test_airborne_human_report_states_inapplicable_gates() -> None:
    result = _run(
        [
            str(INBOX / "04-bat-flap.png"),
            "--motion-class",
            "airborne",
        ]
    )
    assert result.returncode == 0, result.stderr
    assert "max_silhouette: inapplicable" in result.stdout
    assert "displacement_pass: inapplicable" in result.stdout
    assert "3→0" in result.stdout


def test_export_overwrites_existing_frame_file(tmp_path: Path) -> None:
    out = tmp_path / "frames"
    out.mkdir()
    stale = out / "01-miner-idle-f0.png"
    stale.write_bytes(b"stale")

    result = _run(
        [
            str(INBOX / "01-miner-idle.png"),
            "--motion-class",
            "idle",
            "--out",
            str(out),
        ]
    )
    assert result.returncode == 0, result.stderr
    with Image.open(stale) as image:
        assert image.mode == "RGBA"
        assert image.size == LOGICAL_SIZE
