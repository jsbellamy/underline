"""Final-polish bundle validation — initialize, check, and finalize logical Frames.

Consumes current production Acceptance profiles via ``ingest_strip_provider`` and
``coherence_split`` without mutating Gate semantics or evidence.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from PIL import Image, UnidentifiedImageError

from pipeline.gate_evidence import EvidenceError, sha256_bytes, sha256_file, write_json_immutable
from pipeline.recovery import MAGENTA
from pipeline.strip import (
    DEFAULT_LAYOUT,
    Cell,
    Outcome,
    StripLayout,
    canonicalize_frame,
    coherence_split,
    ingest_strip_provider,
    load_provider_frames,
)

BUNDLE_SCHEMA = "final-polish-bundle/0"
REPORT_SCHEMA = "final-polish-report/0"

FRAME_DIR_NAMES = ("draft", "polished", "release")
EXPECTED_FRAME_NAMES = tuple(f"frame-{index}.png" for index in range(DEFAULT_LAYOUT.frame_count))


class FinalPolishError(ValueError):
    """Base error for final-polish bundle operations."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class BundleExistsError(FinalPolishError):
    """Refuse to initialize when the bundle destination already exists."""


class InitializationRejectedError(FinalPolishError):
    """Provider ingest did not PASS — no bundle must be created."""


class InvalidBundleError(FinalPolishError):
    """Bundled bytes or logical Frames are not trustworthy."""


@dataclass(frozen=True)
class StructuralViolation:
    code: str
    frame_index: int | None = None
    x: int | None = None
    y: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class StructuralCheckResult:
    pass_: bool
    outcome: Outcome
    violations: tuple[StructuralViolation, ...]


@dataclass(frozen=True)
class VisibleCellEdit:
    frame_index: int
    x: int
    y: int
    draft_rgb: tuple[int, int, int]
    polished_rgb: tuple[int, int, int]


@dataclass(frozen=True)
class VisibleCellDelta:
    edits: tuple[VisibleCellEdit, ...]
    per_frame_counts: tuple[int, ...]
    total_edits: int


@dataclass(frozen=True)
class FinalPolishCheckResult:
    outcome: Outcome
    provider_outcome: Outcome
    structural: StructuralCheckResult
    delta: VisibleCellDelta
    coherence: dict[str, Any]
    manifest_sha256: str
    provider_sha256: str
    draft_hashes: tuple[str, ...]
    polished_hashes: tuple[str, ...]
    fingerprint: str


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _frame_dir(bundle_root: Path, layer: str) -> Path:
    return bundle_root / layer


def _provider_path(bundle_root: Path) -> Path:
    return bundle_root / "provider" / "source.png"


def _reports_dir(bundle_root: Path) -> Path:
    return bundle_root / "reports"


