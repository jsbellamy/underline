"""Static asset bundle lifecycle — initialize, check, and finalize provider sheets."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from pipeline import canonical
from pipeline.cell_raster import RasterError, write_cells
from pipeline.cell_raster import read_cells as _read_cells
from pipeline.gate_evidence import EvidenceError, sha256_bytes, sha256_file, write_json_immutable
from pipeline.recovery import MIN_GRID_SCORE, detect_pitch, key, raw_clipping, raw_gates, sample_cells
from pipeline.strip import Cell

SPEC_SCHEMA = "static-sheet-spec/0"
BUNDLE_SCHEMA = "static-asset-bundle/0"
REPORT_SCHEMA = "static-asset-report/0"
PITCH_PX = 24
Outcome = Literal["PASS", "FAIL"]
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_REPO_ROOT = Path(__file__).resolve().parents[1]


class StaticAssetError(ValueError):
    """Base error for static asset bundle operations."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class BundleExistsError(StaticAssetError):
    """Refuse to initialize when the bundle destination already exists."""


class InitializationRejectedError(StaticAssetError):
    """Provider or spec validation failed — no bundle must be created."""


class InvalidBundleError(StaticAssetError):
    """Bundled bytes or logical items are not trustworthy."""


class InvalidSpecError(StaticAssetError):
    """Static sheet specification is invalid."""


@dataclass(frozen=True)
class StaticSheetItem:
    id: str
    index: int
    release_path: str


@dataclass(frozen=True)
class StaticSheetSpec:
    id: str
    cell_w: int
    cell_h: int
    columns: int
    rows: int
    gutter: int
    master_palette_path: str
    master_palette_sha256: str
    items: tuple[StaticSheetItem, ...]


@dataclass(frozen=True)
class StructuralViolation:
    code: str
    item_id: str | None = None
    x: int | None = None
    y: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class StructuralCheckResult:
    pass_: bool
    outcome: Outcome
    violations: tuple[StructuralViolation, ...]


@dataclass(frozen=True)
class ChangedCellEdit:
    item_id: str
    x: int
    y: int
    draft_rgb: tuple[int, int, int]
    polished_rgb: tuple[int, int, int]


@dataclass(frozen=True)
class ChangedCellDelta:
    edits: tuple[ChangedCellEdit, ...]
    per_item_counts: tuple[int, ...]
    total_edits: int


@dataclass(frozen=True)
class StaticAssetCheckResult:
    outcome: Outcome
    structural: StructuralCheckResult
    delta: ChangedCellDelta
    manifest_sha256: str
    provider_sha256: str
    spec_sha256: str
    palette_sha256: str
    draft_hashes: tuple[str, ...]
    polished_hashes: tuple[str, ...]
    fingerprint: str


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    if not _HEX_COLOR.match(value):
        raise InvalidSpecError(f"invalid hex color: {value!r}", reason_code="invalid_palette")
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


def _palette_rgb_set(palette_doc: dict[str, Any]) -> frozenset[tuple[int, int, int]]:
    colors: set[tuple[int, int, int]] = set()
    role_groups = palette_doc.get("role_groups")
    if not isinstance(role_groups, list):
        raise InvalidSpecError("master palette missing role_groups", reason_code="invalid_palette")
    for group in role_groups:
        if not isinstance(group, dict):
            continue
        for hex_color in group.get("colors", []):
            if not isinstance(hex_color, str):
                continue
            colors.add(_hex_to_rgb(hex_color))
    if not colors:
        raise InvalidSpecError("master palette has no colors", reason_code="invalid_palette")
    return frozenset(colors)


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidSpecError(f"{field} must be a positive integer", reason_code="invalid_spec")
    return value


def _gutter_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvalidSpecError("gutter must be an integer >= 1", reason_code="invalid_spec")
    return value


