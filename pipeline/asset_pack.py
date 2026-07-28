"""Asset pack schema, validation, and deterministic first-room previews."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError

from pipeline.cell_raster import cells_from_rgba
from pipeline.gate_evidence import sha256_file
from pipeline.static_asset import _palette_rgb_set

PACK_SCHEMA = "asset-pack/0"
ANIMATION_REPORT_SCHEMA = "final-polish-report/0"
STATIC_REPORT_SCHEMA = "static-asset-report/0"
VIEWPORT_W = 320
VIEWPORT_H = 180
SCALE_FACTOR = 4
_REPO_ROOT = Path(__file__).resolve().parents[1]

AssetKind = Literal["animation", "static"]

FIRST_ROOM_ANIMATION_POLICY: dict[str, dict[str, Any]] = {
    "dwarf-idle": {
        "loop": True,
        "durations_ms": [200, 200, 200, 200],
        "contact_frame": None,
    },
    "dwarf-walk": {
        "loop": True,
        "durations_ms": [125, 125, 125, 125],
        "contact_frame": None,
    },
    "dwarf-swing": {
        "loop": False,
        "durations_ms": [150, 80, 60, 180],
        "contact_frame": 3,
    },
    "lantern": {
        "loop": True,
        "durations_ms": [160, 160, 160, 160],
        "contact_frame": None,
    },
}

TERRACED_SHAFT_PREVIEW_SCENE: dict[str, Any] = {
    "composition": "terraced-shaft-variant-b",
    "grid_columns": 10,
    "grid_rows": 5,
    "blocks": [
        {"col": 0, "row": 1, "texture_variant": 0, "mask": 2},
        {"col": 1, "row": 1, "texture_variant": 1, "mask": 3},
        {"col": 2, "row": 1, "texture_variant": 2, "mask": 2},
        {"col": 3, "row": 2, "texture_variant": 0, "mask": 12},
        {"col": 4, "row": 2, "texture_variant": 1, "mask": 13},
        {"col": 5, "row": 2, "texture_variant": 1, "mask": 5},
        {"col": 6, "row": 2, "texture_variant": 2, "mask": 9},
        {"col": 7, "row": 2, "texture_variant": 0, "mask": 8},
        {"col": 3, "row": 3, "texture_variant": 1, "mask": 4},
        {"col": 4, "row": 3, "texture_variant": 2, "mask": 6},
        {"col": 5, "row": 3, "texture_variant": 0, "mask": 4},
        {"col": 6, "row": 3, "texture_variant": 1, "mask": 12},
        {"col": 7, "row": 3, "texture_variant": 2, "mask": 8},
        {"col": 8, "row": 3, "texture_variant": 0, "mask": 0},
        {"col": 1, "row": 4, "texture_variant": 1, "mask": 1},
        {"col": 2, "row": 4, "texture_variant": 2, "mask": 5},
        {
            "col": 3,
            "row": 4,
            "texture_variant": 0,
            "mask": 5,
            "ore_item_id": "ore-cyan-seam",
        },
        {"col": 4, "row": 4, "texture_variant": 1, "mask": 4},
        {"col": 5, "row": 4, "texture_variant": 2, "mask": 0},
    ],
    "entities": [
        {"asset_id": "dwarf-idle", "frame_index": 0, "x": 96, "y": 40},
        {"asset_id": "lantern", "frame_index": 0, "x": 224, "y": 24},
    ],
    "layer_order": ["mineable_blocks", "ore_overlays", "entities"],
}


class AssetPackError(ValueError):
    """Base error for asset pack operations."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class InvalidAssetPackError(AssetPackError):
    """Pack manifest or referenced bytes are not trustworthy."""


@dataclass(frozen=True)
class ReleaseRef:
    path: str
    sha256: str


@dataclass(frozen=True)
class ReportRef:
    path: str
    sha256: str


@dataclass(frozen=True)
class AnimationAssetRow:
    id: str
    kind: Literal["animation"]
    bundle_path: str
    final_report: ReportRef
    releases: tuple[ReleaseRef, ...]
    facing: str
    runtime_mirror: bool
    loop: bool
    durations_ms: tuple[int, ...]
    contact_frame: int | None = None


@dataclass(frozen=True)
class StaticAssetRow:
    id: str
    kind: Literal["static"]
    bundle_path: str
    final_report: ReportRef
    releases: tuple[ReleaseRef, ...]
    item_ids: tuple[str, ...]


