"""Behavioral proof for dwarf swing palette migration (issue #178)."""

from __future__ import annotations

import hashlib
import json
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
SWING_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "swing"
SWING_POLISHED = SWING_BUNDLE / "polished"
POLISHED_ROLES_JSON = SWING_BUNDLE / "polished-roles.json"
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"

PALETTE_EXACT_IDENTITY_SHA = (
    "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
)

PRE_SLICE_ALPHA_SHA256 = {
    0: "1a8f62d55229801f2e013787a3edc6b3ee27840d2a4b08583bd8199401cae942",
    1: "35ffe138238c92a98d7d3551ba97eab118d205af12b5d4feaffb1eb38e58b1c0",
    2: "5dd2c12582f62e71d693115814dbadc5fe538c15414b2cf3ecdac246b5a19a21",
    3: "3bc0a68cbfc879222955136f40eab2daa6104ea2c261b2fef0c1e2103a6aca0d",
}
PRE_SLICE_OCCUPANCY = [0.461, 0.393, 0.401, 0.333]
PRE_SLICE_BBOX = {
    0: (1, 14, 1, 23),
    1: (0, 15, 8, 23),
    2: (0, 15, 9, 23),
    3: (0, 14, 10, 23),
}

PRE_CLEANUP_CELL_SHA256 = {
    0: "778ba92bb3f37fae1f92affd6d4f5ef55fb0d6afecc59ac93267154bc1ffcaad",
    1: "caae16c357f9ef0d38e47f53ab60fdecfdd13558a7f7123e77b05b94a237287e",
    2: "4110a7d28318475777382c8075f24e0e883434d704100dbfb10b860599593c5b",
    3: "13df7373b0dcfbe92191a8cb50cfc6ab0009958236c81b5f03d8740ca595788e",
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


def test_swing_polished_frames_are_palette_exact() -> None:
    allowed = _palette_color_set()
    for index in range(4):
        cells = read_cells(SWING_POLISHED / f"frame-{index}.png")
        for row in cells:
            for cell in row:
                if cell is not None:
                    assert cell in allowed


def test_swing_polished_frames_preserve_pre_slice_alpha_occupancy_and_bbox() -> None:
    for index in range(4):
        path = SWING_POLISHED / f"frame-{index}.png"
        assert _alpha_sha256(path) == PRE_SLICE_ALPHA_SHA256[index]
        assert _occupancy(path) == pytest.approx(PRE_SLICE_OCCUPANCY[index], abs=0.01)
        assert _bounding_box(path) == PRE_SLICE_BBOX[index]


def test_swing_polished_roles_reproduce_pre_cleanup_rasters() -> None:
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


def test_swing_bundle_check_passes_with_palette_exact_identity_lock() -> None:
    result = check_bundle(SWING_BUNDLE)
    assert result.outcome == "PASS"
    assert result.identity_lock is not None
    assert result.identity_lock.outcome == "PASS"
    assert result.identity_lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA
    lock = evaluate_identity_lock(
        [read_cells(SWING_POLISHED / f"frame-{index}.png") for index in range(4)],
        "swing",
        palette_exact=True,
        polished_roles_path=POLISHED_ROLES_JSON,
    )
    assert lock.outcome == "PASS"
    assert lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA


def test_swing_finalize_rebinds_release_and_report() -> None:
    report_path = finalize_bundle(SWING_BUNDLE)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["outcome"] == "PASS"
    assert report["identity_lock"]["outcome"] == "PASS"
    assert report["identity_lock"]["identity_sha256"] == PALETTE_EXACT_IDENTITY_SHA
    for index in range(4):
        release_path = SWING_BUNDLE / "release" / f"frame-{index}.png"
        polished_path = SWING_POLISHED / f"frame-{index}.png"
        assert release_path.is_file()
        assert sha256_file(release_path) == sha256_file(polished_path)
