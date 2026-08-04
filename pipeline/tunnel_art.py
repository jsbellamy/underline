"""Tunnel scenery acquisition — deterministic build and verify from archived raws."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from pipeline.cell_raster import RasterError, read_cells
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.recovery import MIN_GRID_SCORE, detect_pitch, key, raw_clipping, raw_gates, sample_cells
from pipeline.strip import Cell

SOURCE_SCHEMA = "tunnel-art-source/0"
PACK_SCHEMA = "tunnel-art-pack/0"
REPORT_SCHEMA = "tunnel-art-report/0"

ASSET_CLASSES = ("background", "tile-sheet")
BACKGROUND_RUNTIME_SIZE = (480, 112)
TILE_CELL_SIZE = (16, 16)
TILE_PITCH_PX = 16

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RAW_ROOT_REL = Path("assets-raw") / "tunnel"
_RUNTIME_ROOT_REL = Path("src") / "assets" / "tunnel"
_MANIFEST_REL = _RUNTIME_ROOT_REL / "manifest.json"

_REQUIRED_SOURCE_FIELDS = (
    "provider",
    "acquisition_tool",
    "prompt",
    "raw_sha256",
    "asset_class",
    "runtime_destination",
    "source_resolution",
    "reduction",
)


class TunnelArtError(ValueError):
    """Base error for tunnel art operations."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class TunnelBundleRef:
    asset_class: Literal["background", "tile-sheet"]
    key: str
    raw_path: Path
    sidecar_path: Path


@dataclass(frozen=True)
class BackgroundReduction:
    crop_box: tuple[int, int, int, int]
    crop_size: tuple[int, int]
    resample: Literal["NEAREST"]
    runtime_size: tuple[int, int]


@dataclass(frozen=True)
class TileSheetReduction:
    cell_w: int
    cell_h: int
    columns: int
    gutter: int
    items: tuple[str, ...]
    resample: None


@dataclass(frozen=True)
class TunnelSource:
    provider: str
    acquisition_tool: str
    prompt: str
    raw_sha256: str
    asset_class: Literal["background", "tile-sheet"]
    runtime_destination: str
    source_resolution: tuple[int, int]
    reduction: BackgroundReduction | TileSheetReduction
    raw_path: Path


@dataclass(frozen=True)
class BundleReportRow:
    key: str
    asset_class: str
    outcome: Literal["PASS", "FAIL"]
    raw_sha256: str
    runtime_sha256: str | None
    reason: str | None = None


@dataclass(frozen=True)
class TunnelArtReport:
    outcome: Literal["PASS", "FAIL"]
    bundles: tuple[BundleReportRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": REPORT_SCHEMA,
            "outcome": self.outcome,
            "bundles": [
                {
                    "key": row.key,
                    "asset_class": row.asset_class,
                    "outcome": row.outcome,
                    "raw_sha256": row.raw_sha256,
                    "runtime_sha256": row.runtime_sha256,
                    "reason": row.reason,
                }
                for row in self.bundles
            ],
        }


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TunnelArtError(f"missing or invalid {field}", reason_code="invalid_sidecar")
    return value