def _cleanup_partial(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


def _save_logical_frame(cells: list[list[Cell]], path: Path) -> None:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    image = Image.new("RGBA", (width, height), (*MAGENTA, 0))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            rgb = cells[y][x]
            if rgb is not None:
                pixels[x, y] = (*rgb, 255)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _cells_from_rgba_image(image: Image.Image) -> list[list[Cell]]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    assert pixels is not None
    cells: list[list[Cell]] = []
    for y in range(height):
        row: list[Cell] = []
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                row.append(None)
            else:
                row.append((int(r), int(g), int(b)))
        cells.append(row)
    return cells


def _load_logical_frame_png(
    path: Path,
    *,
    frame_w: int,
    frame_h: int,
) -> list[list[Cell]]:
    if not path.is_file():
        raise InvalidBundleError(
            f"missing logical frame: {path.name}",
            reason_code="missing_frame",
        )
    try:
        with Image.open(path) as image:
            if image.mode != "RGBA":
                raise InvalidBundleError(
                    f"frame must be RGBA: {path.name}",
                    reason_code="wrong_mode",
                )
            if image.size != (frame_w, frame_h):
                raise InvalidBundleError(
                    f"frame must be {frame_w}x{frame_h}: {path.name}",
                    reason_code="wrong_size",
                )
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            for value in alpha.get_flattened_data():
                if value not in (0, 255):
                    raise InvalidBundleError(
                        f"non-binary alpha in {path.name}",
                        reason_code="non_binary_alpha",
                    )
            return _cells_from_rgba_image(rgba)
    except UnidentifiedImageError as exc:
        raise InvalidBundleError(
            f"unreadable frame: {path.name}",
            reason_code="unreadable_frame",
        ) from exc


def _load_frame_sequence(bundle_root: Path, layer: str) -> list[list[list[Cell]]]:
    directory = _frame_dir(bundle_root, layer)
    if not directory.is_dir():
        raise InvalidBundleError(
            f"missing frame directory: {layer}",
            reason_code="missing_frame",
        )

    present = {path.name for path in directory.glob("*.png")}
    expected = set(EXPECTED_FRAME_NAMES)
    if present != expected:
        missing = expected - present
        extra = present - expected
        if missing and not extra:
            raise InvalidBundleError(
                f"missing frames in {layer}",
                reason_code="missing_frame",
            )
        if extra and not missing:
            raise InvalidBundleError(
                f"unexpected frames in {layer}",
                reason_code="extra_frame",
            )
        if len(present) == len(expected):
            raise InvalidBundleError(
                f"misordered frames in {layer}",
                reason_code="misordered_frames",
            )
        if extra:
            raise InvalidBundleError(
                f"unexpected frames in {layer}",
                reason_code="extra_frame",
            )
        raise InvalidBundleError(
            f"missing frames in {layer}",
            reason_code="missing_frame",
        )

    layout = _corpus_layout()
    return [
        _load_logical_frame_png(
            directory / name,
            frame_w=layout.frame_w,
            frame_h=layout.frame_h,
        )
        for name in EXPECTED_FRAME_NAMES
    ]


def _canonical_draft_frames(provider_path: Path, layout: StripLayout) -> list[list[list[Cell]]]:
    frames = load_provider_frames(provider_path, layout)
    if frames is None:
        raise InvalidBundleError(
            "provider strip could not be pitch-sliced",
            reason_code="draft_reproduction_mismatch",
        )
    return [
        canonicalize_frame(frame, frame_w=layout.frame_w, frame_h=layout.frame_h)
        for frame in frames
    ]


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


def _ordered_frame_hashes(bundle_root: Path, layer: str) -> tuple[str, ...]:
    directory = _frame_dir(bundle_root, layer)
    return tuple(sha256_file(directory / name) for name in EXPECTED_FRAME_NAMES)


def _fingerprint_polished_hashes(polished_hashes: Sequence[str]) -> str:
    joined = ":".join(polished_hashes)
    return sha256_bytes(joined.encode("utf-8"))


def _collect_draft_palette(draft_frames: list[list[list[Cell]]]) -> set[tuple[int, int, int]]:
    palette: set[tuple[int, int, int]] = set()
    for frame in draft_frames:
        for row in frame:
            for rgb in row:
                if rgb is not None:
                    palette.add(rgb)
    return palette


def _structural_check(
    draft_frames: list[list[list[Cell]]],
    polished_frames: list[list[list[Cell]]],
) -> StructuralCheckResult:
    violations: list[StructuralViolation] = []
    allowed_palette = _collect_draft_palette(draft_frames)

    for frame_index, (draft, polished) in enumerate(zip(draft_frames, polished_frames)):
        for y, (draft_row, polished_row) in enumerate(zip(draft, polished)):
            for x, (draft_cell, polished_cell) in enumerate(zip(draft_row, polished_row)):
                draft_alpha = draft_cell is not None
                polished_alpha = polished_cell is not None
                if draft_alpha != polished_alpha:
                    violations.append(
                        StructuralViolation(
                            code="alpha_mismatch",
                            frame_index=frame_index,
                            x=x,
                            y=y,
                        )
                    )
                    continue
                if polished_cell is not None and polished_cell not in allowed_palette:
                    violations.append(
                        StructuralViolation(
                            code="palette_violation",
                            frame_index=frame_index,
                            x=x,
                            y=y,
                        )
                    )

    if violations:
        return StructuralCheckResult(pass_=False, outcome="FAIL", violations=tuple(violations))
    return StructuralCheckResult(pass_=True, outcome="PASS", violations=())


def _visible_cell_delta(
    draft_frames: list[list[list[Cell]]],
    polished_frames: list[list[list[Cell]]],
) -> VisibleCellDelta:
    edits: list[VisibleCellEdit] = []
    per_frame_counts = [0, 0, 0, 0]

    for frame_index, (draft, polished) in enumerate(zip(draft_frames, polished_frames)):
        for y, (draft_row, polished_row) in enumerate(zip(draft, polished)):
            for x, (draft_cell, polished_cell) in enumerate(zip(draft_row, polished_row)):
                if draft_cell is None and polished_cell is None:
                    continue
                if draft_cell is None or polished_cell is None:
                    continue
                if draft_cell != polished_cell:
                    edits.append(
                        VisibleCellEdit(
                            frame_index=frame_index,
                            x=x,
                            y=y,
                            draft_rgb=draft_cell,
                            polished_rgb=polished_cell,
                        )
                    )
                    per_frame_counts[frame_index] += 1

    return VisibleCellDelta(
        edits=tuple(edits),
        per_frame_counts=tuple(per_frame_counts),
        total_edits=len(edits),
    )


def _aggregate_outcome(
    *,
    provider_outcome: Outcome,
    structural: StructuralCheckResult,
    coherence: dict[str, Any],
) -> Outcome:
    if provider_outcome != "PASS":
        return provider_outcome
    if not structural.pass_:
        return structural.outcome
    return coherence.get("outcome", "FAIL")


def _verify_provider_and_drafts(bundle_root: Path, manifest: dict[str, Any]) -> Outcome:
    provider_rel = manifest["provider"]["relative_path"]
    expected_provider_hash = manifest["provider"]["sha256"]
    provider_path = bundle_root / provider_rel
    actual_provider_hash = sha256_file(provider_path)
    if actual_provider_hash != expected_provider_hash:
        raise InvalidBundleError(
            "bundled provider hash does not match manifest",
            reason_code="provider_hash_mismatch",
        )

    layout = _corpus_layout()
    for entry in manifest["draft_frames"]:
        rel = entry["relative_path"]
        expected = entry["sha256"]
        actual = sha256_file(bundle_root / rel)
        if actual != expected:
            raise InvalidBundleError(
                f"draft frame hash mismatch: {rel}",
                reason_code="draft_hash_mismatch",
            )

    reproduced = _canonical_draft_frames(provider_path, layout)
    for entry, frame in zip(manifest["draft_frames"], reproduced):
        bundled = _load_logical_frame_png(
            bundle_root / entry["relative_path"],
            frame_w=layout.frame_w,
            frame_h=layout.frame_h,
        )
        if bundled != frame:
            raise InvalidBundleError(
                f"reproduced draft mismatch: {entry['relative_path']}",
                reason_code="draft_reproduction_mismatch",
            )

    ingest = ingest_strip_provider(provider_path, layout, motion_class=manifest["motion_class"])
    return ingest.outcome


def initialize_bundle(
    provider_path: Path,
    motion_class: str,
    bundle_root: Path,
    *,
    layout: StripLayout | None = None,
) -> None:
    """Create a hash-bound bundle when provider ingest PASSes; fail closed otherwise."""
    if bundle_root.exists():
        raise BundleExistsError(
            f"bundle destination already exists: {bundle_root}",
            reason_code="bundle_exists",
        )

    probe_layout = layout or _corpus_layout()
    ingest = ingest_strip_provider(provider_path, probe_layout, motion_class=motion_class)
    if ingest.outcome != "PASS" or not ingest.pass_:
        raise InitializationRejectedError(
            f"provider ingest outcome {ingest.outcome!r} — bundle not created",
            reason_code="ingest_not_pass",
        )

    frames = load_provider_frames(provider_path, probe_layout)
    if frames is None:
        raise InitializationRejectedError(
            "provider strip could not be pitch-sliced — bundle not created",
            reason_code="ingest_not_pass",
        )
    canonical_frames = [
        canonicalize_frame(frame, frame_w=probe_layout.frame_w, frame_h=probe_layout.frame_h)
        for frame in frames
    ]

    temp_root = bundle_root.parent / f".{bundle_root.name}.tmp"
    _cleanup_partial(temp_root)
    try:
        temp_root.mkdir(parents=True, exist_ok=False)
        provider_dest = temp_root / "provider" / "source.png"
        provider_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(provider_path, provider_dest)

        draft_hashes: list[dict[str, Any]] = []
        for index, cells in enumerate(canonical_frames):
            rel = f"draft/frame-{index}.png"
            draft_path = temp_root / rel
            _save_logical_frame(cells, draft_path)
            polished_path = temp_root / "polished" / f"frame-{index}.png"
            polished_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(draft_path, polished_path)
            draft_hashes.append(
                {
                    "index": index,
                    "relative_path": rel,
                    "sha256": sha256_file(draft_path),
                }
            )

        manifest = {
            "schema": BUNDLE_SCHEMA,
            "motion_class": motion_class,
            "layout": {
                "frame_w": probe_layout.frame_w,
                "frame_h": probe_layout.frame_h,
                "frame_count": probe_layout.frame_count,
                "frame_order": list(range(probe_layout.frame_count)),
                "gutter": probe_layout.gutter,
            },
            "provider": {
                "original_filename": provider_path.name,
                "relative_path": "provider/source.png",
                "sha256": sha256_file(provider_dest),
            },
            "draft_frames": draft_hashes,
        }
        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp_root / "reports").mkdir()
        temp_root.rename(bundle_root)
    except Exception:
        _cleanup_partial(temp_root)
        raise


