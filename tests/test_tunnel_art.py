"""Behavioral proof for pipeline.tunnel_art (issue #416)."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.recovery import MAGENTA
from pipeline.tunnel_art import (
    PACK_SCHEMA,
    SOURCE_SCHEMA,
    TunnelArtError,
    build_tunnel_assets,
    discover_tunnel_bundles,
    parse_tunnel_source,
    recover_tile_sheet_cells,
    verify_tunnel_assets,
)

ROOT = Path(__file__).resolve().parents[1]
STONE = (74, 59, 72)
STONE_LIGHT = (98, 81, 93)
TILE_PITCH = 16
TILE_BORDER_PAD = 2


def _sha256_png(image: Image.Image) -> str:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return sha256_bytes(buf.getvalue())


def _background_sidecar(
    *,
    raw_sha256: str,
    source_resolution: list[int],
    crop_box: list[int],
    crop_size: list[int],
) -> dict[str, object]:
    return {
        "schema": SOURCE_SCHEMA,
        "provider": "test-provider",
        "acquisition_tool": "pytest",
        "prompt": "tunnel background test fixture",
        "raw_sha256": raw_sha256,
        "asset_class": "background",
        "runtime_destination": "src/assets/tunnel/background/test-bg.png",
        "source_resolution": source_resolution,
        "reduction": {
            "crop_box": crop_box,
            "crop_size": crop_size,
            "resample": "NEAREST",
            "runtime_size": [480, 112],
        },
    }


def _tile_sidecar(
    *,
    raw_sha256: str,
    source_resolution: list[int],
    columns: int,
    gutter: int,
    items: list[str],
    cell_w: int = 16,
    cell_h: int = 16,
) -> dict[str, object]:
    return {
        "schema": SOURCE_SCHEMA,
        "provider": "test-provider",
        "acquisition_tool": "pytest",
        "prompt": "tunnel tile-sheet test fixture",
        "raw_sha256": raw_sha256,
        "asset_class": "tile-sheet",
        "runtime_destination": "src/assets/tunnel/tiles/test-tiles",
        "source_resolution": source_resolution,
        "reduction": {
            "cell_w": cell_w,
            "cell_h": cell_h,
            "columns": columns,
            "gutter": gutter,
            "items": items,
            "resample": None,
        },
    }


def _write_png(path: Path, image: Image.Image) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return sha256_file(path)


def _draw_tile_block(
    pixels,
    gx: int,
    gy: int,
    pitch: int,
    rgb: tuple[int, int, int],
    *,
    origin_x: int = TILE_BORDER_PAD,
    origin_y: int = TILE_BORDER_PAD,
) -> None:
    x0 = origin_x + gx * pitch
    y0 = origin_y + gy * pitch
    for y in range(y0, y0 + pitch):
        for x in range(x0, x0 + pitch):
            pixels[x, y] = (*rgb, 255)


def _render_tile_sheet(
    *,
    columns: int,
    gutter: int,
    item_cells: dict[str, list[list[tuple[int, int, int] | None]]],
    item_order: list[str],
    cell_w: int = 16,
    cell_h: int = 16,
    pitch: int = TILE_PITCH,
) -> Image.Image:
    rows = (len(item_order) + columns - 1) // columns
    grid_w = columns * cell_w + (columns - 1) * gutter
    grid_h = rows * cell_h + (rows - 1) * gutter
    image = Image.new(
        "RGBA",
        (grid_w * pitch + TILE_BORDER_PAD * 2, grid_h * pitch + TILE_BORDER_PAD * 2),
        (*MAGENTA, 255),
    )
    pixels = image.load()
    assert pixels is not None
    for index, item_id in enumerate(item_order):
        col = index % columns
        row = index // columns
        origin_gx = col * (cell_w + gutter)
        origin_gy = row * (cell_h + gutter)
        cells = item_cells[item_id]
        for gy in range(cell_h):
            for gx in range(cell_w):
                rgb = cells[gy][gx]
                if rgb is None:
                    continue
                _draw_tile_block(pixels, origin_gx + gx, origin_gy + gy, pitch, rgb)
    return image


def _checker_cells(
    rgb: tuple[int, int, int],
    alt: tuple[int, int, int],
    *,
    cell_w: int = 16,
    cell_h: int = 16,
) -> list[list[tuple[int, int, int] | None]]:
    return [
        [rgb if (x + y) % 2 == 0 else alt for x in range(cell_w)]
        for y in range(cell_h)
    ]


def _fixture_roots(tmp_path: Path) -> tuple[Path, Path]:
    raw_root = tmp_path / "assets-raw" / "tunnel"
    runtime_root = tmp_path / "src" / "assets" / "tunnel"
    raw_root.mkdir(parents=True)
    runtime_root.mkdir(parents=True)
    return raw_root, runtime_root


def test_parse_tile_reduction_accepts_8x8_and_rejects_invalid_cell_dims(tmp_path: Path) -> None:
    raw_path = tmp_path / "ore.png"
    _write_png(raw_path, Image.new("RGBA", (100, 100), (*MAGENTA, 255)))
    raw_sha = sha256_file(raw_path)
    base = _tile_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[100, 100],
        columns=2,
        gutter=1,
        items=["a", "b"],
        cell_w=8,
        cell_h=8,
    )
    source = parse_tunnel_source(base, raw_path)
    reduction = source.reduction
    assert reduction.cell_w == 8
    assert reduction.cell_h == 8

    for bad_w in (0, -1, True, "8", 8.0):
        doc = dict(base)
        doc["reduction"] = dict(base["reduction"])
        doc["reduction"]["cell_w"] = bad_w
        with pytest.raises(TunnelArtError) as exc_info:
            parse_tunnel_source(doc, raw_path)
        assert exc_info.value.reason_code == "invalid_sidecar"

    for bad_h in (0, -1, True, "8", 8.0):
        doc = dict(base)
        doc["reduction"] = dict(base["reduction"])
        doc["reduction"]["cell_h"] = bad_h
        with pytest.raises(TunnelArtError) as exc_info:
            parse_tunnel_source(doc, raw_path)
        assert exc_info.value.reason_code == "invalid_sidecar"


def test_parse_tunnel_source_rejects_missing_required_field(tmp_path: Path) -> None:
    raw_path = tmp_path / "bg.png"
    _write_png(raw_path, Image.new("RGBA", (960, 224), (20, 30, 40, 255)))
    sidecar = _background_sidecar(
        raw_sha256=sha256_file(raw_path),
        source_resolution=[960, 224],
        crop_box=[120, 0, 840, 224],
        crop_size=[720, 224],
    )
    del sidecar["prompt"]
    with pytest.raises(TunnelArtError, match="prompt"):
        parse_tunnel_source(sidecar, raw_path)


def test_discover_tunnel_bundles_reports_orphans(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    bg_dir = raw_root / "background"
    bg_dir.mkdir(parents=True)

    complete_png = Image.new("RGBA", (960, 224), (30, 40, 50, 255))
    complete_raw = bg_dir / "complete.png"
    complete_sha = _write_png(complete_raw, complete_png)
    crop_box = [120, 0, 840, 224]
    complete_sidecar = _background_sidecar(
        raw_sha256=complete_sha,
        source_resolution=[960, 224],
        crop_box=crop_box,
        crop_size=[720, 224],
    )
    (bg_dir / "complete.source.json").write_text(json.dumps(complete_sidecar), encoding="utf-8")

    orphan_png = bg_dir / "orphan-png.png"
    _write_png(orphan_png, Image.new("RGBA", (64, 64), (10, 10, 10, 255)))
    (bg_dir / "orphan-sidecar.source.json").write_text("{}", encoding="utf-8")

    complete, failures = discover_tunnel_bundles(raw_root)
    assert len(complete) == 1
    assert complete[0].key == "complete"
    assert {row.key for row in failures} == {
        "background/orphan-png",
        "background/orphan-sidecar",
    }


def test_build_background_is_byte_identical(tmp_path: Path) -> None:
    raw_root, runtime_root = _fixture_roots(tmp_path)
    bg_dir = raw_root / "background"
    bg_dir.mkdir(parents=True)
    image = Image.new("RGBA", (960, 224), (30, 40, 50, 255))
    for x in range(960):
        for y in range(224):
            image.putpixel((x, y), ((x + y) % 256, 40, 50, 255))
    raw_path = bg_dir / "band.png"
    raw_sha = _write_png(raw_path, image)
    from pipeline.tunnel_art import crop_to_aspect

    cropped, crop_box = crop_to_aspect(image, 480, 112)
    sidecar = _background_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[960, 224],
        crop_box=list(crop_box),
        crop_size=[cropped.width, cropped.height],
    )
    (bg_dir / "band.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    repo_root = tmp_path
    (repo_root / "src" / "assets" / "tunnel").mkdir(parents=True, exist_ok=True)
    sidecar["runtime_destination"] = "src/assets/tunnel/background/band.png"
    (bg_dir / "band.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    first = build_tunnel_assets(repo_root)
    assert first.outcome == "PASS"
    first_bytes = (repo_root / "src/assets/tunnel/background/band.png").read_bytes()
    with Image.open(__import__("io").BytesIO(first_bytes)) as built:
        assert built.size == (480, 112)

    second = build_tunnel_assets(repo_root)
    assert second.outcome == "PASS"
    second_bytes = (repo_root / "src/assets/tunnel/background/band.png").read_bytes()
    assert first_bytes == second_bytes


def test_build_tile_sheet_items_are_16x16_and_match_source(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    tile_dir = raw_root / "tile-sheet"
    tile_dir.mkdir(parents=True)
    item_a = _checker_cells(STONE, STONE_LIGHT)
    item_b = _checker_cells(STONE_LIGHT, STONE)
    sheet = _render_tile_sheet(
        columns=2,
        gutter=1,
        item_cells={"rock-a": item_a, "rock-b": item_b},
        item_order=["rock-a", "rock-b"],
    )
    raw_path = tile_dir / "rocks.png"
    raw_sha = _write_png(raw_path, sheet)
    sidecar = _tile_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[sheet.width, sheet.height],
        columns=2,
        gutter=1,
        items=["rock-a", "rock-b"],
    )
    sidecar["runtime_destination"] = "src/assets/tunnel/tiles/rocks"
    (tile_dir / "rocks.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    report = build_tunnel_assets(tmp_path)
    assert report.outcome == "PASS"

    for item_id, expected_cells in (("rock-a", item_a), ("rock-b", item_b)):
        runtime_path = tmp_path / "src/assets/tunnel/tiles/rocks" / f"{item_id}.png"
        with Image.open(runtime_path) as image:
            assert image.size == (16, 16)
        actual_cells = read_cells(runtime_path, size=(16, 16), label="tile")
        for y in range(16):
            for x in range(16):
                assert actual_cells[y][x] == expected_cells[y][x]


def test_build_tile_sheet_items_are_8x8_and_match_source(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    tile_dir = raw_root / "tile-sheet"
    tile_dir.mkdir(parents=True)
    pitch = 12
    item_a = _checker_cells(STONE, STONE_LIGHT, cell_w=8, cell_h=8)
    item_b = _checker_cells(STONE_LIGHT, STONE, cell_w=8, cell_h=8)
    item_c = _checker_cells(STONE, STONE_LIGHT, cell_w=8, cell_h=8)
    item_d = _checker_cells(STONE_LIGHT, STONE, cell_w=8, cell_h=8)
    sheet = _render_tile_sheet(
        columns=2,
        gutter=1,
        item_cells={"ore-a": item_a, "ore-b": item_b, "ore-c": item_c, "ore-d": item_d},
        item_order=["ore-a", "ore-b", "ore-c", "ore-d"],
        cell_w=8,
        cell_h=8,
        pitch=pitch,
    )
    raw_path = tile_dir / "heap-ore.png"
    raw_sha = _write_png(raw_path, sheet)
    sidecar = _tile_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[sheet.width, sheet.height],
        columns=2,
        gutter=1,
        items=["ore-a", "ore-b", "ore-c", "ore-d"],
        cell_w=8,
        cell_h=8,
    )
    sidecar["runtime_destination"] = "src/assets/tunnel/tiles/heap-ore"
    (tile_dir / "heap-ore.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    report = build_tunnel_assets(tmp_path)
    assert report.outcome == "PASS"

    for item_id, expected_cells in (
        ("ore-a", item_a),
        ("ore-b", item_b),
        ("ore-c", item_c),
        ("ore-d", item_d),
    ):
        runtime_path = tmp_path / "src/assets/tunnel/tiles/heap-ore" / f"{item_id}.png"
        with Image.open(runtime_path) as image:
            assert image.size == (8, 8)
        actual_cells = read_cells(runtime_path, size=(8, 8), label="tile")
        for y in range(8):
            for x in range(8):
                assert actual_cells[y][x] == expected_cells[y][x]

    verify_report = verify_tunnel_assets(tmp_path)
    assert verify_report.outcome == "PASS"


def test_recover_tile_sheet_cells_rejects_axis_stretched_raw(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    tile_dir = raw_root / "tile-sheet"
    tile_dir.mkdir(parents=True)
    sheet = _render_tile_sheet(
        columns=2,
        gutter=1,
        item_cells={
            "a": _checker_cells(STONE, STONE_LIGHT),
            "b": _checker_cells(STONE_LIGHT, STONE),
        },
        item_order=["a", "b"],
    )
    stretched = sheet.resize((sheet.width, sheet.height + 40), Image.NEAREST)
    raw_path = tile_dir / "stretched.png"
    raw_sha = _write_png(raw_path, stretched)
    sidecar = _tile_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[stretched.width, stretched.height],
        columns=2,
        gutter=1,
        items=["a", "b"],
    )
    (tile_dir / "stretched.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    source = parse_tunnel_source(sidecar, raw_path)
    with pytest.raises(TunnelArtError) as exc_info:
        recover_tile_sheet_cells(raw_path, source.reduction)
    assert exc_info.value.reason_code == "geometry_mismatch"
    assert "pitch" in str(exc_info.value).lower()


def test_verify_fails_on_mutated_runtime_and_emits_report(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    bg_dir = raw_root / "background"
    bg_dir.mkdir(parents=True)
    image = Image.new("RGBA", (960, 224), (30, 40, 50, 255))
    raw_path = bg_dir / "band.png"
    raw_sha = _write_png(raw_path, image)
    from pipeline.tunnel_art import crop_to_aspect

    cropped, crop_box = crop_to_aspect(image, 480, 112)
    sidecar = _background_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[960, 224],
        crop_box=list(crop_box),
        crop_size=[cropped.width, cropped.height],
    )
    sidecar["runtime_destination"] = "src/assets/tunnel/background/band.png"
    (bg_dir / "band.source.json").write_text(json.dumps(sidecar), encoding="utf-8")
    build_tunnel_assets(tmp_path)

    runtime_path = tmp_path / "src/assets/tunnel/background/band.png"
    runtime_path.write_bytes(runtime_path.read_bytes() + b"x")

    report = verify_tunnel_assets(tmp_path)
    assert report.outcome == "FAIL"
    failed = [row for row in report.bundles if row.outcome == "FAIL"]
    assert any(row.key == "background/band" for row in failed)
    payload = report.to_dict()
    assert payload["schema"] == "tunnel-art-report/0"
    row = next(row for row in payload["bundles"] if row["key"] == "background/band")
    assert row["asset_class"] == "background"
    assert row["raw_sha256"] == raw_sha
    assert row["runtime_sha256"]
    assert row["reason"]


def test_verify_pass_emits_report_with_required_fields(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    bg_dir = raw_root / "background"
    bg_dir.mkdir(parents=True)
    image = Image.new("RGBA", (960, 224), (30, 40, 50, 255))
    raw_path = bg_dir / "band.png"
    raw_sha = _write_png(raw_path, image)
    from pipeline.tunnel_art import crop_to_aspect

    cropped, crop_box = crop_to_aspect(image, 480, 112)
    sidecar = _background_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[960, 224],
        crop_box=list(crop_box),
        crop_size=[cropped.width, cropped.height],
    )
    sidecar["runtime_destination"] = "src/assets/tunnel/background/band.png"
    (bg_dir / "band.source.json").write_text(json.dumps(sidecar), encoding="utf-8")
    build_tunnel_assets(tmp_path)

    report = verify_tunnel_assets(tmp_path)
    assert report.outcome == "PASS"
    row = report.to_dict()["bundles"][0]
    assert set(row) == {"key", "asset_class", "outcome", "raw_sha256", "runtime_sha256", "reason"}
    assert row["outcome"] == "PASS"
    assert row["reason"] is None


def test_build_writes_manifest_hash_binding(tmp_path: Path) -> None:
    raw_root, _runtime_root = _fixture_roots(tmp_path)
    bg_dir = raw_root / "background"
    bg_dir.mkdir(parents=True)
    image = Image.new("RGBA", (960, 224), (30, 40, 50, 255))
    raw_path = bg_dir / "band.png"
    raw_sha = _write_png(raw_path, image)
    from pipeline.tunnel_art import crop_to_aspect

    cropped, crop_box = crop_to_aspect(image, 480, 112)
    sidecar = _background_sidecar(
        raw_sha256=raw_sha,
        source_resolution=[960, 224],
        crop_box=list(crop_box),
        crop_size=[cropped.width, cropped.height],
    )
    sidecar["runtime_destination"] = "src/assets/tunnel/background/band.png"
    (bg_dir / "band.source.json").write_text(json.dumps(sidecar), encoding="utf-8")

    build_tunnel_assets(tmp_path)
    manifest = json.loads((tmp_path / "src/assets/tunnel/manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == PACK_SCHEMA
    entry = manifest["entries"][0]
    runtime_path = tmp_path / entry["relative_path"]
    assert entry["sha256"] == sha256_file(runtime_path)
    assert entry["source_sha256"] == raw_sha
    assert entry["source_relative_path"] == "assets-raw/tunnel/background/band.png"
