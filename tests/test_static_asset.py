"""Behavioral proof for pipeline.static_asset (issue #105)."""

from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from pipeline.gate_evidence import sha256_file
from pipeline.recovery import MAGENTA
from pipeline.static_asset import (
    BUNDLE_SCHEMA,
    REPORT_SCHEMA,
    SPEC_SCHEMA,
    BundleExistsError,
    InitializationRejectedError,
    InvalidBundleError,
    InvalidSpecError,
    check_static_bundle,
    expected_grid_size,
    finalize_static_bundle,
    initialize_static_bundle,
    load_static_sheet_spec,
    parse_static_sheet_spec,
    recover_static_sheet_cells,
    slice_static_item,
)
from pipeline.strip import Cell

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
PALETTE_SHA = sha256_file(PALETTE_PATH)
STONE = (74, 59, 72)
STONE_LIGHT = (98, 81, 93)
PITCH = 24
BORDER_PAD = 2


def _draw_block(
    px,
    gx: int,
    gy: int,
    pitch: int,
    rgb: tuple[int, int, int],
    *,
    origin_x: int = BORDER_PAD,
    origin_y: int = BORDER_PAD,
) -> None:
    x0 = origin_x + gx * pitch
    y0 = origin_y + gy * pitch
    for y in range(y0, y0 + pitch):
        for x in range(x0, x0 + pitch):
            px[x, y] = (*rgb, 255)


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
    img_w = grid_w * PITCH + BORDER_PAD * 2
    img_h = grid_h * PITCH + BORDER_PAD * 2
    image = Image.new("RGBA", (img_w, img_h), (*MAGENTA, 255))
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


def _item_block(rgb: tuple[int, int, int], cell_w: int, cell_h: int) -> list[list[Cell]]:
    alt = STONE_LIGHT if rgb == STONE else STONE
    return [
        [rgb if (x + y) % 2 == 0 else alt for x in range(cell_w)]
        for y in range(cell_h)
    ]


def _base_spec_doc(
    *,
    items: list[dict[str, object]] | None = None,
    columns: int = 2,
    rows: int = 1,
    cell_w: int = 4,
    cell_h: int = 4,
    gutter: int = 2,
    spec_id: str = "test-tiles",
) -> dict[str, object]:
    if items is None:
        items = [
            {"id": "tile-a", "index": 0, "release_path": "tiles/tile-a.png"},
            {"id": "tile-b", "index": 1, "release_path": "tiles/tile-b.png"},
        ]
    return {
        "schema": SPEC_SCHEMA,
        "id": spec_id,
        "cell_w": cell_w,
        "cell_h": cell_h,
        "columns": columns,
        "rows": rows,
        "gutter": gutter,
        "master_palette": {
            "path": "assets/palettes/first-room.json",
            "sha256": PALETTE_SHA,
        },
        "items": items,
    }


