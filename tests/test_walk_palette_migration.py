"""Behavioral proof for dwarf walk palette migration (issue #177)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.final_polish import check_bundle, finalize_bundle
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import evaluate_identity_lock
from pipeline.palette_quantize import load_master_palette, quantize_cells

ROOT = Path(__file__).resolve().parents[1]
WALK_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "walk"
WALK_POLISHED = WALK_BUNDLE / "polished"
POLISHED_ROLES_JSON = WALK_BUNDLE / "polished-roles.json"
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"

PALETTE_EXACT_IDENTITY_SHA = (
    "707442d156b96b862f801a5e81febdbb5ca47c82e0d3587dffc255c7e02b4357"
)

PRE_SLICE_ALPHA_SHA256 = {
    0: "9b0caba4d85301d1c205756e593edfe89530e8d16b5bbf41896a0d0649f34da2",
    1: "1533f5d7a93e39ed1681cd0aaea63ba1c24622e62f8cc8f0648c76ae567d2b8a",
    2: "0308a49ef552dbef0f95c9fdd3460b9f9ef490b82b76f047464423a59367c288",
    3: "a6fe1f3e5e091957567f43f432d8bb2525e31442b4dd6e8feb5c62fed84854f5",
}
PRE_SLICE_OCCUPANCY = [0.40, 0.39, 0.37, 0.39]
PRE_SLICE_BBOX = {
    0: (2, 14, 7, 23),
    1: (2, 14, 7, 23),
    2: (1, 14, 7, 23),
    3: (1, 13, 7, 23),
}

PRE_CLEANUP_CELL_SHA256 = {
    0: "8ee40aedf1f360d412a6775e095b5fc98ca4853b09ce9aed20d56881043c97fb",
    1: "35abfcc824188249820d9a7226a3eff795fe5f5bd6e5d88220edc45e09b3cb94",
    2: "5f951e2cff54bc28af59a8935709f5a11220946dba832ad7e0000379adf6ed22",
    3: "fd895ef15503b2c72626cc75c14f80841f383d73898ab71da74cd689ffcc9570",
}


def _palette_color_set() -> set[tuple[int, int, int]]:
    palette = load_master_palette(MASTER_PALETTE_PATH)
    colors: set[tuple[int, int, int]] = set()
    for role_colors in palette.role_colors.values():
        colors.update(role_colors)
    return colors


def _alpha_sha256(path: Path) -> str:
    with Image.open(path) as image:
        alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    return hashlib.sha256(alpha.tobytes()).hexdigest()


def _occupancy(path: Path) -> float:
    with Image.open(path) as image:
        alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    return float(np.count_nonzero(alpha)) / (16 * 24)


def _bounding_box(path: Path) -> tuple[int, int, int, int]:
    cells = read_cells(path)
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                xs.append(x)
                ys.append(y)
    return min(xs), max(xs), min(ys), max(ys)


def _cell_content_sha256(cells: list[list[tuple[int, int, int] | None]]) -> str:
    payload = json.dumps(cells, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_role_assignment(cells_doc: dict[str, str]) -> dict[tuple[int, int], str]:
    return {
        (int(x_text), int(y_text)): role
        for key, role in cells_doc.items()
        for x_text, y_text in [key.split(",", maxsplit=1)]
    }


def _frame_roles_entry(doc: dict[str, object], index: int) -> dict[str, object]:
    frames = doc.get("frames")
    assert isinstance(frames, list)
    for entry in frames:
        if isinstance(entry, dict) and entry.get("index") == index:
            return entry
    raise AssertionError(f"missing frame {index} in polished-roles.json")


def test_walk_polished_frames_are_palette_exact() -> None:
    allowed = _palette_color_set()
    for index in range(4):
        cells = read_cells(WALK_POLISHED / f"frame-{index}.png")
        for row in cells:
            for cell in row:
                if cell is not None:
                    assert cell in allowed


def test_walk_polished_frames_preserve_pre_slice_alpha_occupancy_and_bbox() -> None:
    for index in range(4):
        path = WALK_POLISHED / f"frame-{index}.png"
        assert _alpha_sha256(path) == PRE_SLICE_ALPHA_SHA256[index]
        assert _occupancy(path) == pytest.approx(PRE_SLICE_OCCUPANCY[index], abs=0.01)
        assert _bounding_box(path) == PRE_SLICE_BBOX[index]


def test_walk_polished_roles_reproduce_pre_cleanup_rasters() -> None:
    doc = json.loads(POLISHED_ROLES_JSON.read_text(encoding="utf-8"))
    assert doc["schema"] == "polished-roles/0"
    palette = load_master_palette(MASTER_PALETTE_PATH)
    for index in range(4):
        entry = _frame_roles_entry(doc, index)
        source = ROOT / str(entry["source"])
        cells_doc = entry.get("cells")
        assert isinstance(cells_doc, dict)
        role_assignment = _load_role_assignment(cells_doc)
        source_cells = read_cells(source)
        precleanup = quantize_cells(source_cells, palette, role_assignment)
        assert _cell_content_sha256(precleanup) == PRE_CLEANUP_CELL_SHA256[index]


def test_walk_bundle_check_passes_with_palette_exact_identity_lock(tmp_path: Path) -> None:
    bundle = tmp_path / "dwarf-walk"
    shutil.copytree(WALK_BUNDLE, bundle)
    result = check_bundle(bundle)
    assert result.outcome == "PASS"
    assert result.identity_lock is not None
    assert result.identity_lock.outcome == "PASS"
    assert result.identity_lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA
    lock = evaluate_identity_lock(
        [read_cells(WALK_POLISHED / f"frame-{index}.png") for index in range(4)],
        "walk",
        palette_exact=True,
        polished_roles_path=POLISHED_ROLES_JSON,
    )
    assert lock.outcome == "PASS"
    assert lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA


def _strip_finalize_outputs(bundle: Path) -> None:
    """Remove immutable finalize outputs so finalize_bundle can rewrite them."""
    reports = bundle / "reports"
    if reports.is_dir():
        for path in reports.iterdir():
            if path.name != "audit.json":
                path.unlink()
    release = bundle / "release"
    if release.is_dir():
        for path in release.iterdir():
            path.unlink()


def test_walk_finalize_rebinds_release_and_report(tmp_path: Path) -> None:
    bundle = tmp_path / "walk"
    shutil.copytree(WALK_BUNDLE, bundle)
    _strip_finalize_outputs(bundle)
    report_path = finalize_bundle(bundle)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["outcome"] == "PASS"
    assert report["identity_lock"]["outcome"] == "PASS"
    assert report["identity_lock"]["identity_sha256"] == PALETTE_EXACT_IDENTITY_SHA
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    for index in range(4):
        release_path = bundle / "release" / f"frame-{index}.png"
        polished_path = bundle / "polished" / f"frame-{index}.png"
        assert release_path.is_file()
        assert sha256_file(release_path) == sha256_file(polished_path)
