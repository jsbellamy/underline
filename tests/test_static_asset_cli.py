"""Subprocess proof for pipeline.static_asset_cli (issue #105)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from pipeline.gate_evidence import sha256_file
from pipeline.recovery import MAGENTA
from pipeline.static_asset import initialize_static_bundle
from pipeline.strip import Cell

ROOT = Path(__file__).resolve().parents[1]
PALETTE_SHA = sha256_file(ROOT / "assets" / "palettes" / "first-room.json")
STONE = (74, 59, 72)
STONE_LIGHT = (98, 81, 93)
PITCH = 24
BORDER_PAD = 2


def _draw_block(px, gx: int, gy: int, pitch: int, rgb: tuple[int, int, int]) -> None:
    x0 = BORDER_PAD + gx * pitch
    y0 = BORDER_PAD + gy * pitch
    for y in range(y0, y0 + pitch):
        for x in range(x0, x0 + pitch):
            px[x, y] = (*rgb, 255)


def _item_block(rgb: tuple[int, int, int], cell_w: int, cell_h: int) -> list[list[Cell]]:
    alt = STONE_LIGHT if rgb == STONE else STONE
    return [
        [rgb if (x + y) % 2 == 0 else alt for x in range(cell_w)]
        for y in range(cell_h)
    ]


def _render_static_sheet(
    *,
    cell_w: int,
    cell_h: int,
    columns: int,
    rows: int,
    gutter: int,
    item_cells: dict[int, list[list[Cell]]],
) -> Image.Image:
    grid_w = columns * cell_w + (columns - 1) * gutter
    grid_h = rows * cell_h + (rows - 1) * gutter
    image = Image.new(
        "RGBA",
        (grid_w * PITCH + BORDER_PAD * 2, grid_h * PITCH + BORDER_PAD * 2),
        (*MAGENTA, 255),
    )
    pixels = image.load()
    assert pixels is not None
    for index, cells in item_cells.items():
        col = index % columns
        row = index // columns
        origin_gx = col * (cell_w + gutter)
        origin_gy = row * (cell_h + gutter)
        for gy in range(cell_h):
            for gx in range(cell_w):
                rgb = cells[gy][gx]
                if rgb is None:
                    continue
                _draw_block(pixels, origin_gx + gx, origin_gy + gy, PITCH, rgb)
    return image


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    provider = tmp_path / "sheet.png"
    image = _render_static_sheet(
        cell_w=4,
        cell_h=4,
        columns=2,
        rows=1,
        gutter=2,
        item_cells={
            0: _item_block(STONE, 4, 4),
            1: _item_block(STONE_LIGHT, 4, 4),
        },
    )
    image.save(provider)
    provenance = tmp_path / "sheet.source.json"
    provenance.write_text(
        json.dumps({"raw_sha256": sha256_file(provider), "master_palette_id": "first-room"})
        + "\n",
        encoding="utf-8",
    )
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "static-sheet-spec/0",
                "id": "cli-tiles",
                "cell_w": 4,
                "cell_h": 4,
                "columns": 2,
                "rows": 1,
                "gutter": 2,
                "master_palette": {
                    "path": "assets/palettes/first-room.json",
                    "sha256": PALETTE_SHA,
                },
                "items": [
                    {"id": "tile-a", "index": 0, "release_path": "tiles/tile-a.png"},
                    {"id": "tile-b", "index": 1, "release_path": "tiles/tile-b.png"},
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return provider, provenance, spec


def _run_module(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.static_asset_cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_npm(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npm", "run", "asset:static", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_npm_entrypoint_runs_init_check_finalize(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    init = _run_npm(
        [
            "init",
            str(provider),
            "--provenance",
            str(provenance),
            "--spec",
            str(spec),
            "--out",
            str(bundle),
        ]
    )
    assert init.returncode == 0, init.stderr
    check = _run_npm(["check", str(bundle)])
    assert check.returncode == 0, check.stderr
    finalize = _run_npm(["finalize", str(bundle)])
    assert finalize.returncode == 0, finalize.stderr
    assert (bundle / "release" / "tiles" / "tile-a.png").is_file()


def test_init_creates_bundle_via_module_entrypoint(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    result = _run_module(
        [
            "init",
            str(provider),
            "--provenance",
            str(provenance),
            "--spec",
            str(spec),
            "--out",
            str(bundle),
        ]
    )
    assert result.returncode == 0, result.stderr
    assert (bundle / "manifest.json").is_file()


def test_init_invalid_provider_exit_2(tmp_path: Path) -> None:
    provider = tmp_path / "bad.png"
    provider.write_bytes(b"not png")
    provenance = tmp_path / "bad.source.json"
    provenance.write_text(json.dumps({"raw_sha256": sha256_file(provider)}) + "\n")
    _, _, spec = _write_fixture(tmp_path / "fixture")
    bundle = tmp_path / "bundle"
    result = _run_module(
        [
            "init",
            str(provider),
            "--provenance",
            str(provenance),
            "--spec",
            str(spec),
            "--out",
            str(bundle),
        ]
    )
    assert result.returncode == 2


def test_check_fail_exit_1(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    initialize_static_bundle(provider, provenance, spec, bundle, repo_root=ROOT)
    polished = bundle / "polished" / "tile-a.png"
    with Image.open(polished) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        pixels[0, 0] = (1, 2, 3, 255)
        rgba.save(polished)
    result = _run_module(["check", str(bundle)])
    assert result.returncode == 1


def test_init_json_emits_hashes(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    result = _run_module(
        [
            "init",
            str(provider),
            "--provenance",
            str(provenance),
            "--spec",
            str(spec),
            "--out",
            str(bundle),
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "PASS"
    assert payload["manifest_sha256"]
    assert payload["spec_sha256"]
    assert payload["palette_sha256"]
    assert payload["draft_hashes"]
    assert payload["polished_hashes"]


def test_finalize_json_reports_release_paths(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    initialize_static_bundle(provider, provenance, spec, bundle, repo_root=ROOT)
    result = _run_module(["finalize", str(bundle), "--json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["report_path"]
    assert payload["release_paths"]
    assert len(payload["release_paths"]) == 2


def test_check_human_output_lists_structural_summary(tmp_path: Path) -> None:
    provider, provenance, spec = _write_fixture(tmp_path)
    bundle = tmp_path / "bundle"
    initialize_static_bundle(provider, provenance, spec, bundle, repo_root=ROOT)
    result = _run_module(["check", str(bundle)])
    assert result.returncode == 0
    assert "Structural  PASS" in result.stdout
    assert "Overall  PASS" in result.stdout