def _validate_release_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidSpecError("release_path must be a non-empty string", reason_code="invalid_spec")
    if value.startswith("/") or ".." in Path(value).parts:
        raise InvalidSpecError(f"release_path must be relative: {value!r}", reason_code="invalid_spec")
    if Path(value).suffix.lower() != ".png":
        raise InvalidSpecError(f"release_path must end with .png: {value!r}", reason_code="invalid_spec")
    return value


def parse_static_sheet_spec(
    doc: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> StaticSheetSpec:
    """Validate and parse a static-sheet-spec/0 document."""
    root = repo_root or _REPO_ROOT
    if doc.get("schema") != SPEC_SCHEMA:
        raise InvalidSpecError(
            f"expected schema {SPEC_SCHEMA!r}",
            reason_code="invalid_spec",
        )
    spec_id = doc.get("id")
    if not isinstance(spec_id, str) or not spec_id:
        raise InvalidSpecError("id must be a non-empty string", reason_code="invalid_spec")

    cell_w = _positive_int(doc.get("cell_w"), "cell_w")
    cell_h = _positive_int(doc.get("cell_h"), "cell_h")
    columns = _positive_int(doc.get("columns"), "columns")
    rows = _positive_int(doc.get("rows"), "rows")
    gutter = _gutter_int(doc.get("gutter"))

    palette_binding = doc.get("master_palette")
    if not isinstance(palette_binding, dict):
        raise InvalidSpecError("master_palette must be an object", reason_code="invalid_spec")
    palette_path = palette_binding.get("path")
    palette_sha = palette_binding.get("sha256")
    if not isinstance(palette_path, str) or not palette_path:
        raise InvalidSpecError("master_palette.path required", reason_code="invalid_spec")
    if palette_path.startswith("/") or ".." in Path(palette_path).parts:
        raise InvalidSpecError(
            f"master_palette.path must be repo-relative: {palette_path!r}",
            reason_code="invalid_spec",
        )
    if not isinstance(palette_sha, str) or not palette_sha:
        raise InvalidSpecError("master_palette.sha256 required", reason_code="invalid_spec")
    palette_file = root / palette_path
    if not palette_file.is_file():
        raise InvalidSpecError(
            f"master_palette.path does not exist: {palette_path}",
            reason_code="invalid_palette_path",
        )
    if sha256_file(palette_file) != palette_sha:
        raise InvalidSpecError(
            "master_palette.sha256 does not match file",
            reason_code="invalid_palette_hash",
        )

    raw_items = doc.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise InvalidSpecError("items must be a non-empty list", reason_code="invalid_spec")

    items: list[StaticSheetItem] = []
    seen_indices: set[int] = set()
    seen_ids: set[str] = set()
    seen_release_paths: set[str] = set()
    slot_count = columns * rows

    for row in raw_items:
        if not isinstance(row, dict):
            raise InvalidSpecError("each item must be an object", reason_code="invalid_spec")
        item_id = row.get("id")
        index = row.get("index")
        release_path = row.get("release_path")
        if not isinstance(item_id, str) or not item_id:
            raise InvalidSpecError("item id must be a non-empty string", reason_code="invalid_spec")
        if not isinstance(index, int) or isinstance(index, bool):
            raise InvalidSpecError("item index must be an integer", reason_code="invalid_spec")
        if index < 0 or index >= slot_count:
            raise InvalidSpecError(
                f"item index {index} outside grid slots 0..{slot_count - 1}",
                reason_code="invalid_index",
            )
        if index in seen_indices:
            raise InvalidSpecError(f"duplicate item index: {index}", reason_code="duplicate_index")
        if item_id in seen_ids:
            raise InvalidSpecError(f"duplicate item id: {item_id!r}", reason_code="duplicate_id")
        release_path = _validate_release_path(release_path)
        if release_path in seen_release_paths:
            raise InvalidSpecError(
                f"duplicate release_path: {release_path!r}",
                reason_code="duplicate_release_path",
            )
        seen_indices.add(index)
        seen_ids.add(item_id)
        seen_release_paths.add(release_path)
        items.append(StaticSheetItem(id=item_id, index=index, release_path=release_path))

    if not items:
        raise InvalidSpecError("items must not be empty", reason_code="invalid_spec")

    max_index = max(item.index for item in items)
    expected_indices = set(range(max_index + 1))
    if seen_indices != expected_indices:
        raise InvalidSpecError(
            "items have holes before the last declared index",
            reason_code="index_hole",
        )

    items.sort(key=lambda item: item.index)
    return StaticSheetSpec(
        id=spec_id,
        cell_w=cell_w,
        cell_h=cell_h,
        columns=columns,
        rows=rows,
        gutter=gutter,
        master_palette_path=palette_path,
        master_palette_sha256=palette_sha,
        items=tuple(items),
    )


def load_static_sheet_spec(path: Path, *, repo_root: Path | None = None) -> StaticSheetSpec:
    if not path.is_file():
        raise InvalidSpecError(f"missing spec file: {path}", reason_code="missing_spec")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidSpecError(f"invalid spec JSON: {path}", reason_code="invalid_spec") from exc
    if not isinstance(doc, dict):
        raise InvalidSpecError("spec must be a JSON object", reason_code="invalid_spec")
    return parse_static_sheet_spec(doc, repo_root=repo_root)


def expected_grid_size(spec: StaticSheetSpec) -> tuple[int, int]:
    grid_w = spec.columns * spec.cell_w + (spec.columns - 1) * spec.gutter
    grid_h = spec.rows * spec.cell_h + (spec.rows - 1) * spec.gutter
    return grid_w, grid_h


def recover_static_sheet_cells(
    provider_path: Path,
    spec: StaticSheetSpec,
) -> tuple[list[list[Cell]], dict[str, Any]]:
    """Recover one logical sheet grid using vendored recovery primitives."""
    gate_errs = raw_gates(provider_path)
    if gate_errs:
        raise InitializationRejectedError("; ".join(gate_errs), reason_code="raw_gate_fail")

    clip = raw_clipping(provider_path)
    if clip:
        raise InitializationRejectedError("; ".join(clip), reason_code="raw_clipping")

    src, fg, bbox = key(provider_path)
    x0, y0, x1, y1 = 0, 0, src.width - 1, src.height - 1
    bbox = (x0, y0, x1, y1)
    pitch_val = float(PITCH_PX)
    band_lo, band_hi = pitch_val * 0.98, pitch_val * 1.02
    pitch_y_fit = detect_pitch(src, fg, "y", band_lo, band_hi)
    pitch_x_fit = detect_pitch(src, fg, "x", band_lo, band_hi)
    pitch_y = {"pitch": pitch_val, "phase": pitch_y_fit["phase"], "score": pitch_y_fit["score"]}
    pitch_x = {"pitch": pitch_val, "phase": pitch_x_fit["phase"], "score": pitch_x_fit["score"]}
    if pitch_y["score"] < MIN_GRID_SCORE or pitch_x["score"] < MIN_GRID_SCORE:
        raise InitializationRejectedError(
            f"pitch-fail x={pitch_x['score']:.3f} y={pitch_y['score']:.3f}",
            reason_code="pitch_fail",
        )

    cells = sample_cells(src, fg, bbox, pitch_x, pitch_y)
    grid_h = len(cells)
    grid_w = len(cells[0]) if cells else 0
    expected_w, expected_h = expected_grid_size(spec)
    meta: dict[str, Any] = {
        "bbox": list(bbox),
        "pitch_x": {"pitch": pitch_x["pitch"], "score": pitch_x["score"]},
        "pitch_y": {"pitch": pitch_y["pitch"], "score": pitch_y["score"]},
        "grid": [grid_w, grid_h],
        "expected_grid": [expected_w, expected_h],
    }
    if grid_w != expected_w or grid_h != expected_h:
        raise InitializationRejectedError(
            f"sheet geometry mismatch: expected {expected_w}x{expected_h}, got {grid_w}x{grid_h}",
            reason_code="geometry_mismatch",
        )
    return cells, meta


def slice_static_item(
    cells: list[list[Cell]],
    spec: StaticSheetSpec,
    index: int,
) -> list[list[Cell]]:
    col = index % spec.columns
    row = index // spec.columns
    x0 = col * (spec.cell_w + spec.gutter)
    y0 = row * (spec.cell_h + spec.gutter)
    return [
        list(cells[y][x0 : x0 + spec.cell_w])
        for y in range(y0, y0 + spec.cell_h)
    ]


def _cleanup_partial(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


def _load_logical_item_png(
    path: Path,
    *,
    item_id: str,
    cell_w: int,
    cell_h: int,
) -> list[list[Cell]]:
    try:
        return _read_cells(path, size=(cell_w, cell_h), label="item")
    except RasterError as exc:
        message = str(exc).replace(path.name, item_id)
        raise InvalidBundleError(message, reason_code=exc.reason_code) from exc


def _load_manifest(bundle_root: Path) -> dict[str, Any]:
    path = bundle_root / "manifest.json"
    if not path.is_file():
        raise InvalidBundleError("missing manifest.json", reason_code="missing_manifest")
    try:
        doc = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise InvalidBundleError("invalid manifest JSON", reason_code="invalid_manifest") from exc
    if doc.get("schema") != BUNDLE_SCHEMA:
        raise InvalidBundleError("unknown bundle schema", reason_code="invalid_manifest")
    return doc


def _manifest_sha256(bundle_root: Path) -> str:
    return sha256_file(bundle_root / "manifest.json")


def _fingerprint_polished_hashes(polished_hashes: Sequence[str]) -> str:
    joined = ":".join(polished_hashes)
    return sha256_bytes(joined.encode("utf-8"))


def _load_bound_palette(bundle_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    binding = manifest.get("master_palette")
    if not isinstance(binding, dict):
        raise InvalidBundleError("invalid master palette binding", reason_code="invalid_palette")
    try:
        path = canonical.verify_binding(binding, root=bundle_root, label="palette")
    except canonical.BindingError as exc:
        raise InvalidBundleError(str(exc), reason_code=exc.reason_code) from exc
    if binding.get("relative_path") != "palette.json":
        raise InvalidBundleError("invalid master palette path", reason_code="invalid_palette")
    try:
        palette = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidBundleError("invalid embedded master palette JSON", reason_code="invalid_palette") from exc
    if not isinstance(palette, dict):
        raise InvalidBundleError("embedded master palette must be an object", reason_code="invalid_palette")
    return palette


def _structural_check(
    draft_items: list[list[list[Cell]]],
    polished_items: list[list[list[Cell]]],
    item_ids: list[str],
    allowed_palette: frozenset[tuple[int, int, int]],
) -> StructuralCheckResult:
    violations: list[StructuralViolation] = []

    if len(draft_items) != len(polished_items):
        violations.append(
            StructuralViolation(code="item_count_mismatch", detail="draft/polished count differ")
        )
        return StructuralCheckResult(pass_=False, outcome="FAIL", violations=tuple(violations))

    for item_id, draft, polished in zip(item_ids, draft_items, polished_items):
        for y, (draft_row, polished_row) in enumerate(zip(draft, polished)):
            for x, (draft_cell, polished_cell) in enumerate(zip(draft_row, polished_row)):
                draft_alpha = draft_cell is not None
                polished_alpha = polished_cell is not None
                if draft_alpha != polished_alpha:
                    violations.append(
                        StructuralViolation(
                            code="alpha_mismatch",
                            item_id=item_id,
                            x=x,
                            y=y,
                        )
                    )
                    continue
                if polished_cell is not None and polished_cell not in allowed_palette:
                    violations.append(
                        StructuralViolation(
                            code="palette_violation",
                            item_id=item_id,
                            x=x,
                            y=y,
                        )
                    )

    if violations:
        return StructuralCheckResult(pass_=False, outcome="FAIL", violations=tuple(violations))
    return StructuralCheckResult(pass_=True, outcome="PASS", violations=())


def _changed_cell_delta(
    draft_items: list[list[list[Cell]]],
    polished_items: list[list[list[Cell]]],
    item_ids: list[str],
) -> ChangedCellDelta:
    edits: list[ChangedCellEdit] = []
    per_item_counts = [0 for _ in draft_items]

    for item_index, (item_id, draft, polished) in enumerate(zip(item_ids, draft_items, polished_items)):
        for y, (draft_row, polished_row) in enumerate(zip(draft, polished)):
            for x, (draft_cell, polished_cell) in enumerate(zip(draft_row, polished_row)):
                if draft_cell is None and polished_cell is None:
                    continue
                if draft_cell is None or polished_cell is None:
                    continue
                if draft_cell != polished_cell:
                    edits.append(
                        ChangedCellEdit(
                            item_id=item_id,
                            x=x,
                            y=y,
                            draft_rgb=draft_cell,
                            polished_rgb=polished_cell,
                        )
                    )
                    per_item_counts[item_index] += 1

    return ChangedCellDelta(
        edits=tuple(edits),
        per_item_counts=tuple(per_item_counts),
        total_edits=len(edits),
    )


def _verify_provider_and_drafts(
    bundle_root: Path,
    manifest: dict[str, Any],
    spec: StaticSheetSpec,
) -> None:
    provider_rel = manifest["provider"]["relative_path"]
    if sha256_file(bundle_root / provider_rel) != manifest["provider"]["sha256"]:
        raise InvalidBundleError(
            "bundled provider hash does not match manifest",
            reason_code="provider_hash_mismatch",
        )

    provenance_rel = manifest["provenance"]["relative_path"]
    if sha256_file(bundle_root / provenance_rel) != manifest["provenance"]["sha256"]:
        raise InvalidBundleError(
            "bundled provenance hash does not match manifest",
            reason_code="provenance_hash_mismatch",
        )

    for entry in manifest["draft_items"]:
        rel = entry["relative_path"]
        if sha256_file(bundle_root / rel) != entry["sha256"]:
            raise InvalidBundleError(
                f"draft item hash mismatch: {rel}",
                reason_code="draft_hash_mismatch",
            )

    provider_path = bundle_root / provider_rel
    cells, _ = recover_static_sheet_cells(provider_path, spec)
    for entry in manifest["draft_items"]:
        reproduced = slice_static_item(cells, spec, int(entry["index"]))
        bundled = _load_logical_item_png(
            bundle_root / entry["relative_path"],
            item_id=str(entry["id"]),
            cell_w=spec.cell_w,
            cell_h=spec.cell_h,
        )
        if bundled != reproduced:
            raise InvalidBundleError(
                f"reproduced draft mismatch: {entry['relative_path']}",
                reason_code="draft_reproduction_mismatch",
            )


def _validate_provenance_sidecar(
    provider_path: Path,
    provenance_path: Path,
) -> None:
    if not provenance_path.is_file():
        raise InitializationRejectedError(
            f"missing provenance sidecar: {provenance_path}",
            reason_code="missing_provenance",
        )
    try:
        record = json.loads(provenance_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InitializationRejectedError(
            f"invalid provenance sidecar: {exc}",
            reason_code="invalid_provenance",
        ) from exc
    if not isinstance(record, dict):
        raise InitializationRejectedError(
            "provenance sidecar must be a JSON object",
            reason_code="invalid_provenance",
        )
    actual = sha256_file(provider_path)
    if record.get("raw_sha256") != actual:
        raise InitializationRejectedError(
            "provider bytes differ from provenance raw_sha256",
            reason_code="provenance_hash_mismatch",
        )


def initialize_static_bundle(
    provider_path: Path,
    provenance_sidecar: Path,
    spec_path: Path,
    out: Path,
    *,
    repo_root: Path | None = None,
) -> None:
    """Create a hash-bound static asset bundle when provider and spec validate."""
    root = repo_root or _REPO_ROOT
    if out.exists():
        raise BundleExistsError(
            f"bundle destination already exists: {out}",
            reason_code="bundle_exists",
        )
    if not provider_path.is_file():
        raise InitializationRejectedError(
            f"missing provider: {provider_path}",
            reason_code="missing_provider",
        )

    spec = load_static_sheet_spec(spec_path, repo_root=root)
    _validate_provenance_sidecar(provider_path, provenance_sidecar)

    staging_provider = provider_path
    temp_provider_dir: Path | None = None
    expected_sidecar = provider_path.with_suffix(".source.json")
    if not expected_sidecar.is_file():
        temp_provider_dir = out.parent / f".{out.name}.provider-staging"
        _cleanup_partial(temp_provider_dir)
        temp_provider_dir.mkdir(parents=True, exist_ok=True)
        staging_provider = temp_provider_dir / provider_path.name
        shutil.copy2(provider_path, staging_provider)
        shutil.copy2(provenance_sidecar, staging_provider.with_suffix(".source.json"))

    try:
        cells, _ = recover_static_sheet_cells(staging_provider, spec)
    except InitializationRejectedError:
        if temp_provider_dir is not None:
            _cleanup_partial(temp_provider_dir)
        raise
    finally:
        if temp_provider_dir is not None:
            _cleanup_partial(temp_provider_dir)

    palette_source = root / spec.master_palette_path
    palette_doc = json.loads(palette_source.read_text(encoding="utf-8"))
    spec_doc = json.loads(spec_path.read_text(encoding="utf-8"))

    temp_root = out.parent / f".{out.name}.tmp"
    _cleanup_partial(temp_root)
    try:
        temp_root.mkdir(parents=True, exist_ok=False)
        provider_dest = temp_root / "provider" / "source.png"
        provider_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(provider_path, provider_dest)

        provenance_dest = temp_root / "provider" / "source.source.json"
        shutil.copy2(provenance_sidecar, provenance_dest)

        spec_dest = temp_root / "spec.json"
        spec_dest.write_text(json.dumps(spec_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        palette_dest = temp_root / "palette.json"
        shutil.copy2(palette_source, palette_dest)

        draft_entries: list[dict[str, Any]] = []
        for item in spec.items:
            item_cells = slice_static_item(cells, spec, item.index)
            draft_rel = f"draft/{item.id}.png"
            draft_path = temp_root / draft_rel
            write_cells(draft_path, item_cells)
            polished_path = temp_root / "polished" / f"{item.id}.png"
            polished_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(draft_path, polished_path)
            draft_entries.append(
                {
                    "id": item.id,
                    "index": item.index,
                    "release_path": item.release_path,
                    "relative_path": draft_rel,
                    "sha256": sha256_file(draft_path),
                }
            )

        manifest = {
            "schema": BUNDLE_SCHEMA,
            "spec_id": spec.id,
            "layout": {
                "cell_w": spec.cell_w,
                "cell_h": spec.cell_h,
                "columns": spec.columns,
                "rows": spec.rows,
                "gutter": spec.gutter,
            },
            "provider": {
                "original_filename": provider_path.name,
                "relative_path": "provider/source.png",
                "sha256": sha256_file(provider_dest),
            },
            "provenance": {
                "relative_path": "provider/source.source.json",
                "sha256": sha256_file(provenance_dest),
            },
            "spec": {
                "relative_path": "spec.json",
                "sha256": sha256_file(spec_dest),
            },
            "master_palette": {
                "relative_path": "palette.json",
                "sha256": sha256_file(palette_dest),
                "id": palette_doc.get("id"),
            },
            "draft_items": draft_entries,
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp_root / "reports").mkdir()
        temp_root.rename(out)
    except Exception:
        _cleanup_partial(temp_root)
        raise


def _spec_from_manifest(bundle_root: Path, manifest: dict[str, Any]) -> StaticSheetSpec:
    spec_binding = manifest.get("spec")
    if not isinstance(spec_binding, dict):
        raise InvalidBundleError("invalid spec binding", reason_code="invalid_spec")
    if spec_binding.get("relative_path") != "spec.json":
        raise InvalidBundleError("invalid spec path", reason_code="invalid_spec")
    spec_path = bundle_root / "spec.json"
    if not spec_path.is_file():
        raise InvalidBundleError("missing embedded spec", reason_code="missing_spec")
    if sha256_file(spec_path) != spec_binding.get("sha256"):
        raise InvalidBundleError(
            "embedded spec hash does not match manifest",
            reason_code="spec_hash_mismatch",
        )
    doc = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise InvalidBundleError("embedded spec must be an object", reason_code="invalid_spec")
    return parse_static_sheet_spec(doc, repo_root=_REPO_ROOT)


def check_static_bundle(bundle_root: Path) -> StaticAssetCheckResult:
    """Read-only structural validation of a static asset bundle."""
    manifest = _load_manifest(bundle_root)
    spec = _spec_from_manifest(bundle_root, manifest)
    palette_doc = _load_bound_palette(bundle_root, manifest)
    allowed_palette = _palette_rgb_set(palette_doc)

    _verify_provider_and_drafts(bundle_root, manifest, spec)

    item_ids: list[str] = []
    draft_items: list[list[list[Cell]]] = []
    polished_items: list[list[list[Cell]]] = []
    draft_hashes: list[str] = []
    polished_hashes: list[str] = []

    for entry in manifest["draft_items"]:
        item_id = str(entry["id"])
        item_ids.append(item_id)
        draft_path = bundle_root / str(entry["relative_path"])
        polished_path = bundle_root / "polished" / f"{item_id}.png"
        draft_items.append(
            _load_logical_item_png(
                draft_path,
                item_id=item_id,
                cell_w=spec.cell_w,
                cell_h=spec.cell_h,
            )
        )
        polished_items.append(
            _load_logical_item_png(
                polished_path,
                item_id=item_id,
                cell_w=spec.cell_w,
                cell_h=spec.cell_h,
            )
        )
        draft_hashes.append(sha256_file(draft_path))
        polished_hashes.append(sha256_file(polished_path))

    structural = _structural_check(draft_items, polished_items, item_ids, allowed_palette)
    delta = _changed_cell_delta(draft_items, polished_items, item_ids)
    outcome: Outcome = structural.outcome
    fingerprint = _fingerprint_polished_hashes(polished_hashes)

    return StaticAssetCheckResult(
        outcome=outcome,
        structural=structural,
        delta=delta,
        manifest_sha256=_manifest_sha256(bundle_root),
        provider_sha256=sha256_file(bundle_root / manifest["provider"]["relative_path"]),
        spec_sha256=sha256_file(bundle_root / "spec.json"),
        palette_sha256=sha256_file(bundle_root / "palette.json"),
        draft_hashes=tuple(draft_hashes),
        polished_hashes=tuple(polished_hashes),
        fingerprint=fingerprint,
    )


def _report_payload(bundle_root: Path, result: StaticAssetCheckResult) -> dict[str, Any]:
    manifest = _load_manifest(bundle_root)
    payload: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "fingerprint": result.fingerprint,
        "manifest_sha256": result.manifest_sha256,
        "spec_id": manifest["spec_id"],
        "layout": manifest["layout"],
        "provider": {
            "relative_path": manifest["provider"]["relative_path"],
            "sha256": result.provider_sha256,
        },
        "spec": {
            "relative_path": manifest["spec"]["relative_path"],
            "sha256": result.spec_sha256,
        },
        "master_palette": {
            "relative_path": manifest["master_palette"]["relative_path"],
            "sha256": result.palette_sha256,
            "id": manifest["master_palette"].get("id"),
        },
        "draft_items": [
            {"id": entry["id"], "index": entry["index"], "sha256": digest}
            for entry, digest in zip(manifest["draft_items"], result.draft_hashes)
        ],
        "polished_items": [
            {"id": entry["id"], "index": entry["index"], "sha256": digest}
            for entry, digest in zip(manifest["draft_items"], result.polished_hashes)
        ],
        "structural": {
            "pass": result.structural.pass_,
            "outcome": result.structural.outcome,
            "violations": [
                {
                    "code": violation.code,
                    "item_id": violation.item_id,
                    "x": violation.x,
                    "y": violation.y,
                    "detail": violation.detail,
                }
                for violation in result.structural.violations
            ],
        },
        "changed_cells": {
            "edits": [
                {
                    "item_id": edit.item_id,
                    "x": edit.x,
                    "y": edit.y,
                    "draft_rgb": list(edit.draft_rgb),
                    "polished_rgb": list(edit.polished_rgb),
                }
                for edit in result.delta.edits
            ],
            "per_item_counts": list(result.delta.per_item_counts),
            "total_edits": result.delta.total_edits,
        },
        "outcome": result.outcome,
    }
    if result.outcome == "PASS":
        payload["release_items"] = [
            {
                "id": entry["id"],
                "release_path": entry["release_path"],
                "sha256": digest,
            }
            for entry, digest in zip(manifest["draft_items"], result.polished_hashes)
        ]
    return payload


def _reports_dir(bundle_root: Path) -> Path:
    return bundle_root / "reports"


def _ensure_release_items(bundle_root: Path, result: StaticAssetCheckResult) -> list[Path]:
    manifest = _load_manifest(bundle_root)
    release_paths: list[Path] = []
    for entry, polished_hash in zip(manifest["draft_items"], result.polished_hashes):
        item_id = str(entry["id"])
        source = bundle_root / "polished" / f"{item_id}.png"
        if sha256_file(source) != polished_hash:
            raise InvalidBundleError(
                f"polished item hash mismatch: {item_id}",
                reason_code="release_conflict",
            )
        dest = bundle_root / "release" / str(entry["release_path"])
        if dest.exists():
            if sha256_file(dest) != polished_hash:
                raise InvalidBundleError(
                    f"release item conflict: {entry['release_path']}",
                    reason_code="release_conflict",
                )
            release_paths.append(dest)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        release_paths.append(dest)
    return release_paths


def _canonical_json(value: object) -> object:
    return json.loads(json.dumps(value, sort_keys=True))


def finalize_static_bundle(bundle_root: Path) -> tuple[Path, list[Path]]:
    """Write an immutable report; on PASS, copy polished items to release/."""
    check = check_static_bundle(bundle_root)
    report_path = _reports_dir(bundle_root) / f"{check.fingerprint}.json"
    payload = _report_payload(bundle_root, check)

    if report_path.exists():
        existing = json.loads(report_path.read_text())
        if _canonical_json(existing) != _canonical_json(payload):
            raise InvalidBundleError(
                f"immutable report conflict: {report_path.name}",
                reason_code="report_conflict",
            )
    else:
        try:
            write_json_immutable(report_path, payload)
        except EvidenceError as exc:
            raise InvalidBundleError(str(exc), reason_code="report_conflict") from exc

    release_paths: list[Path] = []
    if check.outcome == "PASS":
        release_paths = _ensure_release_items(bundle_root, check)

    return report_path, release_paths