def check_bundle(bundle_root: Path) -> FinalPolishCheckResult:
    """Validate provenance, logical Frames, structure, delta, and coherence."""
    manifest = _load_manifest(bundle_root)
    manifest_hash = _manifest_sha256(bundle_root)
    provider_outcome = _verify_provider_and_drafts(bundle_root, manifest)

    draft_frames = _load_frame_sequence(bundle_root, "draft")
    polished_frames = _load_frame_sequence(bundle_root, "polished")
    draft_hashes = _ordered_frame_hashes(bundle_root, "draft")
    polished_hashes = _ordered_frame_hashes(bundle_root, "polished")
    provider_sha256 = sha256_file(_provider_path(bundle_root))

    structural = _structural_check(draft_frames, polished_frames)
    delta = _visible_cell_delta(draft_frames, polished_frames)
    coherence = coherence_split(polished_frames, motion_class=manifest["motion_class"])
    outcome = _aggregate_outcome(
        provider_outcome=provider_outcome,
        structural=structural,
        coherence=coherence,
    )
    fingerprint = _fingerprint_polished_hashes(polished_hashes)

    return FinalPolishCheckResult(
        outcome=outcome,
        provider_outcome=provider_outcome,
        structural=structural,
        delta=delta,
        coherence=coherence,
        manifest_sha256=manifest_hash,
        provider_sha256=provider_sha256,
        draft_hashes=draft_hashes,
        polished_hashes=polished_hashes,
        fingerprint=fingerprint,
    )


