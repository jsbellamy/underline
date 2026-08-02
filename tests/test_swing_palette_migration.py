"""Behavioral proof for dwarf swing palette migration (issue #178)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pipeline.cell_raster import read_cells
from pipeline.final_polish import check_bundle, finalize_bundle
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import evaluate_identity_lock
from pipeline.palette_quantize import load_master_palette, quantize_cells
from pipeline.strip import DEFAULT_LAYOUT, resolve_class_frame_geometry
from tests.support.polish_review_fixture import write_passing_reviews

ROOT = Path(__file__).resolve().parents[1]
SWING_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "swing"
SWING_POLISHED = SWING_BUNDLE / "polished"
POLISHED_ROLES_JSON = SWING_BUNDLE / "polished-roles.json"
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"

PALETTE_EXACT_IDENTITY_SHA = (
    "707442d156b96b862f801a5e81febdbb5ca47c82e0d3587dffc255c7e02b4357"
)

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


def _cell_content_sha256(cells: list[list[tuple[int, int, int] | None]]) -> str:
    import hashlib

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
        cells = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
        for row in cells:
            for cell in row:
                if cell is not None:
                    assert cell in allowed



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
        embedded = read_cells(source, size=(24, 24))
        origin_x, _ = resolve_class_frame_geometry("swing").canonical_origin
        anchor_w = DEFAULT_LAYOUT.frame_w
        source_cells = [
            [embedded[y][origin_x + x] for x in range(anchor_w)] for y in range(24)
        ]
        precleanup = quantize_cells(source_cells, palette, role_assignment)
        assert _cell_content_sha256(precleanup) == PRE_CLEANUP_CELL_SHA256[index]


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
    # Union normalization (issue #208) plus the re-tuned 0.88 budget: the
    # production reference (worst-pair 0.6886) now PASSes, not the REVIEW the
    # old area-normalized 0.86 boundary produced.
    assert static_gate["outcome"] == "PASS"
    assert static_gate["acceptance_status"] == "UNSEPARATED"
    lock = evaluate_identity_lock(
        [read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24)) for index in range(4)],
        "swing",
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