AssetRow = AnimationAssetRow | StaticAssetRow


@dataclass(frozen=True)
class PreviewScene:
    composition: str
    grid_columns: int
    grid_rows: int
    blocks: tuple[dict[str, Any], ...]
    entities: tuple[dict[str, Any], ...]
    layer_order: tuple[str, ...]


@dataclass(frozen=True)
class AssetPack:
    id: str
    master_palette_path: str
    master_palette_sha256: str
    viewport: tuple[int, int]
    assets: tuple[AssetRow, ...]
    preview_scene: PreviewScene
    manifest_path: Path | None = None


@dataclass(frozen=True)
class AssetPackCheckResult:
    valid: bool
    outcome: Literal["PASS", "FAIL"]
    pack_id: str
    manifest_path: Path
    release_hashes: tuple[str, ...]
    errors: tuple[str, ...] = ()
    reason_codes: tuple[str | None, ...] = ()


@dataclass(frozen=True)
class PackPreviewResult:
    native_path: Path
    scale4x_path: Path
    native_sha256: str
    scale4x_sha256: str
    release_hashes: tuple[str, ...]


def _validate_repo_relative_path(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidAssetPackError(f"{field} must be a non-empty string", reason_code="invalid_path")
    if value.startswith("/") or ".." in Path(value).parts:
        raise InvalidAssetPackError(
            f"{field} must be repo-relative: {value!r}",
            reason_code="invalid_path",
        )
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidAssetPackError(f"{field} must be a positive integer", reason_code="invalid_field")
    return value


def _load_palette_rgb_set(path: Path) -> frozenset[tuple[int, int, int]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise InvalidAssetPackError("master palette must be an object", reason_code="invalid_palette")
    return _palette_rgb_set(doc)


def _parse_report_ref(value: object) -> ReportRef:
    if not isinstance(value, dict):
        raise InvalidAssetPackError("final_report must be an object", reason_code="invalid_report")
    path = _validate_repo_relative_path(value.get("path"), "final_report.path")
    sha = value.get("sha256")
    if not isinstance(sha, str) or not sha:
        raise InvalidAssetPackError("final_report.sha256 required", reason_code="invalid_report")
    return ReportRef(path=path, sha256=sha)


def _parse_release_refs(value: object) -> tuple[ReleaseRef, ...]:
    if not isinstance(value, list) or not value:
        raise InvalidAssetPackError("releases must be a non-empty list", reason_code="invalid_releases")
    releases: list[ReleaseRef] = []
    seen_paths: set[str] = set()
    for row in value:
        if not isinstance(row, dict):
            raise InvalidAssetPackError("each release must be an object", reason_code="invalid_releases")
        path = _validate_repo_relative_path(row.get("path"), "release.path")
        sha = row.get("sha256")
        if not isinstance(sha, str) or not sha:
            raise InvalidAssetPackError("release.sha256 required", reason_code="invalid_releases")
        if path in seen_paths:
            raise InvalidAssetPackError(f"duplicate release path: {path!r}", reason_code="duplicate_release")
        seen_paths.add(path)
        releases.append(ReleaseRef(path=path, sha256=sha))
    return tuple(releases)


def _parse_animation_row(row: dict[str, Any]) -> AnimationAssetRow:
    asset_id = row.get("id")
    if not isinstance(asset_id, str) or not asset_id:
        raise InvalidAssetPackError("asset id must be a non-empty string", reason_code="invalid_asset")
    if row.get("kind") != "animation":
        raise InvalidAssetPackError(f"asset {asset_id!r} must be animation", reason_code="invalid_kind")
    bundle_path = _validate_repo_relative_path(row.get("bundle_path"), "bundle_path")
    facing = row.get("facing")
    if facing != "right":
        raise InvalidAssetPackError(f"asset {asset_id!r} facing must be right", reason_code="facing")
    runtime_mirror = row.get("runtime_mirror")
    if runtime_mirror is not True:
        raise InvalidAssetPackError(
            f"asset {asset_id!r} runtime_mirror must be true",
            reason_code="runtime_mirror",
        )
    loop = row.get("loop")
    if not isinstance(loop, bool):
        raise InvalidAssetPackError(f"asset {asset_id!r} loop must be boolean", reason_code="loop")
    durations = row.get("durations_ms")
    if not isinstance(durations, list) or not durations:
        raise InvalidAssetPackError(
            f"asset {asset_id!r} durations_ms required",
            reason_code="durations_ms",
        )
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in durations):
        raise InvalidAssetPackError(
            f"asset {asset_id!r} durations_ms must be integers",
            reason_code="durations_ms",
        )
    contact_frame = row.get("contact_frame")
    if contact_frame is not None and (
        not isinstance(contact_frame, int) or isinstance(contact_frame, bool)
    ):
        raise InvalidAssetPackError(
            f"asset {asset_id!r} contact_frame must be an integer",
            reason_code="contact_frame",
        )
    return AnimationAssetRow(
        id=asset_id,
        kind="animation",
        bundle_path=bundle_path,
        final_report=_parse_report_ref(row.get("final_report")),
        releases=_parse_release_refs(row.get("releases")),
        facing="right",
        runtime_mirror=True,
        loop=loop,
        durations_ms=tuple(int(value) for value in durations),
        contact_frame=int(contact_frame) if contact_frame is not None else None,
    )


def _parse_static_row(row: dict[str, Any]) -> StaticAssetRow:
    asset_id = row.get("id")
    if not isinstance(asset_id, str) or not asset_id:
        raise InvalidAssetPackError("asset id must be a non-empty string", reason_code="invalid_asset")
    if row.get("kind") != "static":
        raise InvalidAssetPackError(f"asset {asset_id!r} must be static", reason_code="invalid_kind")
    bundle_path = _validate_repo_relative_path(row.get("bundle_path"), "bundle_path")
    item_ids_raw = row.get("item_ids")
    if not isinstance(item_ids_raw, list) or not item_ids_raw:
        raise InvalidAssetPackError(f"asset {asset_id!r} item_ids required", reason_code="item_ids")
    item_ids: list[str] = []
    seen: set[str] = set()
    for item_id in item_ids_raw:
        if not isinstance(item_id, str) or not item_id:
            raise InvalidAssetPackError("item id must be a non-empty string", reason_code="item_ids")
        if item_id in seen:
            raise InvalidAssetPackError(f"duplicate item id: {item_id!r}", reason_code="duplicate_item_id")
        seen.add(item_id)
        item_ids.append(item_id)
    return StaticAssetRow(
        id=asset_id,
        kind="static",
        bundle_path=bundle_path,
        final_report=_parse_report_ref(row.get("final_report")),
        releases=_parse_release_refs(row.get("releases")),
        item_ids=tuple(item_ids),
    )


def _parse_preview_scene(value: object) -> PreviewScene:
    if not isinstance(value, dict):
        raise InvalidAssetPackError("preview_scene must be an object", reason_code="invalid_scene")
    composition = value.get("composition")
    if composition != "terraced-shaft-variant-b":
        raise InvalidAssetPackError("preview_scene composition invalid", reason_code="invalid_scene")
    grid_columns = value.get("grid_columns")
    if grid_columns != 10:
        raise InvalidAssetPackError("preview_scene grid_columns must be 10", reason_code="grid_columns")
    grid_rows = _positive_int(value.get("grid_rows"), "grid_rows")
    blocks_raw = value.get("blocks")
    entities_raw = value.get("entities")
    layer_order_raw = value.get("layer_order")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        raise InvalidAssetPackError("preview_scene blocks required", reason_code="invalid_scene")
    if not isinstance(entities_raw, list) or not entities_raw:
        raise InvalidAssetPackError("preview_scene entities required", reason_code="invalid_scene")
    if not isinstance(layer_order_raw, list) or not layer_order_raw:
        raise InvalidAssetPackError("preview_scene layer_order required", reason_code="invalid_scene")
    blocks: list[dict[str, Any]] = []
    for block in blocks_raw:
        if not isinstance(block, dict):
            raise InvalidAssetPackError("each preview_scene block must be an object", reason_code="invalid_scene")
        blocks.append(dict(block))
    entities: list[dict[str, Any]] = []
    for entity in entities_raw:
        if not isinstance(entity, dict):
            raise InvalidAssetPackError("each preview_scene entity must be an object", reason_code="invalid_scene")
        entities.append(dict(entity))
    return PreviewScene(
        composition=str(composition),
        grid_columns=int(grid_columns),
        grid_rows=grid_rows,
        blocks=tuple(blocks),
        entities=tuple(entities),
        layer_order=tuple(str(layer) for layer in layer_order_raw),
    )


def serialize_preview_scene(scene: PreviewScene) -> dict[str, Any]:
    return {
        "composition": scene.composition,
        "grid_columns": scene.grid_columns,
        "grid_rows": scene.grid_rows,
        "blocks": [dict(block) for block in scene.blocks],
        "entities": [dict(entity) for entity in scene.entities],
        "layer_order": list(scene.layer_order),
    }


def parse_asset_pack(doc: dict[str, Any], *, repo_root: Path | None = None) -> AssetPack:
    """Validate and parse an asset-pack/0 manifest."""
    root = repo_root or _REPO_ROOT
    if doc.get("schema") != PACK_SCHEMA:
        raise InvalidAssetPackError(f"expected schema {PACK_SCHEMA!r}", reason_code="invalid_schema")
    pack_id = doc.get("id")
    if not isinstance(pack_id, str) or not pack_id:
        raise InvalidAssetPackError("id must be a non-empty string", reason_code="invalid_id")

    palette_binding = doc.get("master_palette")
    if not isinstance(palette_binding, dict):
        raise InvalidAssetPackError("master_palette must be an object", reason_code="invalid_palette")
    palette_path = _validate_repo_relative_path(
        palette_binding.get("path"),
        "master_palette.path",
    )
    palette_sha = palette_binding.get("sha256")
    if not isinstance(palette_sha, str) or not palette_sha:
        raise InvalidAssetPackError("master_palette.sha256 required", reason_code="invalid_palette")

    viewport = doc.get("viewport")
    if not isinstance(viewport, list) or viewport != [VIEWPORT_W, VIEWPORT_H]:
        raise InvalidAssetPackError(
            f"viewport must be [{VIEWPORT_W}, {VIEWPORT_H}]",
            reason_code="invalid_viewport",
        )

    raw_assets = doc.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise InvalidAssetPackError("assets must be a non-empty list", reason_code="invalid_assets")

    assets: list[AssetRow] = []
    seen_ids: set[str] = set()
    for row in raw_assets:
        if not isinstance(row, dict):
            raise InvalidAssetPackError("each asset must be an object", reason_code="invalid_asset")
        kind = row.get("kind")
        if kind == "animation":
            parsed = _parse_animation_row(row)
        elif kind == "static":
            parsed = _parse_static_row(row)
        else:
            raise InvalidAssetPackError("asset kind must be animation or static", reason_code="invalid_kind")
        if parsed.id in seen_ids:
            raise InvalidAssetPackError(f"duplicate asset id: {parsed.id!r}", reason_code="duplicate_id")
        seen_ids.add(parsed.id)
        assets.append(parsed)

    preview_scene = _parse_preview_scene(doc.get("preview_scene"))

    palette_file = root / palette_path
    if not palette_file.is_file():
        raise InvalidAssetPackError(
            f"master_palette.path does not exist: {palette_path}",
            reason_code="missing_palette",
        )
    if sha256_file(palette_file) != palette_sha:
        raise InvalidAssetPackError(
            "master_palette.sha256 does not match file",
            reason_code="invalid_palette_hash",
        )

    return AssetPack(
        id=pack_id,
        master_palette_path=palette_path,
        master_palette_sha256=palette_sha,
        viewport=(VIEWPORT_W, VIEWPORT_H),
        assets=tuple(assets),
        preview_scene=preview_scene,
    )


def load_asset_pack(path: Path, *, repo_root: Path | None = None) -> AssetPack:
    root = repo_root or _REPO_ROOT
    if not path.is_file():
        raise InvalidAssetPackError(f"missing manifest: {path}", reason_code="missing_manifest")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidAssetPackError(f"invalid manifest JSON: {path}", reason_code="invalid_manifest") from exc
    if not isinstance(doc, dict):
        raise InvalidAssetPackError("manifest must be a JSON object", reason_code="invalid_manifest")
    pack = parse_asset_pack(doc, repo_root=root)
    return AssetPack(
        id=pack.id,
        master_palette_path=pack.master_palette_path,
        master_palette_sha256=pack.master_palette_sha256,
        viewport=pack.viewport,
        assets=pack.assets,
        preview_scene=pack.preview_scene,
        manifest_path=path.resolve(),
    )


def _verify_report(path: Path, expected_sha: str, *, kind: AssetKind) -> None:
    if not path.is_file():
        raise InvalidAssetPackError(f"missing final report: {path}", reason_code="missing_report")
    if sha256_file(path) != expected_sha:
        raise InvalidAssetPackError(
            f"final report hash mismatch: {path}",
            reason_code="report_hash_mismatch",
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidAssetPackError(f"invalid report JSON: {path}", reason_code="invalid_report") from exc
    if not isinstance(doc, dict):
        raise InvalidAssetPackError("report must be an object", reason_code="invalid_report")
    expected_schema = ANIMATION_REPORT_SCHEMA if kind == "animation" else STATIC_REPORT_SCHEMA
    if doc.get("schema") != expected_schema:
        raise InvalidAssetPackError(
            f"report schema must be {expected_schema!r}",
            reason_code="invalid_report",
        )
    if doc.get("outcome") != "PASS":
        raise InvalidAssetPackError(
            f"report outcome must be PASS: {path}",
            reason_code="report_not_pass",
        )


def _verify_release(path: Path, expected_sha: str, allowed_palette: frozenset[tuple[int, int, int]]) -> None:
    if not path.is_file():
        raise InvalidAssetPackError(f"missing release: {path}", reason_code="missing_release")
    if sha256_file(path) != expected_sha:
        raise InvalidAssetPackError(
            f"release hash mismatch: {path}",
            reason_code="release_hash_mismatch",
        )
    try:
        with Image.open(path) as image:
            for y, row in enumerate(cells_from_rgba(image)):
                for x, cell in enumerate(row):
                    if cell is None:
                        continue
                    if cell not in allowed_palette:
                        raise InvalidAssetPackError(
                            f"palette violation in {path} at ({x}, {y})",
                            reason_code="palette_violation",
                        )
    except UnidentifiedImageError as exc:
        raise InvalidAssetPackError(f"unreadable release: {path}", reason_code="unreadable_release") from exc


def _enforce_first_room_metadata(asset: AssetRow) -> None:
    if asset.id not in FIRST_ROOM_ANIMATION_POLICY:
        return
    if not isinstance(asset, AnimationAssetRow):
        raise InvalidAssetPackError(
            f"asset {asset.id!r} must be animation for first-room metadata",
            reason_code="metadata_kind",
        )
    policy = FIRST_ROOM_ANIMATION_POLICY[asset.id]
    if asset.loop != policy["loop"]:
        if asset.id == "dwarf-walk":
            raise InvalidAssetPackError("walk loop must be true", reason_code="walk_loop")
        raise InvalidAssetPackError(f"{asset.id} loop must match policy", reason_code="loop")
    if list(asset.durations_ms) != policy["durations_ms"]:
        if asset.id == "dwarf-idle":
            raise InvalidAssetPackError("idle durations must match policy", reason_code="idle durations")
        if asset.id == "dwarf-walk":
            raise InvalidAssetPackError("walk durations must match policy", reason_code="walk durations")
        if asset.id == "dwarf-swing":
            raise InvalidAssetPackError("swing durations must match policy", reason_code="swing durations")
        raise InvalidAssetPackError("lantern durations must match policy", reason_code="lantern durations")
    expected_contact = policy["contact_frame"]
    if asset.contact_frame != expected_contact:
        raise InvalidAssetPackError(
            "contact_frame must be 3 for dwarf-swing",
            reason_code="contact_frame",
        )


def check_asset_pack(manifest_path: Path, *, repo_root: Path | None = None) -> AssetPackCheckResult:
    """Validate an asset pack manifest and every referenced report/release."""
    root = repo_root or _REPO_ROOT
    errors: list[str] = []
    try:
        pack = load_asset_pack(manifest_path, repo_root=root)
        palette = _load_palette_rgb_set(root / pack.master_palette_path)
        release_hashes: list[str] = []
        for asset in pack.assets:
            _enforce_first_room_metadata(asset)
        for asset in pack.assets:
            report_path = root / asset.final_report.path
            _verify_report(report_path, asset.final_report.sha256, kind=asset.kind)
        for asset in pack.assets:
            for release in asset.releases:
                release_path = root / release.path
                _verify_release(release_path, release.sha256, palette)
                release_hashes.append(release.sha256)
        return AssetPackCheckResult(
            valid=True,
            outcome="PASS",
            pack_id=pack.id,
            manifest_path=manifest_path.resolve(),
            release_hashes=tuple(release_hashes),
        )
    except InvalidAssetPackError as exc:
        errors.append(str(exc))
        reason_codes: tuple[str | None, ...] = (exc.reason_code,)
        pack_id = "unknown"
        try:
            doc = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and isinstance(doc.get("id"), str):
                pack_id = doc["id"]
        except (OSError, json.JSONDecodeError):
            pass
        return AssetPackCheckResult(
            valid=False,
            outcome="FAIL",
            pack_id=pack_id,
            manifest_path=manifest_path.resolve(),
            release_hashes=(),
            errors=tuple(errors),
            reason_codes=reason_codes,
        )


def _release_lookup(pack: AssetPack, root: Path) -> dict[tuple[str, str], Path]:
    lookup: dict[tuple[str, str], Path] = {}
    for asset in pack.assets:
        if isinstance(asset, StaticAssetRow):
            for item_id, release in zip(asset.item_ids, asset.releases):
                lookup[(asset.id, item_id)] = root / release.path
        else:
            for index, release in enumerate(asset.releases):
                lookup[(asset.id, f"frame-{index}")] = root / release.path
    return lookup


def _blit_rgba(canvas: Image.Image, overlay: Image.Image, x: int, y: int) -> None:
    canvas.alpha_composite(overlay, (x, y))


def _render_scene_layer(
    canvas: Image.Image,
    pack: AssetPack,
    scene: PreviewScene,
    layer: str,
    lookup: dict[tuple[str, str], Path],
) -> None:
    if layer == "mineable_blocks":
        for block in scene.blocks:
            variant = int(block["texture_variant"])
            item_id = f"cave-v{variant}"
            path = lookup[("cave", item_id)]
            with Image.open(path) as image:
                tile = image.convert("RGBA")
            _blit_rgba(canvas, tile, int(block["col"]) * 32, int(block["row"]) * 32)
        return

    if layer == "ore_overlays":
        for block in scene.blocks:
            ore_item_id = block.get("ore_item_id")
            if not ore_item_id:
                continue
            path = lookup[("mining", str(ore_item_id))]
            with Image.open(path) as image:
                tile = image.convert("RGBA")
            _blit_rgba(canvas, tile, int(block["col"]) * 32, int(block["row"]) * 32)
        return

    if layer == "entities":
        for entity in scene.entities:
            asset_id = str(entity["asset_id"])
            frame_index = int(entity["frame_index"])
            path = lookup[(asset_id, f"frame-{frame_index}")]
            with Image.open(path) as image:
                sprite = image.convert("RGBA")
            _blit_rgba(canvas, sprite, int(entity["x"]), int(entity["y"]))
        return

    raise InvalidAssetPackError(f"unknown preview layer: {layer!r}", reason_code="invalid_layer")


def render_pack_preview(
    manifest_path: Path,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
) -> PackPreviewResult:
    """Render deterministic native and 4× previews for a valid asset pack."""
    root = repo_root or _REPO_ROOT
    check = check_asset_pack(manifest_path, repo_root=root)
    if not check.valid:
        message = check.errors[0] if check.errors else "invalid asset pack"
        raise AssetPackError(message, reason_code="invalid_pack")

    pack = load_asset_pack(manifest_path, repo_root=root)
    lookup = _release_lookup(pack, root)
    canvas = Image.new("RGBA", (VIEWPORT_W, VIEWPORT_H), (0, 0, 0, 0))

    for layer in pack.preview_scene.layer_order:
        _render_scene_layer(canvas, pack, pack.preview_scene, layer, lookup)

    out_dir.mkdir(parents=True, exist_ok=True)
    native_path = out_dir / "native.png"
    scale4x_path = out_dir / "4x.png"
    canvas.save(native_path, format="PNG", compress_level=6)
    enlarged = canvas.resize(
        (VIEWPORT_W * SCALE_FACTOR, VIEWPORT_H * SCALE_FACTOR),
        Image.NEAREST,
    )
    enlarged.save(scale4x_path, format="PNG", compress_level=6)

    return PackPreviewResult(
        native_path=native_path.resolve(),
        scale4x_path=scale4x_path.resolve(),
        native_sha256=sha256_file(native_path),
        scale4x_sha256=sha256_file(scale4x_path),
        release_hashes=check.release_hashes,
    )
