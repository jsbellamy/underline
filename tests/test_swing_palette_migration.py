"""Behavioral proof for dwarf swing palette migration (issue #178)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pipeline.cell_raster import read_cells
from pipeline.final_polish import BUNDLE_SCHEMA, check_bundle, finalize_bundle
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import evaluate_identity_lock
from pipeline.palette_quantize import load_master_palette
from tests.support.polish_review_fixture import write_passing_reviews

ROOT = Path(__file__).resolve().parents[1]
SWING_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "swing"
SWING_POLISHED = SWING_BUNDLE / "polished"
SWING_PART_MAPS = SWING_BUNDLE / "part-maps"
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
IMMUTABLE_PROVIDER_REPORT = (
    "3bcc86581abdabf943d89b9b5c36eddf5ffae25c873f76ccaf34d3584661499e.json"
)

PALETTE_EXACT_IDENTITY_SHA = (
    "707442d156b96b862f801a5e81febdbb5ca47c82e0d3587dffc255c7e02b4357"
)

CELL_AUTHORED_POLISHED_SHA256 = {
    0: "11e74c1780c58594782e74d8c2632f6b979559f2e318cb7b77548a5b046d0ae9",
    1: "783f6e3fbd5edb5c37ff971bbf7b80b93b3f5d9aa51c9d1186042b087ff01cb7",
    2: "d9ded5b48ad485626cd9569a5284f2dae01414855a4e34a595eadf756e15e62d",
    3: "a8d23ef0f703d51846c50024190b75b1aa672984501d7fc0594f21a31cc00bae",
}


def _palette_color_set() -> set[tuple[int, int, int]]:
    palette = load_master_palette(MASTER_PALETTE_PATH)
    colors: set[tuple[int, int, int]] = set()
    for role_colors in palette.role_colors.values():
        colors.update(role_colors)
    return colors


def test_swing_polished_frames_are_palette_exact() -> None:
    allowed = _palette_color_set()
    for index in range(4):
        cells = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
        for row in cells:
            for cell in row:
                if cell is not None:
                    assert cell in allowed


def test_swing_cell_authored_polished_frame_digests_pinned() -> None:
    manifest = json.loads((SWING_BUNDLE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["generation_mode"] == "cell-author"
    for index, expected in CELL_AUTHORED_POLISHED_SHA256.items():
        path = SWING_POLISHED / f"frame-{index}.png"
        assert sha256_file(path) == expected


def _part_cells_from_doc(part_map_doc: dict[str, object], part_id: str) -> set[tuple[int, int]]:
    parts = part_map_doc["parts"]
    assert isinstance(parts, dict)
    part = parts[part_id]
    assert isinstance(part, dict)
    cells = part["cells"]
    assert isinstance(cells, list)
    return {tuple(map(int, key.split(","))) for key in cells}


def test_swing_checked_in_part_maps_cover_frames_and_loader_invariants() -> None:
    """C6: checked-in part maps are exclusive, complete, and honor #300 role/part bindings."""
    palette = load_master_palette(MASTER_PALETTE_PATH)
    for frame_index in range(4):
        cells = read_cells(SWING_POLISHED / f"frame-{frame_index}.png", size=(24, 24))
        part_map_doc = json.loads(
            (SWING_PART_MAPS / f"frame-{frame_index}.json").read_text(encoding="utf-8")
        )
        opaque = {
            (x, y) for y, row in enumerate(cells) for x, cell in enumerate(row) if cell is not None
        }
        claimed: set[tuple[int, int]] = set()
        for part in part_map_doc["parts"].values():
            for key in part["cells"]:
                cell = tuple(map(int, key.split(",")))
                assert cell not in claimed
                claimed.add(cell)
        assert claimed == opaque

        tool_cells = _part_cells_from_doc(part_map_doc, "tool_head") | _part_cells_from_doc(
            part_map_doc, "tool_handle"
        )
        hand_cells = _part_cells_from_doc(part_map_doc, "hand_near") | _part_cells_from_doc(
            part_map_doc, "hand_far"
        )
        head_face_cells = _part_cells_from_doc(part_map_doc, "head_face")
        stone_colors = frozenset(palette.role_colors["stone"])
        skin_colors = frozenset(palette.role_colors["skin"])
        stone_cells = {
            (x, y)
            for y, row in enumerate(cells)
            for x, cell in enumerate(row)
            if cell in stone_colors
        }
        skin_cells = {
            (x, y)
            for y, row in enumerate(cells)
            for x, cell in enumerate(row)
            if cell in skin_colors
        }
        assert stone_cells == tool_cells
        assert skin_cells - head_face_cells == hand_cells


def test_swing_bundle_check_passes_with_palette_exact_identity_lock(tmp_path: Path) -> None:
    bundle = tmp_path / "dwarf-swing"
    shutil.copytree(SWING_BUNDLE, bundle)
    result = check_bundle(bundle)
    assert result.outcome == "PASS"
    assert result.identity_lock is not None
    assert result.identity_lock.outcome == "PASS"
    assert result.identity_lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA
    static_gate = result.coherence.get("gate_outcomes", {}).get("static_silhouette_pass")
    assert static_gate is not None
    assert static_gate["outcome"] == "REVIEW"
    lock = evaluate_identity_lock(
        [read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24)) for index in range(4)],
        "swing",
    )
    assert lock.outcome == "PASS"
    assert lock.identity_sha256 == PALETTE_EXACT_IDENTITY_SHA


def _strip_finalize_outputs(bundle: Path) -> None:
    """Remove immutable finalize outputs so finalize_bundle can rewrite them."""
    reports = bundle / "reports"
    if reports.is_dir():
        for path in reports.iterdir():
            if path.name != "audit.json" and path.name != IMMUTABLE_PROVIDER_REPORT:
                path.unlink()
    reviews = bundle / "reviews"
    if reviews.is_dir():
        shutil.rmtree(reviews)
    release = bundle / "release"
    if release.is_dir():
        for path in release.iterdir():
            path.unlink()


def test_swing_finalize_rebinds_release_and_report(tmp_path: Path) -> None:
    bundle = tmp_path / "swing"
    shutil.copytree(SWING_BUNDLE, bundle)
    _strip_finalize_outputs(bundle)
    write_passing_reviews(bundle)
    report_path = finalize_bundle(bundle)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["outcome"] == "PASS"
    assert report["identity_lock"]["outcome"] == "PASS"
    assert report["identity_lock"]["identity_sha256"] == PALETTE_EXACT_IDENTITY_SHA
    for index in range(4):
        release_path = bundle / "release" / f"frame-{index}.png"
        polished_path = bundle / "polished" / f"frame-{index}.png"
        assert release_path.is_file()
        assert sha256_file(release_path) == sha256_file(polished_path)