def _require_int_list(value: object, field: str, *, length: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise TunnelArtError(f"missing or invalid {field}", reason_code="invalid_sidecar")
    out: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise TunnelArtError(f"missing or invalid {field}", reason_code="invalid_sidecar")
        out.append(item)
    return tuple(out)


def _parse_background_reduction(reduction: object) -> BackgroundReduction:
    if not isinstance(reduction, dict):
        raise TunnelArtError("missing or invalid reduction", reason_code="invalid_sidecar")
    crop_box = _require_int_list(reduction.get("crop_box"), "reduction.crop_box", length=4)
    crop_size = _require_int_list(reduction.get("crop_size"), "reduction.crop_size", length=2)
    resample = reduction.get("resample")
    if resample != "NEAREST":
        raise TunnelArtError("missing or invalid reduction.resample", reason_code="invalid_sidecar")
    runtime_size = _require_int_list(reduction.get("runtime_size"), "reduction.runtime_size", length=2)
    if runtime_size != BACKGROUND_RUNTIME_SIZE:
        raise TunnelArtError(
            f"reduction.runtime_size must be {list(BACKGROUND_RUNTIME_SIZE)}",
            reason_code="invalid_sidecar",
        )
    return BackgroundReduction(
        crop_box=(crop_box[0], crop_box[1], crop_box[2], crop_box[3]),
        crop_size=(crop_size[0], crop_size[1]),
        resample="NEAREST",
        runtime_size=(runtime_size[0], runtime_size[1]),
    )


def _parse_tile_reduction(reduction: object) -> TileSheetReduction:
    if not isinstance(reduction, dict):
        raise TunnelArtError("missing or invalid reduction", reason_code="invalid_sidecar")
    cell_w = reduction.get("cell_w")
    cell_h = reduction.get("cell_h")
    columns = reduction.get("columns")
    gutter = reduction.get("gutter")
    items = reduction.get("items")
    resample = reduction.get("resample")
    if not isinstance(cell_w, int) or isinstance(cell_w, bool) or cell_w != TILE_CELL_SIZE[0]:
        raise TunnelArtError("missing or invalid reduction.cell_w", reason_code="invalid_sidecar")
    if not isinstance(cell_h, int) or isinstance(cell_h, bool) or cell_h != TILE_CELL_SIZE[1]:
        raise TunnelArtError("missing or invalid reduction.cell_h", reason_code="invalid_sidecar")
    if not isinstance(columns, int) or isinstance(columns, bool) or columns <= 0:
        raise TunnelArtError("missing or invalid reduction.columns", reason_code="invalid_sidecar")
    if not isinstance(gutter, int) or isinstance(gutter, bool) or gutter < 0:
        raise TunnelArtError("missing or invalid reduction.gutter", reason_code="invalid_sidecar")
    if not isinstance(items, list) or not items or not all(isinstance(item, str) and item for item in items):
        raise TunnelArtError("missing or invalid reduction.items", reason_code="invalid_sidecar")
    if resample is not None:
        raise TunnelArtError("missing or invalid reduction.resample", reason_code="invalid_sidecar")
    return TileSheetReduction(
        cell_w=cell_w,
        cell_h=cell_h,
        columns=columns,
        gutter=gutter,
        items=tuple(items),
        resample=None,
    )


def parse_tunnel_source(doc: dict[str, Any], raw_path: Path) -> TunnelSource:
    if doc.get("schema") != SOURCE_SCHEMA:
        raise TunnelArtError("missing or invalid schema", reason_code="invalid_sidecar")
    for field in _REQUIRED_SOURCE_FIELDS:
        if field not in doc:
            raise TunnelArtError(f"missing or invalid {field}", reason_code="invalid_sidecar")

    provider = _require_str(doc["provider"], "provider")
    acquisition_tool = _require_str(doc["acquisition_tool"], "acquisition_tool")
    prompt = _require_str(doc["prompt"], "prompt")
    raw_sha256 = _require_str(doc["raw_sha256"], "raw_sha256")
    asset_class = doc["asset_class"]
    if asset_class not in ASSET_CLASSES:
        raise TunnelArtError("missing or invalid asset_class", reason_code="invalid_sidecar")
    runtime_destination = _require_str(doc["runtime_destination"], "runtime_destination")
    source_resolution = _require_int_list(doc["source_resolution"], "source_resolution", length=2)

    actual_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if raw_sha256 != actual_sha:
        raise TunnelArtError(
            f"raw_sha256 mismatch for {raw_path.name}",
            reason_code="hash_mismatch",
        )

    reduction_raw = doc["reduction"]
    if asset_class == "background":
        reduction = _parse_background_reduction(reduction_raw)
    else:
        reduction = _parse_tile_reduction(reduction_raw)

    return TunnelSource(
        provider=provider,
        acquisition_tool=acquisition_tool,
        prompt=prompt,
        raw_sha256=raw_sha256,
        asset_class=asset_class,
        runtime_destination=runtime_destination,
        source_resolution=(source_resolution[0], source_resolution[1]),
        reduction=reduction,
        raw_path=raw_path,
    )


def load_tunnel_source(sidecar_path: Path) -> TunnelSource:
    key = sidecar_path.name[: -len(".source.json")]
    raw_path = sidecar_path.parent / f"{key}.png"
    try:
        doc = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TunnelArtError(f"invalid sidecar JSON: {sidecar_path.name}", reason_code="invalid_sidecar") from exc
    if not isinstance(doc, dict):
        raise TunnelArtError(f"invalid sidecar JSON: {sidecar_path.name}", reason_code="invalid_sidecar")
    return parse_tunnel_source(doc, raw_path)


def crop_to_aspect(
    image: Image.Image,
    target_w: int,
    target_h: int,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    src_w, src_h = image.size
    target_aspect = target_w / target_h
    src_aspect = src_w / src_h
    if src_aspect > target_aspect:
        new_w = int(round(src_h * target_aspect))
        x0 = (src_w - new_w) // 2
        crop_box = (x0, 0, x0 + new_w, src_h)
    else:
        new_h = int(round(src_w / target_aspect))
        y0 = (src_h - new_h) // 2
        crop_box = (0, y0, src_w, y0 + new_h)
    return image.crop(crop_box), crop_box


def build_background_png(raw_path: Path, source: TunnelSource) -> bytes:
    if not isinstance(source.reduction, BackgroundReduction):
        raise TunnelArtError("background build requires background reduction", reason_code="invalid_sidecar")
    with Image.open(raw_path) as opened:
        image = opened.convert("RGBA")
    if image.size != source.source_resolution:
        raise TunnelArtError(
            f"source_resolution mismatch for {raw_path.name}: "
            f"expected {source.source_resolution}, got {image.size}",
            reason_code="resolution_mismatch",
        )
    cropped, crop_box = crop_to_aspect(image, *BACKGROUND_RUNTIME_SIZE)
    expected_box = source.reduction.crop_box
    if crop_box != expected_box:
        raise TunnelArtError(
            f"crop_box mismatch for {raw_path.name}: expected {expected_box}, got {crop_box}",
            reason_code="crop_mismatch",
        )
    if cropped.size != source.reduction.crop_size:
        raise TunnelArtError(
            f"crop_size mismatch for {raw_path.name}: "
            f"expected {source.reduction.crop_size}, got {cropped.size}",
            reason_code="crop_mismatch",
        )
    runtime = cropped.resize(BACKGROUND_RUNTIME_SIZE, Image.NEAREST)
    buf = __import__("io").BytesIO()
    runtime.save(buf, format="PNG")
    return buf.getvalue()


def _expected_tile_grid_size(reduction: TileSheetReduction) -> tuple[int, int]:
    rows = (len(reduction.items) + reduction.columns - 1) // reduction.columns
    grid_w = reduction.columns * reduction.cell_w + (reduction.columns - 1) * reduction.gutter
    grid_h = rows * reduction.cell_h + (rows - 1) * reduction.gutter
    return grid_w, grid_h


def recover_tile_sheet_cells(raw_path: Path, reduction: TileSheetReduction) -> list[list[Cell]]:
    gate_errs = raw_gates(raw_path)
    if gate_errs:
        raise TunnelArtError("; ".join(gate_errs), reason_code="raw_gate_fail")

    clip = raw_clipping(raw_path)
    if clip:
        raise TunnelArtError("; ".join(clip), reason_code="raw_clipping")

    src, fg, bbox = key(raw_path)
    x0, y0, x1, y1 = 0, 0, src.width - 1, src.height - 1
    bbox = (x0, y0, x1, y1)
    pitch_val = float(TILE_PITCH_PX)
    band_lo, band_hi = pitch_val * 0.98, pitch_val * 1.02
    pitch_y_fit = detect_pitch(src, fg, "y", band_lo, band_hi)
    pitch_x_fit = detect_pitch(src, fg, "x", band_lo, band_hi)
    pitch_y = {"pitch": pitch_val, "phase": pitch_y_fit["phase"], "score": pitch_y_fit["score"]}
    pitch_x = {"pitch": pitch_val, "phase": pitch_x_fit["phase"], "score": pitch_x_fit["score"]}
    if pitch_y["score"] < MIN_GRID_SCORE or pitch_x["score"] < MIN_GRID_SCORE:
        raise TunnelArtError(
            f"grid recovery failed for {raw_path.name}: "
            f"x={pitch_x['score']:.3f} y={pitch_y['score']:.3f}",
            reason_code="grid_recovery_fail",
        )

    cells = sample_cells(src, fg, bbox, pitch_x, pitch_y)
    grid_h = len(cells)
    grid_w = len(cells[0]) if cells else 0
    expected_w, expected_h = _expected_tile_grid_size(reduction)
    if grid_w != expected_w or grid_h != expected_h:
        raise TunnelArtError(
            f"sheet geometry mismatch for {raw_path.name}: expected {expected_w}x{expected_h}, got {grid_w}x{grid_h}",
            reason_code="geometry_mismatch",
        )
    return cells


def slice_tile_item(
    cells: list[list[Cell]],
    reduction: TileSheetReduction,
    item_index: int,
) -> list[list[Cell]]:
    col = item_index % reduction.columns
    row = item_index // reduction.columns
    x0 = col * (reduction.cell_w + reduction.gutter)
    y0 = row * (reduction.cell_h + reduction.gutter)
    return [
        list(cells[y][x0 : x0 + reduction.cell_w])
        for y in range(y0, y0 + reduction.cell_h)
    ]


def _cells_to_png_bytes(cells: list[list[Cell]]) -> bytes:
    import io

    tmp = io.BytesIO()
    frame_h = len(cells)
    frame_w = len(cells[0]) if cells else 0
    from pipeline.strip import canonicalize_frame

    logical = canonicalize_frame(cells, frame_w=frame_w, frame_h=frame_h)
    height = len(logical)
    width = len(logical[0]) if logical else 0
    image = Image.new("RGBA", (width, height), (255, 0, 255, 0))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            rgb = logical[y][x]
            if rgb is not None:
                pixels[x, y] = (*rgb, 255)
    image.save(tmp, format="PNG")
    return tmp.getvalue()


def build_tile_sheet_pngs(raw_path: Path, source: TunnelSource) -> dict[str, bytes]:
    if not isinstance(source.reduction, TileSheetReduction):
        raise TunnelArtError("tile-sheet build requires tile-sheet reduction", reason_code="invalid_sidecar")
    reduction = source.reduction
    with Image.open(raw_path) as opened:
        image = opened.convert("RGBA")
    if image.size != source.source_resolution:
        raise TunnelArtError(
            f"source_resolution mismatch for {raw_path.name}: "
            f"expected {source.source_resolution}, got {image.size}",
            reason_code="resolution_mismatch",
        )
    cells = recover_tile_sheet_cells(raw_path, reduction)
    outputs: dict[str, bytes] = {}
    for index, item_id in enumerate(reduction.items):
        item_cells = slice_tile_item(cells, reduction, index)
        outputs[item_id] = _cells_to_png_bytes(item_cells)
    return outputs


def discover_tunnel_bundles(
    raw_root: Path,
) -> tuple[tuple[TunnelBundleRef, ...], tuple[BundleReportRow, ...]]:
    complete: list[TunnelBundleRef] = []
    failures: list[BundleReportRow] = []
    if not raw_root.is_dir():
        return tuple(), tuple()

    sidecar_keys: set[tuple[str, str]] = set()
    png_keys: set[tuple[str, str]] = set()

    for asset_class in ASSET_CLASSES:
        class_dir = raw_root / asset_class
        if not class_dir.is_dir():
            continue
        for sidecar_path in sorted(class_dir.glob("*.source.json")):
            key = sidecar_path.name[: -len(".source.json")]
            sidecar_keys.add((asset_class, key))
            raw_path = class_dir / f"{key}.png"
            if not raw_path.is_file():
                failures.append(
                    BundleReportRow(
                        key=f"{asset_class}/{key}",
                        asset_class=asset_class,
                        outcome="FAIL",
                        raw_sha256="",
                        runtime_sha256=None,
                        reason=f"missing raw PNG for sidecar {sidecar_path.name}",
                    )
                )
                continue
            complete.append(
                TunnelBundleRef(
                    asset_class=asset_class,
                    key=key,
                    raw_path=raw_path,
                    sidecar_path=sidecar_path,
                )
            )
        for raw_path in sorted(class_dir.glob("*.png")):
            key = raw_path.stem
            png_keys.add((asset_class, key))
            sidecar_path = raw_path.with_suffix(".source.json")
            if not sidecar_path.is_file():
                failures.append(
                    BundleReportRow(
                        key=f"{asset_class}/{key}",
                        asset_class=asset_class,
                        outcome="FAIL",
                        raw_sha256=sha256_file(raw_path),
                        runtime_sha256=None,
                        reason=f"missing sidecar for raw {raw_path.name}",
                    )
                )

    complete.sort(key=lambda ref: (ref.asset_class, ref.key))
    failures.sort(key=lambda row: row.key)
    return tuple(complete), tuple(failures)


def _bundle_key(ref: TunnelBundleRef) -> str:
    return f"{ref.asset_class}/{ref.key}"


def _runtime_paths(source: TunnelSource, key: str) -> list[Path]:
    if source.asset_class == "background":
        return [Path(source.runtime_destination)]
    if not isinstance(source.reduction, TileSheetReduction):
        raise TunnelArtError("tile-sheet requires tile-sheet reduction", reason_code="invalid_sidecar")
    base = Path(source.runtime_destination)
    return [base / f"{item_id}.png" for item_id in source.reduction.items]


def _build_bundle_outputs(source: TunnelSource, key: str) -> dict[Path, bytes]:
    if source.asset_class == "background":
        png_bytes = build_background_png(source.raw_path, source)
        return {Path(source.runtime_destination): png_bytes}
    return {
        Path(source.runtime_destination) / f"{item_id}.png": png_bytes
        for item_id, png_bytes in build_tile_sheet_pngs(source.raw_path, source).items()
    }


def build_tunnel_assets(repo_root: Path | None = None) -> TunnelArtReport:
    root = repo_root or _REPO_ROOT
    raw_root = root / _RAW_ROOT_REL
    complete, failures = discover_tunnel_bundles(raw_root)
    rows: list[BundleReportRow] = list(failures)
    manifest_entries: list[dict[str, str]] = []

    for ref in complete:
        bundle_key = _bundle_key(ref)
        try:
            source = load_tunnel_source(ref.sidecar_path)
        except TunnelArtError as exc:
            rows.append(
                BundleReportRow(
                    key=bundle_key,
                    asset_class=ref.asset_class,
                    outcome="FAIL",
                    raw_sha256=sha256_file(ref.raw_path),
                    runtime_sha256=None,
                    reason=str(exc),
                )
            )
            continue

        try:
            outputs = _build_bundle_outputs(source, ref.key)
        except TunnelArtError as exc:
            rows.append(
                BundleReportRow(
                    key=bundle_key,
                    asset_class=ref.asset_class,
                    outcome="FAIL",
                    raw_sha256=source.raw_sha256,
                    runtime_sha256=None,
                    reason=str(exc),
                )
            )
            continue

        source_rel = ref.raw_path.relative_to(root).as_posix()
        for rel_path, png_bytes in sorted(outputs.items(), key=lambda item: item[0].as_posix()):
            dest = root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(png_bytes)
            manifest_entries.append(
                {
                    "relative_path": rel_path.as_posix(),
                    "sha256": sha256_bytes(png_bytes),
                    "source_relative_path": source_rel,
                    "source_sha256": source.raw_sha256,
                }
            )
            rows.append(
                BundleReportRow(
                    key=bundle_key,
                    asset_class=ref.asset_class,
                    outcome="PASS",
                    raw_sha256=source.raw_sha256,
                    runtime_sha256=sha256_bytes(png_bytes),
                    reason=None,
                )
            )

    manifest_entries.sort(key=lambda entry: entry["relative_path"])
    manifest_doc = {
        "schema": PACK_SCHEMA,
        "entries": manifest_entries,
    }
    manifest_path = root / _MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_doc, indent=2, sort_keys=True) + "\n")
    outcome: Literal["PASS", "FAIL"] = "PASS" if all(row.outcome == "PASS" for row in rows) else "FAIL"
    return TunnelArtReport(outcome=outcome, bundles=tuple(rows))