def _write_spec(tmp_path: Path, doc: dict[str, object]) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def _write_provider_fixture(
    tmp_path: Path,
    *,
    item_cells: dict[int, list[list[Cell]]] | None = None,
    columns: int = 2,
    rows: int = 1,
    cell_w: int = 4,
    cell_h: int = 4,
    gutter: int = 2,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    if item_cells is None:
        item_cells = {
            0: _item_block(STONE, cell_w, cell_h),
            1: _item_block(STONE_LIGHT, cell_w, cell_h),
        }
    provider = tmp_path / "sheet.png"
    image = _render_static_sheet(
        cell_w=cell_w,
        cell_h=cell_h,
        columns=columns,
        rows=rows,
        gutter=gutter,
        item_cells=item_cells,
    )
    image.save(provider)
    provenance = tmp_path / "sheet.source.json"
    provenance.write_text(
        json.dumps(
            {
                "prompt": "test static sheet",
                "provider": "pytest",
                "raw_sha256": sha256_file(provider),
                "master_palette_id": "first-room",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return provider, provenance


def _init_bundle(tmp_path: Path) -> Path:
    provider, provenance = _write_provider_fixture(tmp_path)
    spec_path = _write_spec(tmp_path, _base_spec_doc())
    bundle = tmp_path / "bundle"
    initialize_static_bundle(provider, provenance, spec_path, bundle, repo_root=ROOT)
    return bundle


def _load_item_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _set_opaque_rgb(path: Path, x: int, y: int, rgb: tuple[int, int, int]) -> None:
    image = _load_item_rgba(path)
    pixels = image.load()
    assert pixels is not None
    pixels[x, y] = (*rgb, 255)
    image.save(path)


def _set_alpha(path: Path, x: int, y: int, alpha: int) -> None:
    image = _load_item_rgba(path)
    pixels = image.load()
    assert pixels is not None
    r, g, b, _ = pixels[x, y]
    pixels[x, y] = (r, g, b, alpha)
    image.save(path)


def _bundle_tree(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


# --- C1 specification tests ---


def test_spec_accepts_valid_layout(tmp_path: Path) -> None:
    spec_path = _write_spec(tmp_path, _base_spec_doc())
    spec = load_static_sheet_spec(spec_path, repo_root=ROOT)
    assert spec.id == "test-tiles"
    assert expected_grid_size(spec) == (10, 4)


def test_spec_rejects_duplicate_index(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[
            {"id": "tile-a", "index": 0, "release_path": "tiles/a.png"},
            {"id": "tile-b", "index": 0, "release_path": "tiles/b.png"},
        ]
    )
    with pytest.raises(InvalidSpecError, match="duplicate item index"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_rejects_duplicate_id(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[
            {"id": "tile-a", "index": 0, "release_path": "tiles/a.png"},
            {"id": "tile-a", "index": 1, "release_path": "tiles/b.png"},
        ]
    )
    with pytest.raises(InvalidSpecError, match="duplicate item id"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_rejects_duplicate_release_path(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[
            {"id": "tile-a", "index": 0, "release_path": "tiles/same.png"},
            {"id": "tile-b", "index": 1, "release_path": "tiles/same.png"},
        ]
    )
    with pytest.raises(InvalidSpecError, match="duplicate release_path"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_rejects_index_out_of_bounds(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[{"id": "tile-a", "index": 2, "release_path": "tiles/a.png"}],
        columns=2,
        rows=1,
    )
    with pytest.raises(InvalidSpecError, match="outside grid slots"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_rejects_holes_before_last_item(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[
            {"id": "tile-a", "index": 0, "release_path": "tiles/a.png"},
            {"id": "tile-c", "index": 2, "release_path": "tiles/c.png"},
        ],
        columns=2,
        rows=2,
    )
    with pytest.raises(InvalidSpecError, match="holes"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_allows_trailing_unused_cells(tmp_path: Path) -> None:
    doc = _base_spec_doc(
        items=[{"id": "tile-a", "index": 0, "release_path": "tiles/a.png"}],
        columns=2,
        rows=2,
    )
    spec = parse_static_sheet_spec(doc, repo_root=ROOT)
    assert len(spec.items) == 1


def test_spec_rejects_bad_palette_path(tmp_path: Path) -> None:
    doc = _base_spec_doc()
    doc["master_palette"] = {"path": "missing/palette.json", "sha256": "0" * 64}
    with pytest.raises(InvalidSpecError, match="does not exist"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_rejects_palette_hash_mismatch(tmp_path: Path) -> None:
    doc = _base_spec_doc()
    doc["master_palette"]["sha256"] = "0" * 64
    with pytest.raises(InvalidSpecError, match="sha256 does not match"):
        parse_static_sheet_spec(doc, repo_root=ROOT)


def test_spec_row_major_traversal_matches_slice(tmp_path: Path) -> None:
    provider, _ = _write_provider_fixture(
        tmp_path,
        columns=2,
        rows=2,
        item_cells={
            0: _item_block(STONE, 4, 4),
            1: _item_block(STONE_LIGHT, 4, 4),
            2: _item_block((74, 59, 72), 4, 4),
            3: _item_block((98, 81, 93), 4, 4),
        },
    )
    spec = parse_static_sheet_spec(
        _base_spec_doc(
            columns=2,
            rows=2,
            items=[
                {"id": "a", "index": 0, "release_path": "a.png"},
                {"id": "b", "index": 1, "release_path": "b.png"},
                {"id": "c", "index": 2, "release_path": "c.png"},
                {"id": "d", "index": 3, "release_path": "d.png"},
            ],
        ),
        repo_root=ROOT,
    )
    cells, _ = recover_static_sheet_cells(provider, spec)
    sliced = slice_static_item(cells, spec, 2)
    assert len(sliced) == spec.cell_h
    assert len(sliced[0]) == spec.cell_w
    assert sliced[0][0] in {STONE, STONE_LIGHT}


# --- C2 initialization tests ---


def test_initialize_creates_hash_bound_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert (bundle / "provider" / "source.png").is_file()
    assert (bundle / "provider" / "source.source.json").is_file()
    assert (bundle / "spec.json").is_file()
    assert (bundle / "palette.json").is_file()
    assert (bundle / "draft" / "tile-a.png").is_file()
    assert (bundle / "polished" / "tile-a.png").is_file()
    assert sha256_file(bundle / "palette.json") == manifest["master_palette"]["sha256"]


def test_initialize_slices_items_to_declared_dimensions(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    with Image.open(bundle / "draft" / "tile-a.png") as image:
        assert image.size == (4, 4)
        assert image.mode == "RGBA"
    with Image.open(bundle / "draft" / "tile-b.png") as image:
        assert image.size == (4, 4)


def test_initialize_slices_correct_grid_slots(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    spec = load_static_sheet_spec(bundle / "spec.json", repo_root=ROOT)
    cells, _ = recover_static_sheet_cells(bundle / "provider" / "source.png", spec)
    expected_a = slice_static_item(cells, spec, 0)
    expected_b = slice_static_item(cells, spec, 1)

    def cells_from_png(path: Path) -> list[list[Cell]]:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            width, height = rgba.size
            pixels = rgba.load()
            assert pixels is not None
            out: list[list[Cell]] = []
            for y in range(height):
                row: list[Cell] = []
                for x in range(width):
                    r, g, b, a = pixels[x, y]
                    row.append(None if a == 0 else (int(r), int(g), int(b)))
                out.append(row)
            return out

    bundled_a = cells_from_png(bundle / "draft" / "tile-a.png")
    bundled_b = cells_from_png(bundle / "draft" / "tile-b.png")

    assert bundled_a == expected_a
    assert bundled_b == expected_b
    assert bundled_a != bundled_b
    assert bundled_a[0][0] == STONE
    assert bundled_b[0][0] == STONE_LIGHT


def test_initialize_rejects_invalid_provider(tmp_path: Path) -> None:
    provider = tmp_path / "bad.png"
    provider.write_bytes(b"not a png")
    provenance = tmp_path / "bad.source.json"
    provenance.write_text(json.dumps({"raw_sha256": sha256_file(provider)}) + "\n")
    spec_path = _write_spec(tmp_path, _base_spec_doc())
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError):
        initialize_static_bundle(provider, provenance, spec_path, bundle, repo_root=ROOT)
    assert not bundle.exists()


def test_initialize_cleans_up_on_geometry_mismatch(tmp_path: Path) -> None:
    provider, provenance = _write_provider_fixture(
        tmp_path,
        columns=1,
        rows=1,
        item_cells={0: _item_block(STONE, 4, 4)},
    )
    spec_path = _write_spec(tmp_path, _base_spec_doc(columns=2, rows=1))
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError, match="geometry mismatch"):
        initialize_static_bundle(provider, provenance, spec_path, bundle, repo_root=ROOT)
    assert not bundle.exists()
    assert _bundle_tree(tmp_path) == {
        "sheet.png",
        "sheet.source.json",
        "spec.json",
    }


def test_initialize_refuses_existing_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    provider, provenance = _write_provider_fixture(tmp_path / "again")
    spec_path = _write_spec(tmp_path / "again", _base_spec_doc())
    with pytest.raises(BundleExistsError):
        initialize_static_bundle(provider, provenance, spec_path, bundle, repo_root=ROOT)


def test_draft_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    draft = bundle / "draft" / "tile-a.png"
    with Image.open(draft) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        pixels[0, 0] = (17, 23, 32, 255)
        rgba.save(draft)
    with pytest.raises(InvalidBundleError, match="draft item hash mismatch"):
        check_static_bundle(bundle)


def test_provider_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    provider = bundle / "provider" / "source.png"
    with Image.open(provider) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        pixels[0, 0] = (0, 0, 0, 255)
        rgba.save(provider)
    with pytest.raises(InvalidBundleError, match="provider hash does not match"):
        check_static_bundle(bundle)


# --- C3 structural check tests ---


def test_check_passes_valid_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = check_static_bundle(bundle)
    assert result.outcome == "PASS"
    assert result.structural.pass_ is True
    assert result.delta.total_edits == 0


def test_check_reports_changed_cells(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "tile-a.png"
    _set_opaque_rgb(polished, 0, 0, STONE_LIGHT)
    result = check_static_bundle(bundle)
    assert result.outcome == "PASS"
    assert result.delta.total_edits == 1
    assert result.delta.edits[0].item_id == "tile-a"


def test_check_fails_wrong_mode(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    path = bundle / "polished" / "tile-a.png"
    with Image.open(path) as image:
        image.convert("RGB").save(path)
    with pytest.raises(InvalidBundleError, match="RGBA"):
        check_static_bundle(bundle)


def test_check_fails_wrong_size(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    path = bundle / "polished" / "tile-a.png"
    with Image.open(path) as image:
        resized = image.resize((5, 4))
        resized.save(path)
    with pytest.raises(InvalidBundleError, match="4x4"):
        check_static_bundle(bundle)


def test_check_fails_non_binary_alpha(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    _set_alpha(bundle / "polished" / "tile-a.png", 0, 0, 128)
    with pytest.raises(InvalidBundleError, match="non-binary alpha"):
        check_static_bundle(bundle)


def test_check_fails_palette_violation(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    _set_opaque_rgb(bundle / "polished" / "tile-a.png", 0, 0, (1, 2, 3))
    result = check_static_bundle(bundle)
    assert result.outcome == "FAIL"
    assert any(v.code == "palette_violation" for v in result.structural.violations)


def test_check_fails_alpha_mask_change(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "tile-a.png"
    image = _load_item_rgba(polished)
    pixels = image.load()
    assert pixels is not None
    pixels[0, 0] = (0, 0, 0, 0)
    image.save(polished)
    result = check_static_bundle(bundle)
    assert result.outcome == "FAIL"
    assert any(v.code == "alpha_mismatch" for v in result.structural.violations)


def test_check_fails_missing_polished_item(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    (bundle / "polished" / "tile-b.png").unlink()
    with pytest.raises(InvalidBundleError, match="missing logical item"):
        check_static_bundle(bundle)


def test_check_ignores_extra_polished_item(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    shutil.copy2(bundle / "polished" / "tile-a.png", bundle / "polished" / "extra.png")
    result = check_static_bundle(bundle)
    assert result.outcome == "PASS"


# --- C4 finalize tests ---


def test_finalize_writes_release_only_on_pass(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    report_path, release_paths = finalize_static_bundle(bundle)
    assert report_path.is_file()
    assert (bundle / "release" / "tiles" / "tile-a.png").is_file()
    assert len(release_paths) == 2


def test_finalize_report_is_immutable(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    report_path, _ = finalize_static_bundle(bundle)
    payload = json.loads(report_path.read_text())
    assert payload["schema"] == REPORT_SCHEMA
    report_path_again, _ = finalize_static_bundle(bundle)
    assert report_path_again == report_path


def test_finalize_refuses_conflicting_release_bytes(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    finalize_static_bundle(bundle)
    conflict = bundle / "release" / "tiles" / "tile-a.png"
    conflict.write_bytes(b"conflict")
    with pytest.raises(InvalidBundleError, match="release item conflict"):
        finalize_static_bundle(bundle)


def test_finalize_does_not_release_on_fail(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    _set_opaque_rgb(bundle / "polished" / "tile-a.png", 0, 0, (1, 2, 3))
    report_path, release_paths = finalize_static_bundle(bundle)
    assert report_path.is_file()
    assert release_paths == []
    assert not (bundle / "release").exists()


def test_initialize_bundle_leaves_no_item_staging_directory(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    staging_dirs = [
        path
        for path in bundle.rglob("*")
        if path.is_dir() and path.name == ".item-staging"
    ]
    assert staging_dirs == []


def test_static_asset_has_no_pil_dependency() -> None:
    from pipeline import static_asset

    source = inspect.getsource(static_asset)
    assert "PIL" not in source
