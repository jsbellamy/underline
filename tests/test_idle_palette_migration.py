"""Behavioral proof for dwarf idle palette migration (issue #176)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.final_polish import check_bundle
from pipeline.gate_evidence import sha256_file
from pipeline.palette_quantize import load_master_palette, quantize_cells

ROOT = Path(__file__).resolve().parents[1]
IDLE_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "idle"
IDLE_POLISHED = IDLE_BUNDLE / "polished"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
POLISHED_ROLES_JSON = IDLE_BUNDLE / "polished-roles.json"
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"

# Palette-exact since #179 collapsed the two identities onto the canonical path.
CANONICAL_IDENTITY_SHA = "707442d156b96b862f801a5e81febdbb5ca47c82e0d3587dffc255c7e02b4357"

PRE_SLICE_ALPHA_SHA256 = {
    0: "46be406c2de591036a943d2d5bf2962a4ea82cae62ae1a49222957da92ce2d57",
    1: "370f121df51ee60618bdb16d19158701d7bf6d7305cacc239f8d201cc1926c0a",
    2: "ea868876433f1c3d9aaf61db3d57c26d139cc2ca2c44cea3871a71a98991a391",
    3: "d07b5eca7c9aae3b5e1a92ce8d79451f63c0d8df872b37b247c763d624a4e998",
}
PRE_SLICE_OCCUPANCY = [0.698, 0.701, 0.677, 0.688]

# Frame 0 re-pinned on #300: the glove/haft re-role changed the canonical Frame
# only. Frames 1-3 are untouched, which is the evidence that the re-role stayed
# inside Frame 0 rather than drifting across the idle bundle.
PRE_CLEANUP_CELL_SHA256 = {
    0: "aab388ecd3875e492ce1f147020e638654427b637be61e1d50114b1020f52ecb",
    1: "3a26a19cb46e452aa3dbde29b299158dd0dc133d9c397b4a21718d4c36bdaafe",
    2: "91f818f850044eabb50d6190ce6986920f2a960df6e4917fc1fc8ca39bddaa5d",
    3: "a1bec61b77e2aa6d4bfc6b4d300d013fd395e01b299b888301a95666c824ae76",
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


def test_idle_polished_frames_are_palette_exact_and_frame_zero_matches_identity() -> None:
    allowed = _palette_color_set()
    for index in range(4):
        path = IDLE_POLISHED / f"frame-{index}.png"
        cells = read_cells(path)
        for row in cells:
            for cell in row:
                if cell is not None:
                    assert cell in allowed
    assert (IDLE_POLISHED / "frame-0.png").read_bytes() == IDENTITY_PNG.read_bytes()


def test_idle_polished_frames_preserve_pre_slice_alpha_and_occupancy() -> None:
    for index in range(4):
        path = IDLE_POLISHED / f"frame-{index}.png"
        assert _alpha_sha256(path) == PRE_SLICE_ALPHA_SHA256[index]
        assert _occupancy(path) == pytest.approx(PRE_SLICE_OCCUPANCY[index], abs=0.001)


def test_idle_polished_roles_reproduce_pre_cleanup_rasters() -> None:
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


def test_idle_precleanup_rasters_equal_the_committed_polished_frames() -> None:
    """C4 anchor for the #300 re-role.

    `PRE_CLEANUP_CELL_SHA256` is otherwise a bare pin that has to be re-derived
    from the code every time the role map moves, which cannot disagree with the
    quantizer. The idle bundle carries a zero hand-cleanup delta, so the
    pre-cleanup raster must equal the reviewed committed Frame exactly. That ties
    the pin to the artifact a human approved rather than to the quantizer output.
    """
    doc = json.loads(POLISHED_ROLES_JSON.read_text(encoding="utf-8"))
    palette = load_master_palette(MASTER_PALETTE_PATH)
    for index in range(4):
        entry = _frame_roles_entry(doc, index)
        role_assignment = _load_role_assignment(entry["cells"])
        source_cells = read_cells(ROOT / str(entry["source"]))
        precleanup = quantize_cells(source_cells, palette, role_assignment)
        assert precleanup == read_cells(IDLE_POLISHED / f"frame-{index}.png")


def test_idle_bundle_check_passes_after_palette_migration(tmp_path: Path) -> None:
    bundle = tmp_path / "dwarf-idle"
    shutil.copytree(IDLE_BUNDLE, bundle)
    result = check_bundle(bundle)
    assert result.outcome == "PASS"
    assert result.structural.outcome == "PASS"
    assert result.coherence["outcome"] == "PASS"


def test_identity_json_idle_bundle_matches_disk_and_identity_png_is_palette_exact() -> None:
    declaration = json.loads(IDENTITY_JSON.read_text(encoding="utf-8"))
    identity_png = declaration["identity_png"]
    assert identity_png["sha256"] == CANONICAL_IDENTITY_SHA
    assert sha256_file(IDENTITY_PNG) == CANONICAL_IDENTITY_SHA

    idle_bundle = declaration["idle_bundle"]
    report_path = ROOT / idle_bundle["report_relative_path"]
    assert report_path.is_file()
    assert sha256_file(report_path) == idle_bundle["report_sha256"]
    assert idle_bundle["report_fingerprint"] == report_path.stem

    release_frame_0 = IDLE_BUNDLE / "release" / "frame-0.png"
    assert sha256_file(release_frame_0) == idle_bundle["release_frame_0_sha256"]
    assert idle_bundle["release_frame_0_sha256"] == CANONICAL_IDENTITY_SHA