def verify_tunnel_assets(repo_root: Path | None = None) -> TunnelArtReport:
    root = repo_root or _REPO_ROOT
    raw_root = root / _RAW_ROOT_REL
    complete, failures = discover_tunnel_bundles(raw_root)
    rows: list[BundleReportRow] = list(failures)

    for ref in complete:
        bundle_key = _bundle_key(ref)
        try:
            source = load_tunnel_source(ref.sidecar_path)
        except TunnelArtError as exc:
            rows.append(
                BundleReportRow(
                    key=bundle_key,
                    asset_class=ref.asset_class,
                    outcome="FAIL",
                    raw_sha256=sha256_file(ref.raw_path),
                    runtime_sha256=None,
                    reason=str(exc),
                )
            )
            continue

        try:
            expected_outputs = _build_bundle_outputs(source, ref.key)
        except TunnelArtError as exc:
            rows.append(
                BundleReportRow(
                    key=bundle_key,
                    asset_class=ref.asset_class,
                    outcome="FAIL",
                    raw_sha256=source.raw_sha256,
                    runtime_sha256=None,
                    reason=str(exc),
                )
            )
            continue

        bundle_failed = False
        fail_reason: str | None = None
        runtime_sha: str | None = None
        for rel_path, expected_bytes in sorted(expected_outputs.items(), key=lambda item: item[0].as_posix()):
            runtime_path = root / rel_path
            if not runtime_path.is_file():
                bundle_failed = True
                fail_reason = f"missing runtime PNG {rel_path.as_posix()}"
                break
            actual_bytes = runtime_path.read_bytes()
            runtime_sha = sha256_bytes(actual_bytes)
            if source.asset_class == "background":
                with Image.open(__import__("io").BytesIO(actual_bytes)) as image:
                    if image.size != BACKGROUND_RUNTIME_SIZE:
                        bundle_failed = True
                        fail_reason = (
                            f"wrong runtime dimension for {rel_path.as_posix()}: "
                            f"expected {BACKGROUND_RUNTIME_SIZE}, got {image.size}"
                        )
                        break
            else:
                try:
                    read_cells(runtime_path, size=TILE_CELL_SIZE, label="tile")
                except RasterError as exc:
                    bundle_failed = True
                    fail_reason = str(exc)
                    break
            if actual_bytes != expected_bytes:
                bundle_failed = True
                fail_reason = f"runtime bytes mismatch for {rel_path.as_posix()}"
                break

        rows.append(
            BundleReportRow(
                key=bundle_key,
                asset_class=ref.asset_class,
                outcome="FAIL" if bundle_failed else "PASS",
                raw_sha256=source.raw_sha256,
                runtime_sha256=runtime_sha,
                reason=fail_reason,
            )
        )

    outcome: Literal["PASS", "FAIL"] = "PASS" if rows and all(row.outcome == "PASS" for row in rows) else "FAIL"
    if not rows:
        outcome = "PASS"
    return TunnelArtReport(outcome=outcome, bundles=tuple(rows))


def _exit_code(outcome: str) -> int:
    return 0 if outcome == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tunnel art build and verify")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="Build runtime tunnel art from archived raws")
    build_parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    verify_parser = subparsers.add_parser("verify", help="Verify committed runtime tunnel art")
    verify_parser.add_argument("--json", action="store_true", help="Emit machine-readable report")
    args = parser.parse_args(argv)

    if args.command == "build":
        report = build_tunnel_assets()
    else:
        report = verify_tunnel_assets()

    if args.json:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
    return _exit_code(report.outcome)


if __name__ == "__main__":
    raise SystemExit(main())