def _report_payload(bundle_root: Path, result: FinalPolishCheckResult) -> dict[str, Any]:
    manifest = _load_manifest(bundle_root)
    payload: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "fingerprint": result.fingerprint,
        "manifest_sha256": result.manifest_sha256,
        "motion_class": manifest["motion_class"],
        "layout": manifest["layout"],
        "provider": {
            "relative_path": manifest["provider"]["relative_path"],
            "sha256": result.provider_sha256,
        },
        "draft_frames": [
            {"index": index, "sha256": digest}
            for index, digest in enumerate(result.draft_hashes)
        ],
        "polished_frames": [
            {"index": index, "sha256": digest}
            for index, digest in enumerate(result.polished_hashes)
        ],
        "provider_acceptance": {"outcome": result.provider_outcome},
        "structural": {
            "pass": result.structural.pass_,
            "outcome": result.structural.outcome,
            "violations": [
                {
                    "code": violation.code,
                    "frame_index": violation.frame_index,
                    "x": violation.x,
                    "y": violation.y,
                    "detail": violation.detail,
                }
                for violation in result.structural.violations
            ],
        },
        "visible_cell_delta": {
            "edits": [
                {
                    "frame_index": edit.frame_index,
                    "x": edit.x,
                    "y": edit.y,
                    "draft_rgb": list(edit.draft_rgb),
                    "polished_rgb": list(edit.polished_rgb),
                }
                for edit in result.delta.edits
            ],
            "per_frame_counts": list(result.delta.per_frame_counts),
            "total_edits": result.delta.total_edits,
        },
        "coherence": result.coherence,
        "outcome": result.outcome,
    }
    if result.outcome == "PASS":
        payload["release_frames"] = [
            {"index": index, "sha256": digest}
            for index, digest in enumerate(result.polished_hashes)
        ]
    return payload


def _ensure_release_frames(bundle_root: Path, result: FinalPolishCheckResult) -> None:
    release_dir = _frame_dir(bundle_root, "release")
    release_dir.mkdir(parents=True, exist_ok=True)
    for index, name in enumerate(EXPECTED_FRAME_NAMES):
        source = _frame_dir(bundle_root, "polished") / name
        dest = release_dir / name
        if dest.exists():
            if sha256_file(dest) != result.polished_hashes[index]:
                raise InvalidBundleError(
                    f"release frame conflict: {name}",
                    reason_code="release_conflict",
                )
            continue
        shutil.copy2(source, dest)


def _canonical_json(value: object) -> object:
    return json.loads(json.dumps(value, sort_keys=True))


def finalize_bundle(
    bundle_root: Path,
    result: FinalPolishCheckResult | None = None,
) -> Path:
    """Write an immutable report; on PASS, copy polished Frames to release/."""
    check = result or check_bundle(bundle_root)
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

    if check.outcome == "PASS":
        _ensure_release_frames(bundle_root, check)

    return report_path
