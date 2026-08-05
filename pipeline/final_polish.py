"""Final-polish bundle validation — initialize, check, and finalize logical Frames.

Consumes current production Acceptance profiles via ``ingest_strip_provider`` and
``coherence_split`` without mutating Gate semantics or evidence.
"""

from __future__ import annotations

import functools
import json
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline import canonical
from pipeline import gate_control as gc
from pipeline.asset_pack import FIRST_ROOM_ANIMATION_POLICY
from pipeline.cell_delta import (
    CellDeltaError,
    assert_cell_delta_replay,
    validate_cell_delta_ledger,
)
from pipeline.cell_raster import RasterError, write_cells
from pipeline.cell_raster import read_cells as _read_cells
from pipeline.cell_raster import write_silhouette_gif, write_silhouette_strip
from pipeline.gate_evidence import EvidenceError, manifest_sha256, sha256_bytes, sha256_file, write_json_immutable
from pipeline.palette_quantize import load_master_palette
from pipeline.identity_lock import (
    IDENTITY_LOCK_NEAR_MISS_SCHEMA,
    IdentityLockError,
    IdentityLockResult,
    evaluate_identity_lock,
    evaluate_provider_post_edit,
    expected_image_edit_source_sha256,
    identity_lock_applies,
    identity_lock_report_payload,
    provider_post_edit_report_payload,
)
from pipeline.strip import (
    DEFAULT_LAYOUT,
    Cell,
    IngestResult,
    Outcome,
    StripLayout,
    canonicalize_frame,
    coherence_split,
    embed_on_class_canvas,
    ingest_strip_provider,
    layout_for_motion_class,
    load_provider_frames,
    resolve_class_frame_geometry,
)

BUNDLE_SCHEMA_LEGACY_1 = "final-polish-bundle/1"
BUNDLE_SCHEMA = "final-polish-bundle/2"
BUNDLE_SCHEMAS = frozenset({BUNDLE_SCHEMA_LEGACY_1, BUNDLE_SCHEMA})
PROVENANCE_SCHEMA = "animation-strip-provenance/0"
ATTEMPT_LEDGER_SCHEMA = "animation-attempt-ledger/0"
PROFILE_SCHEMA = "polish-profile/0"
REPORT_SCHEMA = "final-polish-report/0"
GENERATION_MODES = frozenset({"text-to-image", "image-edit", "cell-author"})
PROVIDER_GENERATION_MODES = frozenset({"text-to-image", "image-edit"})
CELL_AUTHOR_GENERATION_MODE = "cell-author"
CELL_AUTHOR_PROVENANCE_SCHEMA = "cell-author-provenance/0"
MOTION_POSE_PLAN_SCHEMA = "motion-pose-plan/0"
CELL_AUTHOR_PROVENANCE_REQUIRED_FIELDS = (
    "schema",
    "generation_mode",
    "specification_id",
    "motion_class",
    "base_specification_id",
    "base_frames_sha256",
    "base_frame_mapping",
    "pose_plan",
    "cell_delta_ledger",
    "authoring_agent",
    "authoring_session_id",
    "repository_commit",
)
ATTEMPT_OUTCOMES = frozenset({"accepted", "rejected"})
LEGACY_BUNDLES_SCHEMA = "acquisition-legacy-allowlist/0"
ATTEMPTS_JSONL_REL = "attempts.jsonl"
PROVENANCE_REQUIRED_FIELDS = (
    "schema",
    "specification_id",
    "attempt_id",
    "predecessor_attempt_id",
    "generator",
    "model",
    "prompt_text",
    "prompt_sha256",
    "generation_mode",
    "reference_image_sha256",
    "edit_source_sha256",
    "generated_at",
    "acquiring_agent",
    "repository_commit",
    "raw_path",
    "raw_sha256",
    "media_type",
    "dimensions",
    "motion_class",
    "master_palette_id",
    "item_geometry",
)

EXPECTED_FRAME_NAMES = tuple(f"frame-{index}.png" for index in range(DEFAULT_LAYOUT.frame_count))
SILHOUETTE_STRIP_RELATIVE_PATH = "reports/silhouette-strip.png"
SILHOUETTE_GIF_RELATIVE_PATH = "reports/silhouette.gif"
_MOTION_CLASS_ASSET_ID = {
    "idle": "dwarf-idle",
    "walk": "dwarf-walk",
    "swing": "dwarf-swing",
    "emissive": "lantern",
}
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DWARF_IDENTITY_DOC = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
_PROFILE_ROOT = _REPO_ROOT / "polish-profiles"
_PROFILE_REGISTRY = {
    "dwarf-miner": _PROFILE_ROOT / "dwarf-miner.json",
    "lantern": _PROFILE_ROOT / "lantern.json",
    "miner": _PROFILE_ROOT / "miner.json",
}


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
class SilhouetteArtifacts:
    strip_relative_path: str
    strip_sha256: str
    gif_relative_path: str
    gif_sha256: str


@dataclass(frozen=True)
class AttestationState:
    state: str
    attempt_id: str | None = None
    store_path: str | None = None
    generation_mode: str | None = None
    base_specification_id: str | None = None
    base_frames_sha256: tuple[str, ...] | None = None
    base_frame_mapping: tuple[int, ...] | None = None
    cell_delta_ledger_sha256: str | None = None


@dataclass(frozen=True)
class FinalPolishCheckResult:
    outcome: Outcome
    provider_outcome: Outcome
    identity_lock: IdentityLockResult | None
    structural: StructuralCheckResult
    delta: VisibleCellDelta
    coherence: dict[str, Any]
    manifest_sha256: str
    provider_sha256: str
    draft_hashes: tuple[str, ...]
    polished_hashes: tuple[str, ...]
    fingerprint: str
    profile_id: str | None = None
    profile_sha256: str | None = None
    provider_post_edit: dict[str, Any] | None = None
    silhouette_artifacts: SilhouetteArtifacts | None = None
    attestation: AttestationState | None = None


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _embed_frames_for_manifest_layout(
    frames: list[list[list[Cell]]],
    *,
    motion_class: str,
    layout: StripLayout,
    anchor_layout: StripLayout | None = None,
) -> list[list[list[Cell]]]:
    if anchor_layout is None:
        anchor_layout = _corpus_layout()
    if (
        layout.frame_w == anchor_layout.frame_w
        and layout.frame_h == anchor_layout.frame_h
    ):
        return frames
    geometry = resolve_class_frame_geometry(motion_class)
    try:
        return [
            embed_on_class_canvas(
                frame,
                class_frame_w=layout.frame_w,
                class_frame_h=layout.frame_h,
                anchor_frame_w=anchor_layout.frame_w,
                anchor_frame_h=anchor_layout.frame_h,
                origin_dx=geometry.canonical_origin[0],
                origin_dy=geometry.canonical_origin[1],
            )
            for frame in frames
        ]
    except ValueError as exc:
        raise InvalidBundleError(str(exc), reason_code="wrong_size") from exc


def _frame_dir(bundle_root: Path, layer: str) -> Path:
    return bundle_root / layer


def _provider_path(bundle_root: Path) -> Path:
    return bundle_root / "provider" / "source.png"


def _reports_dir(bundle_root: Path) -> Path:
    return bundle_root / "reports"


def _cleanup_partial(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)


def _load_logical_frame_png(
    path: Path,
    *,
    frame_w: int,
    frame_h: int,
) -> list[list[Cell]]:
    try:
        return _read_cells(path, size=(frame_w, frame_h), label="frame")
    except RasterError as exc:
        raise InvalidBundleError(str(exc), reason_code=exc.reason_code) from exc


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

    layout = _layout_from_manifest(_load_manifest(bundle_root))
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
    if doc.get("schema") not in BUNDLE_SCHEMAS:
        raise InvalidBundleError("unknown bundle schema", reason_code="invalid_manifest")
    return doc


def _profile_source(profile_id: str) -> Path:
    path = _PROFILE_REGISTRY.get(profile_id)
    if path is None or not path.is_file():
        raise FinalPolishError(
            f"unknown Polish profile: {profile_id!r}",
            reason_code="unknown_polish_profile",
        )
    return path


def _valid_question_list(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    ids: list[str] = []
    for row in value:
        if not isinstance(row, dict):
            return False
        question_id = row.get("id")
        question = row.get("question")
        if not isinstance(question_id, str) or not question_id:
            return False
        if not isinstance(question, str) or not question:
            return False
        ids.append(question_id)
    return len(ids) == len(set(ids))


def _validate_profile_content(profile: dict[str, Any]) -> None:
    if profile.get("verdicts") != ["PASS", "EDIT", "UNCERTAIN"]:
        raise InvalidBundleError(
            "embedded Polish profile has invalid verdicts",
            reason_code="invalid_profile",
        )
    if not _valid_question_list(profile.get("fixed_questions")):
        raise InvalidBundleError(
            "embedded Polish profile has invalid fixed questions",
            reason_code="invalid_profile",
        )
    overrides = profile.get("motion_overrides")
    if not isinstance(overrides, dict) or any(
        not _valid_question_list(questions) for questions in overrides.values()
    ):
        raise InvalidBundleError(
            "embedded Polish profile has invalid Motion overrides",
            reason_code="invalid_profile",
        )
    for key in ("editing_rules", "audit_workflow"):
        value = profile.get(key)
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(row, str) or not row for row in value)
        ):
            raise InvalidBundleError(
                f"embedded Polish profile has invalid {key}",
                reason_code="invalid_profile",
            )
    if not isinstance(profile.get("occlusion_rule"), str) or not profile["occlusion_rule"]:
        raise InvalidBundleError(
            "embedded Polish profile has invalid occlusion rule",
            reason_code="invalid_profile",
        )


def _load_bound_profile(
    bundle_root: Path,
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    binding = manifest.get("polish_profile")
    if binding is None:
        return None
    if not isinstance(binding, dict):
        raise InvalidBundleError(
            "invalid Polish profile binding",
            reason_code="invalid_profile",
        )
    try:
        path = canonical.verify_binding(binding, root=bundle_root, label="profile")
    except canonical.BindingError as exc:
        raise InvalidBundleError(str(exc), reason_code=exc.reason_code) from exc
    if binding.get("relative_path") != "profile.json":
        raise InvalidBundleError(
            "invalid Polish profile path",
            reason_code="invalid_profile",
        )
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidBundleError(
            "invalid embedded Polish profile JSON",
            reason_code="invalid_profile",
        ) from exc
    if not isinstance(profile, dict):
        raise InvalidBundleError(
            "embedded Polish profile must be an object",
            reason_code="invalid_profile",
        )
    if (
        profile.get("schema") != PROFILE_SCHEMA
        or binding.get("schema") != PROFILE_SCHEMA
        or profile.get("id") != binding.get("id")
    ):
        raise InvalidBundleError(
            "embedded Polish profile identity mismatch",
            reason_code="profile_identity_mismatch",
        )
    _validate_profile_content(profile)
    return profile


def load_polish_brief(bundle_root: Path) -> dict[str, Any]:
    """Resolve the embedded visual questions for this bundle's Motion class."""
    manifest = _load_manifest(bundle_root)
    profile = _load_bound_profile(bundle_root, manifest)
    if profile is None:
        raise InvalidBundleError(
            "bundle has no Polish profile; initialize with --polish-profile",
            reason_code="profile_required",
        )
    overrides = profile.get("motion_overrides")
    assert isinstance(overrides, dict)
    binding = manifest["polish_profile"]
    motion_class = str(manifest["motion_class"])
    return {
        "profile": {
            "schema": profile["schema"],
            "id": profile["id"],
            "sha256": binding["sha256"],
        },
        "motion_class": motion_class,
        "occlusion_rule": profile.get("occlusion_rule"),
        "verdicts": profile["verdicts"],
        "fixed_questions": profile["fixed_questions"],
        "motion_questions": overrides.get(motion_class, []),
        "editing_rules": profile["editing_rules"],
        "audit_workflow": profile["audit_workflow"],
    }


def _ordered_frame_hashes(bundle_root: Path, layer: str) -> tuple[str, ...]:
    directory = _frame_dir(bundle_root, layer)
    return tuple(sha256_file(directory / name) for name in EXPECTED_FRAME_NAMES)


def _fingerprint_polished_hashes(
    polished_hashes: Sequence[str],
    identity_lock: IdentityLockResult | None = None,
) -> str:
    """Name the immutable report after everything the report payload depends on.

    Hashing the polished Frame digests alone (issue #300) meant a bundle re-bound
    to a new canonical identity produced a different payload at the *same*
    `reports/{fingerprint}.json` path, which `finalize_bundle` can only reject as
    a `report_conflict`. Bundles without an Identity Lock keep their historical
    fingerprints, so only lock-bound evidence is re-addressed.
    """
    joined = ":".join(polished_hashes)
    if identity_lock is not None:
        joined = ":".join(
            (joined, identity_lock.identity_sha256, identity_lock.lock_spec_sha256)
        )
    return sha256_bytes(joined.encode("utf-8"))


def _collect_draft_palette(draft_frames: list[list[list[Cell]]]) -> set[tuple[int, int, int]]:
    palette: set[tuple[int, int, int]] = set()
    for frame in draft_frames:
        for row in frame:
            for rgb in row:
                if rgb is not None:
                    palette.add(rgb)
    return palette


def _bundle_master_palette_rgb_set(bundle_root: Path) -> set[tuple[int, int, int]]:
    """Master Palette colours bound by provenance, if any."""
    manifest = _load_manifest(bundle_root)
    if _is_cell_authored_manifest(manifest):
        return set()
    sidecar = bundle_root / "provider" / "source.source.json"
    if not sidecar.is_file():
        return set()
    try:
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidBundleError(
            f"invalid provenance sidecar: {sidecar}",
            reason_code="invalid_provenance",
        ) from exc
    palette_id = doc.get("master_palette_id")
    if not isinstance(palette_id, str) or not palette_id:
        return set()
    palette_path = _REPO_ROOT / "assets" / "palettes" / f"{palette_id}.json"
    if not palette_path.is_file():
        return set()
    master = load_master_palette(palette_path)
    colors: set[tuple[int, int, int]] = set()
    for role_colors in master.role_colors.values():
        colors.update(role_colors)
    return colors


def _structural_check(
    draft_frames: list[list[list[Cell]]],
    polished_frames: list[list[list[Cell]]],
    *,
    extra_allowed_palette: set[tuple[int, int, int]] | None = None,
) -> StructuralCheckResult:
    violations: list[StructuralViolation] = []
    allowed_palette = _collect_draft_palette(draft_frames)
    if extra_allowed_palette:
        allowed_palette |= extra_allowed_palette

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
    per_frame_counts = [0 for _ in draft_frames]

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


def _load_dwarf_identity_doc() -> dict[str, Any]:
    if not _DWARF_IDENTITY_DOC.is_file():
        raise FinalPolishError(
            f"missing dwarf identity authority: {_DWARF_IDENTITY_DOC}",
            reason_code="missing_identity_authority",
        )
    doc = json.loads(_DWARF_IDENTITY_DOC.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise FinalPolishError(
            "dwarf identity authority must be a JSON object",
            reason_code="missing_identity_authority",
        )
    return doc


def _binding_sha256(doc: Mapping[str, Any], key: str) -> str:
    binding = doc.get(key)
    if not isinstance(binding, dict):
        raise FinalPolishError(
            f"dwarf identity authority missing {key}",
            reason_code="missing_identity_authority",
        )
    digest = binding.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise FinalPolishError(
            f"dwarf identity authority has invalid {key} sha256",
            reason_code="missing_identity_authority",
        )
    return digest


def _requires_image_edit_evidence(polish_profile: str | None, motion_class: str) -> bool:
    return polish_profile == "dwarf-miner" and motion_class in {"walk", "swing"}


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )


def _png_dimensions(path: Path) -> list[int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return [width, height]


def _expected_item_geometry(layout: StripLayout) -> dict[str, int]:
    return {
        "frame_w": layout.frame_w,
        "frame_h": layout.frame_h,
        "frame_count": layout.frame_count,
        "gutter": layout.gutter,
    }


def _load_json_object(
    path: Path,
    *,
    reason_code: str,
    error_class: type[FinalPolishError] = InitializationRejectedError,
) -> dict[str, Any]:
    if not path.is_file():
        raise error_class(
            f"missing JSON sidecar: {path}",
            reason_code=reason_code,
        )
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise error_class(
            f"invalid JSON sidecar: {exc}",
            reason_code=reason_code,
        ) from exc
    if not isinstance(doc, dict):
        raise error_class(
            "JSON sidecar must be an object",
            reason_code=reason_code,
        )
    return doc


def _validate_animation_provenance_record(
    record: Mapping[str, Any],
    provider_path: Path,
    motion_class: str,
    layout: StripLayout,
    *,
    identity_reference_sha256: str | None = None,
    edit_source_sha256: str | None = None,
    edit_source_path: Path | None = None,
    require_image_edit: bool = False,
    expected_raw_basename: str | None = None,
    error_class: type[FinalPolishError] = InitializationRejectedError,
) -> dict[str, Any]:
    """Validate animation-strip-provenance/0 and semantic bindings."""
    def reject(message: str, reason_code: str) -> None:
        raise error_class(message, reason_code=reason_code)

    if record.get("schema") != PROVENANCE_SCHEMA:
        reject(
            f"provenance schema must be {PROVENANCE_SCHEMA!r}",
            "invalid_provenance",
        )
    for field in PROVENANCE_REQUIRED_FIELDS:
        if field not in record:
            reject(f"provenance missing required field {field!r}", "invalid_provenance")

    for field in (
        "specification_id",
        "attempt_id",
        "generator",
        "model",
        "prompt_text",
        "prompt_sha256",
        "generation_mode",
        "generated_at",
        "acquiring_agent",
        "repository_commit",
        "raw_path",
        "raw_sha256",
        "media_type",
        "motion_class",
        "master_palette_id",
    ):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            reject(
                f"provenance field {field!r} must be a non-empty string",
                "invalid_provenance",
            )

    predecessor = record.get("predecessor_attempt_id")
    if predecessor is not None and (not isinstance(predecessor, str) or not predecessor):
        reject(
            "provenance predecessor_attempt_id must be null or a non-empty string",
            "invalid_provenance",
        )

    prompt_text = str(record["prompt_text"])
    expected_prompt_sha = sha256_bytes(prompt_text.encode("utf-8"))
    if record.get("prompt_sha256") != expected_prompt_sha:
        reject(
            "provenance prompt_sha256 does not match prompt_text",
            "invalid_provenance",
        )

    provider_sha = sha256_file(provider_path)
    if record.get("raw_sha256") != provider_sha:
        reject(
            "provider bytes differ from provenance raw_sha256",
            "provenance_hash_mismatch",
        )

    raw_path = str(record["raw_path"])
    raw_basename = expected_raw_basename or provider_path.name
    if Path(raw_path).name != raw_basename:
        reject(
            "provenance raw_path does not identify the provider input",
            "invalid_provenance",
        )

    if str(record["motion_class"]) != motion_class:
        reject(
            "provenance motion_class does not match init motion_class",
            "invalid_provenance",
        )

    generation_mode = str(record["generation_mode"])
    if generation_mode not in PROVIDER_GENERATION_MODES:
        reject(
            f"provenance generation_mode must be one of {sorted(PROVIDER_GENERATION_MODES)}",
            "invalid_provenance",
        )

    references = record.get("reference_image_sha256")
    if not isinstance(references, list):
        reject(
            "provenance reference_image_sha256 must be an array",
            "invalid_provenance",
        )
    seen_refs: set[str] = set()
    ordered_refs: list[str] = []
    for entry in references:
        if not _is_sha256_hex(entry):
            reject(
                "provenance reference_image_sha256 entries must be SHA-256 hex",
                "invalid_provenance",
            )
        ref = str(entry)
        if ref in seen_refs:
            reject(
                "provenance reference_image_sha256 must be unique",
                "invalid_provenance",
            )
        seen_refs.add(ref)
        ordered_refs.append(ref)

    edit_source = record.get("edit_source_sha256")
    if generation_mode == "text-to-image":
        if edit_source is not None:
            reject(
                "provenance edit_source_sha256 must be null for text-to-image",
                "invalid_provenance",
            )
    else:
        if not _is_sha256_hex(edit_source):
            reject(
                "provenance edit_source_sha256 must be a SHA-256 hex for image-edit",
                "invalid_provenance",
            )

    dimensions = record.get("dimensions")
    if (
        not isinstance(dimensions, list)
        or len(dimensions) != 2
        or not all(isinstance(axis, int) and axis > 0 for axis in dimensions)
    ):
        reject(
            "provenance dimensions must be a two-element positive integer array",
            "invalid_provenance",
        )
    provider_dimensions = _png_dimensions(provider_path)
    if list(dimensions) != provider_dimensions:
        declared_w, declared_h = dimensions
        actual_w, actual_h = provider_dimensions
        reject(
            "provenance_dimensions_mismatch: provenance declares "
            f"{declared_w}x{declared_h} but provider raster is {actual_w}x{actual_h}",
            "provenance_dimensions_mismatch",
        )

    item_geometry = record.get("item_geometry")
    if not isinstance(item_geometry, dict):
        reject(
            "provenance item_geometry must be an object",
            "invalid_provenance",
        )
    expected_geometry = _expected_item_geometry(layout)
    for key, expected in expected_geometry.items():
        if item_geometry.get(key) != expected:
            reject(
                f"provenance item_geometry.{key} does not match production Strip layout",
                "invalid_provenance",
            )

    if require_image_edit or generation_mode == "image-edit":
        if generation_mode != "image-edit":
            reject(
                "dwarf-miner walk/swing requires generation_mode=image-edit",
                "generation_mode_mismatch",
            )
        identity_doc = _load_dwarf_identity_doc()
        canonical_identity = _binding_sha256(identity_doc, "identity_png")
        if ordered_refs != [canonical_identity]:
            reject(
                "provenance reference_image_sha256 must bind the canonical identity",
                "reference_image_mismatch",
            )
        if identity_reference_sha256 is not None and identity_reference_sha256 != canonical_identity:
            reject(
                "identity reference bytes do not match canonical identity hash",
                "identity_hash_mismatch",
            )
        if edit_source_sha256 is not None and str(edit_source) != edit_source_sha256:
            reject(
                "provenance edit_source_sha256 does not match edit-source bytes",
                "edit_source_hash_mismatch",
            )
        if require_image_edit:
            try:
                expected_edit_source_sha = expected_image_edit_source_sha256(
                    identity_doc,
                    root=_REPO_ROOT,
                    motion_class=motion_class,
                )
            except IdentityLockError as exc:
                reject(str(exc), "missing_identity_authority")
            if str(edit_source) != expected_edit_source_sha:
                reject(
                    "provenance edit_source_sha256 must equal the identity.json "
                    "image-edit seed digest (generation_source or magenta pad)",
                    "edit_source_not_generation_source",
                )
        if edit_source_sha256 is not None and edit_source_path is not None:
            edit_source_dimensions = _png_dimensions(edit_source_path)
            if provider_dimensions != edit_source_dimensions:
                provider_w, provider_h = provider_dimensions
                edit_w, edit_h = edit_source_dimensions
                reject(
                    "edit_source_geometry_mismatch: provider raster is "
                    f"{provider_w}x{provider_h} but edit source {edit_source} is "
                    f"{edit_w}x{edit_h}; an image edit preserves the edit-source canvas",
                    "edit_source_geometry_mismatch",
                )

    return dict(record)


def _validate_provenance_sidecar(
    provider_path: Path,
    provenance_path: Path,
    motion_class: str,
    layout: StripLayout,
    *,
    polish_profile: str | None = None,
    identity_reference_path: Path | None = None,
    edit_source_path: Path | None = None,
) -> dict[str, Any]:
    record = _load_json_object(provenance_path, reason_code="invalid_provenance")
    require_image_edit = _requires_image_edit_evidence(polish_profile, motion_class)
    if require_image_edit:
        if identity_reference_path is None:
            raise InitializationRejectedError(
                "dwarf-miner walk/swing requires --identity-reference",
                reason_code="missing_identity_reference",
            )
        if edit_source_path is None:
            raise InitializationRejectedError(
                "dwarf-miner walk/swing requires --edit-source",
                reason_code="missing_edit_source",
            )
        if not identity_reference_path.is_file():
            raise InitializationRejectedError(
                f"missing identity reference: {identity_reference_path}",
                reason_code="missing_identity_reference",
            )
        if not edit_source_path.is_file():
            raise InitializationRejectedError(
                f"missing edit source: {edit_source_path}",
                reason_code="missing_edit_source",
            )
    identity_sha = (
        sha256_file(identity_reference_path)
        if identity_reference_path is not None and identity_reference_path.is_file()
        else None
    )
    edit_sha = (
        sha256_file(edit_source_path)
        if edit_source_path is not None and edit_source_path.is_file()
        else None
    )
    return _validate_animation_provenance_record(
        record,
        provider_path,
        motion_class,
        layout,
        identity_reference_sha256=identity_sha,
        edit_source_sha256=edit_sha,
        edit_source_path=edit_source_path,
        require_image_edit=require_image_edit,
    )


def _legacy_bundles_allowlist_path() -> Path:
    return _REPO_ROOT / "acquisition-controls" / "legacy-bundles.json"


@functools.lru_cache(maxsize=1)
def _load_legacy_bundle_allowlist() -> tuple[tuple[str, str], ...]:
    path = _legacy_bundles_allowlist_path()
    if not path.is_file():
        return ()
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != LEGACY_BUNDLES_SCHEMA:
        raise InvalidBundleError(
            f"legacy bundle allowlist schema must be {LEGACY_BUNDLES_SCHEMA!r}",
            reason_code="invalid_legacy_allowlist",
        )
    entries = doc.get("bundles")
    if not isinstance(entries, list):
        raise InvalidBundleError(
            "legacy bundle allowlist bundles must be an array",
            reason_code="invalid_legacy_allowlist",
        )
    allowed: list[tuple[str, str]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise InvalidBundleError(
                f"legacy bundle allowlist entry[{index}] must be an object",
                reason_code="invalid_legacy_allowlist",
            )
        specification_id = entry.get("specification_id")
        provider_sha256 = entry.get("provider_sha256")
        if not isinstance(specification_id, str) or not specification_id:
            raise InvalidBundleError(
                f"legacy bundle allowlist entry[{index}] missing specification_id",
                reason_code="invalid_legacy_allowlist",
            )
        if not _is_sha256_hex(provider_sha256):
            raise InvalidBundleError(
                f"legacy bundle allowlist entry[{index}] provider_sha256 must be SHA-256 hex",
                reason_code="invalid_legacy_allowlist",
            )
        allowed.append((specification_id, str(provider_sha256)))
    return tuple(allowed)


def _legacy_bundle_allowed(specification_id: str, provider_sha256: str) -> bool:
    return (specification_id, provider_sha256) in _load_legacy_bundle_allowlist()


def _store_row_by_attempt_id(
    store_rows: Sequence[Mapping[str, Any]],
    attempt_id: str,
) -> Mapping[str, Any] | None:
    for row in store_rows:
        if str(row.get("attempt_id")) == attempt_id:
            return row
    return None


def _reject_unregistered_attempt(message: str) -> None:
    raise InitializationRejectedError(message, reason_code="attempt_not_registered")


def _assert_attempt_registered_for_init(
    provenance: Mapping[str, Any],
    provider_sha256: str,
    store_rows: Sequence[Mapping[str, Any]],
    *,
    store_root: Path,
) -> Mapping[str, Any]:
    attempt_id = str(provenance["attempt_id"])
    row = _store_row_by_attempt_id(store_rows, attempt_id)
    if row is None:
        _reject_unregistered_attempt(
            f"provenance attempt_id {attempt_id!r} is not registered in the attested store"
        )
    if str(row["raw_sha256"]) != provider_sha256:
        _reject_unregistered_attempt(
            "registered Attempt raw_sha256 differs from provider PNG digest"
        )
    if row.get("outcome") == "rejected":
        _reject_unregistered_attempt("a rejected Attempt cannot be selected for init")
    store_provenance = _load_json_object(
        store_root / str(row["provenance_path"]),
        reason_code="attempt_not_registered",
    )
    for field in ("generation_mode", "motion_class", "prompt_sha256"):
        if store_provenance.get(field) != provenance.get(field):
            _reject_unregistered_attempt(
                f"registered Attempt {field!r} disagrees with provenance sidecar"
            )
    matching = [candidate for candidate in store_rows if str(candidate["raw_sha256"]) == provider_sha256]
    if not matching or str(matching[-1]["attempt_id"]) != attempt_id:
        _reject_unregistered_attempt(
            "no registered Attempt matches the provider PNG digest"
        )
    return row


def _project_store_rows_to_ledger(
    store_rows: Sequence[Mapping[str, Any]],
    selected_attempt_id: str,
) -> dict[str, Any]:
    selected_index: int | None = None
    for index, row in enumerate(store_rows):
        if str(row["attempt_id"]) == selected_attempt_id:
            selected_index = index
            break
    if selected_index is None:
        raise InitializationRejectedError(
            f"selected attempt_id {selected_attempt_id!r} is absent from the store projection",
            reason_code="attempt_not_registered",
        )
    attempts: list[dict[str, Any]] = []
    for index, row in enumerate(store_rows[: selected_index + 1]):
        ledger_row: dict[str, Any] = {
            "attempt_id": row["attempt_id"],
            "predecessor_attempt_id": row.get("predecessor_attempt_id"),
            "outcome": row["outcome"],
            "rejection_reason": row.get("rejection_reason"),
            "prompt_sha256": row["prompt_sha256"],
            "raw_sha256": row["raw_sha256"],
            "selected": index == selected_index,
        }
        attempts.append(ledger_row)
    return {"schema": ATTEMPT_LEDGER_SCHEMA, "attempts": attempts}


def _build_legacy_single_row_attempt_ledger(provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": ATTEMPT_LEDGER_SCHEMA,
        "attempts": [
            {
                "attempt_id": provenance["attempt_id"],
                "predecessor_attempt_id": provenance.get("predecessor_attempt_id"),
                "outcome": "accepted",
                "rejection_reason": None,
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": provenance["raw_sha256"],
                "selected": True,
            }
        ],
    }


def _build_initial_attempt_ledger(
    provenance: Mapping[str, Any],
    store_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    selected_attempt_id = str(provenance["attempt_id"])
    return _project_store_rows_to_ledger(store_rows, selected_attempt_id)


_PROJECTED_LEDGER_FIELDS = (
    "attempt_id",
    "predecessor_attempt_id",
    "outcome",
    "rejection_reason",
    "prompt_sha256",
    "raw_sha256",
    "selected",
)


def _ledger_attestation_view(ledger: Mapping[str, Any]) -> dict[str, Any]:
    attempts = ledger.get("attempts")
    if not isinstance(attempts, list):
        raise InvalidBundleError(
            "attempt ledger attempts must be a non-empty array",
            reason_code="invalid_attempt_ledger",
        )
    return {
        "schema": ledger.get("schema"),
        "attempts": [
            {field: row.get(field) for field in _PROJECTED_LEDGER_FIELDS}
            for row in attempts
            if isinstance(row, dict)
        ],
    }


def _bundle_provenance_record(
    bundle_root: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    if manifest.get("schema") == BUNDLE_SCHEMA:
        provenance_binding = manifest.get("provenance")
        if not isinstance(provenance_binding, dict):
            return None
        provenance_path = bundle_root / str(provenance_binding["relative_path"])
    else:
        provenance_path = bundle_root / "provider" / "source.source.json"
    if not provenance_path.is_file():
        return None
    return _load_json_object(
        provenance_path,
        reason_code="invalid_provenance",
        error_class=InvalidBundleError,
    )


def _specification_id_for_bundle(
    bundle_root: Path,
    provenance: Mapping[str, Any] | None,
) -> str | None:
    if provenance is not None:
        specification_id = provenance.get("specification_id")
        if isinstance(specification_id, str) and specification_id:
            return specification_id
    try:
        return bundle_root.resolve().relative_to(_REPO_ROOT / "assets").as_posix()
    except ValueError:
        return None


def _attestation_report_payload(state: AttestationState) -> dict[str, Any]:
    payload: dict[str, Any] = {"state": state.state}
    if state.attempt_id is not None:
        payload["attempt_id"] = state.attempt_id
    if state.store_path is not None:
        payload["store_path"] = state.store_path
    if state.generation_mode is not None:
        payload["generation_mode"] = state.generation_mode
    if state.base_specification_id is not None:
        payload["base_specification_id"] = state.base_specification_id
    if state.base_frames_sha256 is not None:
        payload["base_frames_sha256"] = list(state.base_frames_sha256)
    if state.base_frame_mapping is not None:
        payload["base_frame_mapping"] = list(state.base_frame_mapping)
    if state.cell_delta_ledger_sha256 is not None:
        payload["cell_delta_ledger_sha256"] = state.cell_delta_ledger_sha256
    return payload


def _is_cell_authored_manifest(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("generation_mode") == CELL_AUTHOR_GENERATION_MODE


def _reject_generation_mode_changed(message: str) -> None:
    raise InvalidBundleError(message, reason_code="generation_mode_changed")


def _assert_provider_bundle_has_no_cell_authoring(manifest: Mapping[str, Any]) -> None:
    if manifest.get("cell_authoring") is not None:
        _reject_generation_mode_changed("provider bundle must not carry cell_authoring")


def _assert_cell_bundle_has_no_provider_fields(manifest: Mapping[str, Any]) -> None:
    forbidden = ("provider", "provenance", "attempt_ledger")
    for field in forbidden:
        if field in manifest:
            _reject_generation_mode_changed(
                f"cell-author bundle must not carry provider field {field!r}"
            )


def _binding_sha256_dict(binding: Mapping[str, Any]) -> str:
    digest = binding.get("sha256")
    if not isinstance(digest, str) or not _is_sha256_hex(digest):
        raise InvalidBundleError(
            "binding sha256 must be SHA-256 hex",
            reason_code="invalid_manifest",
        )
    return digest


def _load_base_release_frames(
    base_bundle_root: Path, motion_class: str
) -> list[list[list[Cell]]]:
    """Load a base Bundle's release Frames, embedded onto ``motion_class``'s canvas."""
    manifest = _load_manifest(base_bundle_root)
    anchor_layout = _layout_from_manifest(manifest)
    release_dir = _frame_dir(base_bundle_root, "release")
    if not release_dir.is_dir():
        raise InitializationRejectedError(
            f"base bundle missing release frames: {base_bundle_root}",
            reason_code="missing_release_frames",
        )
    frames = [
        _load_logical_frame_png(
            release_dir / name,
            frame_w=anchor_layout.frame_w,
            frame_h=anchor_layout.frame_h,
        )
        for name in EXPECTED_FRAME_NAMES
    ]
    class_geometry = resolve_class_frame_geometry(motion_class)
    class_layout = StripLayout(
        frame_w=class_geometry.frame_w,
        frame_h=class_geometry.frame_h,
        frame_count=anchor_layout.frame_count,
        gutter=anchor_layout.gutter,
    )
    return _embed_frames_for_manifest_layout(
        frames,
        motion_class=motion_class,
        layout=class_layout,
        anchor_layout=anchor_layout,
    )


def _resolve_base_bundle_attestation(
    base_bundle_root: Path,
) -> AttestationState:
    manifest = _load_manifest(base_bundle_root)
    if _is_cell_authored_manifest(manifest):
        raise InitializationRejectedError(
            "cell-author bundle cannot serve as a cell-author base",
            reason_code="cell_author_base_forbidden",
        )
    provenance = _bundle_provenance_record(base_bundle_root, manifest)
    try:
        attestation = _resolve_bundle_attestation(
            base_bundle_root,
            manifest,
            provenance=provenance,
        )
    except InvalidBundleError as exc:
        if exc.reason_code in {
            "attempt_not_registered",
            "missing_attempt_ledger",
            "attempt_ledger_not_attested",
        }:
            raise InitializationRejectedError(
                "base bundle is not attested or legacy-allowlisted",
                reason_code="unattested_base_bundle",
            ) from exc
        raise
    if attestation is None or attestation.state not in {"attested", "legacy"}:
        raise InitializationRejectedError(
            "base bundle is not attested or legacy-allowlisted",
            reason_code="unattested_base_bundle",
        )
    return attestation


def _validate_pose_plan_document(
    pose_plan: Mapping[str, Any],
    *,
    motion_class: str,
    base_specification_id: str,
    base_frame_mapping: Sequence[int],
) -> None:
    if pose_plan.get("schema") != MOTION_POSE_PLAN_SCHEMA:
        raise InitializationRejectedError(
            f"pose plan schema must be {MOTION_POSE_PLAN_SCHEMA!r}",
            reason_code="invalid_pose_plan",
        )
    if str(pose_plan.get("motion_class")) != motion_class:
        raise InitializationRejectedError(
            "pose plan motion_class does not match init motion_class",
            reason_code="invalid_pose_plan",
        )
    if str(pose_plan.get("base_specification_id")) != base_specification_id:
        raise InitializationRejectedError(
            "pose plan base_specification_id does not match ledger",
            reason_code="invalid_pose_plan",
        )
    mapping = pose_plan.get("base_frame_mapping")
    if list(mapping or []) != list(base_frame_mapping):
        raise InitializationRejectedError(
            "pose plan base_frame_mapping does not match ledger",
            reason_code="invalid_pose_plan",
        )


def _validate_cell_author_provenance_record(
    record: Mapping[str, Any],
    *,
    motion_class: str,
    specification_id: str,
    base_specification_id: str,
    base_frames_sha256: Sequence[str],
    base_frame_mapping: Sequence[int],
    pose_plan_sha256: str,
    ledger_sha256: str,
) -> None:
    if record.get("schema") != CELL_AUTHOR_PROVENANCE_SCHEMA:
        raise InitializationRejectedError(
            f"provenance schema must be {CELL_AUTHOR_PROVENANCE_SCHEMA!r}",
            reason_code="invalid_provenance",
        )
    for field in CELL_AUTHOR_PROVENANCE_REQUIRED_FIELDS:
        if field not in record:
            raise InitializationRejectedError(
                f"provenance missing required field {field!r}",
                reason_code="invalid_provenance",
            )
    if str(record["generation_mode"]) != CELL_AUTHOR_GENERATION_MODE:
        raise InitializationRejectedError(
            "provenance generation_mode must be cell-author",
            reason_code="invalid_provenance",
        )
    if str(record["specification_id"]) != specification_id:
        raise InitializationRejectedError(
            "provenance specification_id does not match init specification_id",
            reason_code="invalid_provenance",
        )
    if str(record["motion_class"]) != motion_class:
        raise InitializationRejectedError(
            "provenance motion_class does not match init motion_class",
            reason_code="invalid_provenance",
        )
    if str(record["base_specification_id"]) != base_specification_id:
        raise InitializationRejectedError(
            "provenance base_specification_id mismatch",
            reason_code="invalid_provenance",
        )
    if list(record["base_frames_sha256"]) != list(base_frames_sha256):
        raise InitializationRejectedError(
            "provenance base_frames_sha256 mismatch",
            reason_code="invalid_provenance",
        )
    if list(record["base_frame_mapping"]) != list(base_frame_mapping):
        raise InitializationRejectedError(
            "provenance base_frame_mapping mismatch",
            reason_code="invalid_provenance",
        )
    pose_binding = record["pose_plan"]
    if not isinstance(pose_binding, dict):
        raise InitializationRejectedError(
            "provenance pose_plan must be an object",
            reason_code="invalid_provenance",
        )
    if _binding_sha256_dict(pose_binding) != pose_plan_sha256:
        raise InitializationRejectedError(
            "provenance pose_plan sha256 mismatch",
            reason_code="invalid_provenance",
        )
    ledger_binding = record["cell_delta_ledger"]
    if not isinstance(ledger_binding, dict):
        raise InitializationRejectedError(
            "provenance cell_delta_ledger must be an object",
            reason_code="invalid_provenance",
        )
    if _binding_sha256_dict(ledger_binding) != ledger_sha256:
        raise InitializationRejectedError(
            "provenance cell_delta_ledger sha256 mismatch",
            reason_code="invalid_provenance",
        )
    for field in (
        "authoring_agent",
        "authoring_session_id",
        "repository_commit",
    ):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            raise InitializationRejectedError(
                f"provenance field {field!r} must be a non-empty string",
                reason_code="invalid_provenance",
            )


def _load_authored_frames(
    authored_frames_dir: Path,
    *,
    frame_count: int,
    frame_w: int,
    frame_h: int,
) -> list[list[list[Cell]]]:
    if not authored_frames_dir.is_dir():
        raise InitializationRejectedError(
            f"missing authored frames directory: {authored_frames_dir}",
            reason_code="missing_authored_frames",
        )
    frames: list[list[list[Cell]]] = []
    for index in range(frame_count):
        path = authored_frames_dir / f"frame-{index}.png"
        if not path.is_file():
            raise InitializationRejectedError(
                f"missing authored frame: {path.name}",
                reason_code="missing_authored_frames",
            )
        try:
            frames.append(_read_cells(path, size=(frame_w, frame_h), label="authored frame"))
        except RasterError as exc:
            raise InitializationRejectedError(
                str(exc),
                reason_code=exc.reason_code or "missing_authored_frames",
            ) from exc
    return frames


def _cell_author_attestation_from_bindings(
    *,
    base_specification_id: str,
    base_frames_sha256: Sequence[str],
    base_frame_mapping: Sequence[int],
    ledger_sha256: str,
) -> AttestationState:
    return AttestationState(
        state=CELL_AUTHOR_GENERATION_MODE,
        generation_mode=CELL_AUTHOR_GENERATION_MODE,
        base_specification_id=base_specification_id,
        base_frames_sha256=tuple(base_frames_sha256),
        base_frame_mapping=tuple(base_frame_mapping),
        cell_delta_ledger_sha256=ledger_sha256,
    )


def _resolve_bundle_attestation(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any] | None = None,
) -> AttestationState | None:
    if _is_cell_authored_manifest(manifest):
        authoring = manifest.get("cell_authoring")
        if not isinstance(authoring, dict):
            raise InvalidBundleError(
                "cell-author bundle missing cell_authoring block",
                reason_code="missing_provenance",
            )
        ledger_binding = authoring.get("cell_delta_ledger")
        if not isinstance(ledger_binding, dict):
            raise InvalidBundleError(
                "cell-author bundle missing cell_delta_ledger binding",
                reason_code="missing_provenance",
            )
        return _cell_author_attestation_from_bindings(
            base_specification_id=str(authoring["base_specification_id"]),
            base_frames_sha256=tuple(authoring["base_frames_sha256"]),
            base_frame_mapping=tuple(authoring["base_frame_mapping"]),
            ledger_sha256=_binding_sha256_dict(ledger_binding),
        )

    if manifest.get("schema") != BUNDLE_SCHEMA:
        provenance = provenance or _bundle_provenance_record(bundle_root, manifest)
        specification_id = _specification_id_for_bundle(bundle_root, provenance)
        if specification_id is None:
            return None
        provider_sha256 = sha256_file(_provider_path(bundle_root))
        if _legacy_bundle_allowed(specification_id, provider_sha256):
            return AttestationState(state="legacy")
        return None

    provenance = provenance or _bundle_provenance_record(bundle_root, manifest)
    if provenance is None:
        raise InvalidBundleError(
            "schema /2 bundle missing provenance record",
            reason_code="missing_provenance",
        )
    specification_id = str(provenance["specification_id"])
    provider_sha256 = sha256_file(_provider_path(bundle_root))
    if _legacy_bundle_allowed(specification_id, provider_sha256):
        return AttestationState(state="legacy")

    from pipeline.asset_acquire import acquisition_controls_root, load_asset_attempts

    store_root = acquisition_controls_root(_REPO_ROOT)
    store_rows = load_asset_attempts(store_root, specification_id)
    if not store_rows:
        raise InvalidBundleError(
            f"no attested Attempt rows for specification {specification_id!r}",
            reason_code="attempt_not_registered",
        )
    selected_attempt_id = str(provenance["attempt_id"])
    expected_ledger = _project_store_rows_to_ledger(store_rows, selected_attempt_id)
    ledger_binding = manifest.get("attempt_ledger")
    if not isinstance(ledger_binding, dict):
        raise InvalidBundleError(
            "schema /2 bundle missing attempt_ledger binding",
            reason_code="missing_attempt_ledger",
        )
    ledger_path = bundle_root / str(ledger_binding["relative_path"])
    committed_ledger = _load_json_object(
        ledger_path,
        reason_code="invalid_attempt_ledger",
        error_class=InvalidBundleError,
    )
    if canonical.canonical_value(_ledger_attestation_view(committed_ledger)) != canonical.canonical_value(
        _ledger_attestation_view(expected_ledger)
    ):
        raise InvalidBundleError(
            "committed attempt ledger disagrees with attested store projection",
            reason_code="attempt_ledger_not_attested",
        )
    return AttestationState(
        state="attested",
        attempt_id=selected_attempt_id,
        store_path=ATTEMPTS_JSONL_REL,
    )

def _validate_attempt_ledger_row(row: Mapping[str, Any], *, where: str) -> None:
    for field in (
        "attempt_id",
        "outcome",
        "prompt_sha256",
        "raw_sha256",
    ):
        value = row.get(field)
        if not isinstance(value, str) or not value:
            raise InvalidBundleError(
                f"attempt ledger row missing {field!r}",
                reason_code="invalid_attempt_ledger",
            )
    predecessor = row.get("predecessor_attempt_id")
    if predecessor is not None and (not isinstance(predecessor, str) or not predecessor):
        raise InvalidBundleError(
            "attempt ledger predecessor_attempt_id must be null or a non-empty string",
            reason_code="invalid_attempt_ledger",
        )
    outcome = str(row["outcome"])
    if outcome not in ATTEMPT_OUTCOMES:
        raise InvalidBundleError(
            f"attempt ledger outcome must be one of {sorted(ATTEMPT_OUTCOMES)}",
            reason_code="invalid_attempt_ledger",
        )
    rejection_reason = row.get("rejection_reason")
    if outcome == "accepted":
        if rejection_reason is not None:
            raise InvalidBundleError(
                "accepted attempt ledger row must have null rejection_reason",
                reason_code="invalid_attempt_ledger",
            )
        if row.get("rejection_detail") is not None:
            raise InvalidBundleError(
                "accepted attempt ledger row must have null rejection_detail",
                reason_code="invalid_attempt_ledger",
            )
    else:
        if not isinstance(rejection_reason, str) or not rejection_reason:
            raise InvalidBundleError(
                "rejected attempt ledger row requires rejection_reason",
                reason_code="invalid_attempt_ledger",
            )
        rejection_detail = row.get("rejection_detail")
        if rejection_detail is not None:
            if not isinstance(rejection_detail, dict):
                raise InvalidBundleError(
                    "attempt ledger rejection_detail must be an object",
                    reason_code="invalid_attempt_ledger",
                )
            schema = rejection_detail.get("schema")
            if not isinstance(schema, str) or not schema:
                raise InvalidBundleError(
                    "attempt ledger rejection_detail requires schema",
                    reason_code="invalid_attempt_ledger",
                )
            if schema == IDENTITY_LOCK_NEAR_MISS_SCHEMA:
                primary_reason_code = rejection_detail.get("primary_reason_code")
                if not isinstance(primary_reason_code, str) or not primary_reason_code:
                    raise InvalidBundleError(
                        "identity-lock near-miss rejection_detail requires "
                        "primary_reason_code",
                        reason_code="invalid_attempt_ledger",
                    )
    if not _is_sha256_hex(row.get("prompt_sha256")):
        raise InvalidBundleError(
            "attempt ledger prompt_sha256 must be SHA-256 hex",
            reason_code="invalid_attempt_ledger",
        )
    if not _is_sha256_hex(row.get("raw_sha256")):
        raise InvalidBundleError(
            "attempt ledger raw_sha256 must be SHA-256 hex",
            reason_code="invalid_attempt_ledger",
        )
    if not isinstance(row.get("selected"), bool):
        raise InvalidBundleError(
            "attempt ledger selected must be a boolean",
            reason_code="invalid_attempt_ledger",
        )


def _validate_attempt_ledger_document(
    ledger: Mapping[str, Any],
    provenance: Mapping[str, Any],
    *,
    provider_sha256: str,
    original_filename: str,
    where: str,
) -> None:
    if ledger.get("schema") != ATTEMPT_LEDGER_SCHEMA:
        raise InvalidBundleError(
            f"attempt ledger schema must be {ATTEMPT_LEDGER_SCHEMA!r}",
            reason_code="invalid_attempt_ledger",
        )
    attempts = ledger.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise InvalidBundleError(
            "attempt ledger attempts must be a non-empty array",
            reason_code="invalid_attempt_ledger",
        )

    seen_ids: set[str] = set()
    selected_indices: list[int] = []
    id_to_index: dict[str, int] = {}

    for index, row in enumerate(attempts):
        if not isinstance(row, dict):
            raise InvalidBundleError(
                "attempt ledger row must be an object",
                reason_code="invalid_attempt_ledger",
            )
        _validate_attempt_ledger_row(row, where=f"{where}[{index}]")
        attempt_id = str(row["attempt_id"])
        if attempt_id in seen_ids:
            raise InvalidBundleError(
                f"duplicate attempt_id in ledger: {attempt_id!r}",
                reason_code="invalid_attempt_ledger",
            )
        seen_ids.add(attempt_id)
        id_to_index[attempt_id] = index
        if row.get("selected"):
            selected_indices.append(index)

    if len(selected_indices) != 1:
        raise InvalidBundleError(
            "attempt ledger must contain exactly one selected row",
            reason_code="invalid_attempt_ledger",
        )
    selected_index = selected_indices[0]
    if selected_index != len(attempts) - 1:
        raise InvalidBundleError(
            "selected attempt ledger row must be the final row",
            reason_code="invalid_attempt_ledger",
        )

    selected = attempts[selected_index]
    predecessor = selected.get("predecessor_attempt_id")
    if selected_index == 0:
        if predecessor is not None:
            raise InvalidBundleError(
                "first attempt ledger row must have null predecessor_attempt_id",
                reason_code="invalid_attempt_ledger",
            )
    else:
        if not isinstance(predecessor, str):
            raise InvalidBundleError(
                "selected attempt must name a predecessor_attempt_id",
                reason_code="invalid_attempt_ledger",
            )
        if id_to_index.get(predecessor) != selected_index - 1:
            raise InvalidBundleError(
                "attempt ledger predecessor chain is broken",
                reason_code="invalid_attempt_ledger",
            )
        if attempts[selected_index - 1].get("outcome") != "rejected":
            raise InvalidBundleError(
                "predecessor attempt must be rejected",
                reason_code="invalid_attempt_ledger",
            )

    for index, row in enumerate(attempts):
        if index < len(attempts) - 1 and row.get("outcome") != "rejected":
            raise InvalidBundleError(
                "non-final attempt ledger rows must be rejected",
                reason_code="invalid_attempt_ledger",
            )
        if index < len(attempts) - 1 and row.get("selected"):
            raise InvalidBundleError(
                "only the final attempt ledger row may be selected",
                reason_code="invalid_attempt_ledger",
            )
        predecessor_id = row.get("predecessor_attempt_id")
        if predecessor_id is None:
            if index != 0:
                raise InvalidBundleError(
                    "only the first attempt may have null predecessor_attempt_id",
                    reason_code="invalid_attempt_ledger",
                )
        else:
            pred_index = id_to_index.get(str(predecessor_id))
            if pred_index is None:
                raise InvalidBundleError(
                    f"missing predecessor attempt_id {predecessor_id!r}",
                    reason_code="invalid_attempt_ledger",
                )
            if pred_index != index - 1:
                raise InvalidBundleError(
                    "attempt ledger predecessor chain is not sequential",
                    reason_code="invalid_attempt_ledger",
                )

    if str(provenance.get("attempt_id")) != str(selected["attempt_id"]):
        raise InvalidBundleError(
            "bundled provenance attempt_id disagrees with selected ledger row",
            reason_code="attempt_ledger_mismatch",
        )
    if provenance.get("prompt_sha256") != selected["prompt_sha256"]:
        raise InvalidBundleError(
            "bundled provenance prompt_sha256 disagrees with selected ledger row",
            reason_code="attempt_ledger_mismatch",
        )
    if provenance.get("raw_sha256") != selected["raw_sha256"]:
        raise InvalidBundleError(
            "bundled provenance raw_sha256 disagrees with selected ledger row",
            reason_code="attempt_ledger_mismatch",
        )
    if selected["raw_sha256"] != provider_sha256:
        raise InvalidBundleError(
            "selected attempt raw_sha256 does not match bundled provider",
            reason_code="attempt_ledger_mismatch",
        )
    if provenance.get("raw_sha256") != provider_sha256:
        raise InvalidBundleError(
            "bundled provenance raw_sha256 does not match provider",
            reason_code="provenance_hash_mismatch",
        )


def _verify_hash_binding(
    bundle_root: Path,
    binding: Mapping[str, Any],
    *,
    label: str,
) -> None:
    try:
        canonical.verify_binding(
            binding,
            root=bundle_root,
            label=label,
            path_key="relative_path",
        )
    except canonical.BindingError as exc:
        reason_code = exc.reason_code
        if reason_code == f"invalid_{label}":
            reason_code = f"{label}_hash_mismatch"
        raise InvalidBundleError(str(exc), reason_code=reason_code) from exc


def _verify_evidence_bindings(
    bundle_root: Path,
    manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], AttestationState]:
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise InvalidBundleError(
            "schema /2 bundle expected for evidence bindings",
            reason_code="missing_provenance",
        )
    _assert_provider_bundle_has_no_cell_authoring(manifest)

    provenance_binding = manifest.get("provenance")
    if not isinstance(provenance_binding, dict):
        raise InvalidBundleError(
            "schema /2 bundle missing provenance binding",
            reason_code="missing_provenance",
        )
    _verify_hash_binding(bundle_root, provenance_binding, label="provenance")
    provenance_path = bundle_root / str(provenance_binding["relative_path"])
    provenance = _load_json_object(
        provenance_path,
        reason_code="invalid_provenance",
        error_class=InvalidBundleError,
    )

    provider_rel = manifest["provider"]["relative_path"]
    provider_path = bundle_root / provider_rel
    provider_sha = sha256_file(provider_path)
    layout = _probe_layout_for_manifest(manifest)
    polish_profile_id = (
        None
        if manifest.get("polish_profile") is None
        else str(manifest["polish_profile"]["id"])
    )
    _validate_animation_provenance_record(
        provenance,
        provider_path,
        str(manifest["motion_class"]),
        layout,
        identity_reference_sha256=(
            sha256_file(bundle_root / "reference" / "identity.png")
            if (bundle_root / "reference" / "identity.png").is_file()
            else None
        ),
        edit_source_sha256=(
            sha256_file(bundle_root / "provider" / "edit-source.png")
            if (bundle_root / "provider" / "edit-source.png").is_file()
            else None
        ),
        edit_source_path=(
            bundle_root / "provider" / "edit-source.png"
            if (bundle_root / "provider" / "edit-source.png").is_file()
            else None
        ),
        require_image_edit=_requires_image_edit_evidence(
            polish_profile_id,
            str(manifest["motion_class"]),
        ),
        expected_raw_basename=str(manifest["provider"]["original_filename"]),
        error_class=InvalidBundleError,
    )

    identity_binding = manifest.get("identity_reference")
    edit_binding = manifest.get("edit_source")
    if _requires_image_edit_evidence(polish_profile_id, str(manifest["motion_class"])):
        if identity_binding is None:
            raise InvalidBundleError(
                "schema /2 dwarf-miner walk/swing bundle missing identity_reference binding",
                reason_code="missing_identity_reference",
            )
        if edit_binding is None:
            raise InvalidBundleError(
                "schema /2 dwarf-miner walk/swing bundle missing edit_source binding",
                reason_code="missing_edit_source",
            )
    if identity_binding is not None:
        _verify_hash_binding(bundle_root, identity_binding, label="identity_reference")
    if edit_binding is not None:
        _verify_hash_binding(bundle_root, edit_binding, label="edit_source")

    ledger_binding = manifest.get("attempt_ledger")
    if not isinstance(ledger_binding, dict):
        raise InvalidBundleError(
            "schema /2 bundle missing attempt_ledger binding",
            reason_code="missing_attempt_ledger",
        )
    _verify_hash_binding(bundle_root, ledger_binding, label="attempt_ledger")
    ledger_path = bundle_root / str(ledger_binding["relative_path"])
    ledger = _load_json_object(
        ledger_path,
        reason_code="invalid_attempt_ledger",
        error_class=InvalidBundleError,
    )
    attestation = _resolve_bundle_attestation(
        bundle_root,
        manifest,
        provenance=provenance,
    )
    if attestation is None:
        raise InvalidBundleError(
            "bundle has no attested or legacy Attempt registration",
            reason_code="attempt_not_registered",
        )
    _validate_attempt_ledger_document(
        ledger,
        provenance,
        provider_sha256=provider_sha,
        original_filename=str(manifest["provider"]["original_filename"]),
        where=str(ledger_path),
    )

    return provenance, attestation


def _verify_cell_author_bindings(
    bundle_root: Path,
    manifest: Mapping[str, Any],
) -> AttestationState:
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise InvalidBundleError(
            "schema /2 bundle expected for cell-author bindings",
            reason_code="missing_provenance",
        )
    if not _is_cell_authored_manifest(manifest):
        _reject_generation_mode_changed("manifest generation_mode is not cell-author")
    _assert_cell_bundle_has_no_provider_fields(manifest)

    authoring = manifest.get("cell_authoring")
    if not isinstance(authoring, dict):
        raise InvalidBundleError(
            "cell-author bundle missing cell_authoring block",
            reason_code="missing_provenance",
        )

    provenance_binding = authoring.get("provenance")
    if not isinstance(provenance_binding, dict):
        raise InvalidBundleError(
            "cell-author bundle missing provenance binding",
            reason_code="missing_provenance",
        )
    _verify_hash_binding(bundle_root, provenance_binding, label="provenance")
    provenance_path = bundle_root / str(provenance_binding["relative_path"])
    provenance = _load_json_object(
        provenance_path,
        reason_code="invalid_provenance",
        error_class=InvalidBundleError,
    )

    if str(provenance.get("generation_mode")) != CELL_AUTHOR_GENERATION_MODE:
        _reject_generation_mode_changed(
            "cell-author provenance generation_mode does not match manifest"
        )
    if manifest.get("generation_mode") != provenance.get("generation_mode"):
        _reject_generation_mode_changed(
            "manifest generation_mode does not match cell-author provenance"
        )

    pose_binding = authoring.get("pose_plan")
    ledger_binding = authoring.get("cell_delta_ledger")
    if not isinstance(pose_binding, dict) or not isinstance(ledger_binding, dict):
        raise InvalidBundleError(
            "cell-author bundle missing pose_plan or cell_delta_ledger binding",
            reason_code="missing_provenance",
        )
    _verify_hash_binding(bundle_root, pose_binding, label="pose_plan")
    _verify_hash_binding(bundle_root, ledger_binding, label="cell_delta_ledger")

    pose_plan = _load_json_object(
        bundle_root / str(pose_binding["relative_path"]),
        reason_code="invalid_pose_plan",
        error_class=InvalidBundleError,
    )
    ledger = _load_json_object(
        bundle_root / str(ledger_binding["relative_path"]),
        reason_code="invalid_cell_delta_ledger",
        error_class=InvalidBundleError,
    )

    base_specification_id = str(authoring["base_specification_id"])
    base_frames_sha256 = tuple(str(value) for value in authoring["base_frames_sha256"])
    base_frame_mapping = tuple(int(value) for value in authoring["base_frame_mapping"])
    ledger_sha256 = _binding_sha256_dict(ledger_binding)
    pose_plan_sha256 = _binding_sha256_dict(pose_binding)

    _validate_cell_author_provenance_record(
        provenance,
        motion_class=str(manifest["motion_class"]),
        specification_id=str(provenance["specification_id"]),
        base_specification_id=base_specification_id,
        base_frames_sha256=base_frames_sha256,
        base_frame_mapping=base_frame_mapping,
        pose_plan_sha256=pose_plan_sha256,
        ledger_sha256=ledger_sha256,
    )
    _validate_pose_plan_document(
        pose_plan,
        motion_class=str(manifest["motion_class"]),
        base_specification_id=base_specification_id,
        base_frame_mapping=base_frame_mapping,
    )

    if list(provenance["base_frames_sha256"]) != list(base_frames_sha256):
        raise InvalidBundleError(
            "cell-author provenance base_frames_sha256 mismatch",
            reason_code="invalid_provenance",
        )
    if list(provenance["base_frame_mapping"]) != list(base_frame_mapping):
        raise InvalidBundleError(
            "cell-author provenance base_frame_mapping mismatch",
            reason_code="invalid_provenance",
        )

    return _cell_author_attestation_from_bindings(
        base_specification_id=base_specification_id,
        base_frames_sha256=base_frames_sha256,
        base_frame_mapping=base_frame_mapping,
        ledger_sha256=ledger_sha256,
    )


def _replay_cell_author_drafts(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> list[list[list[Cell]]]:
    authoring = manifest["cell_authoring"]
    base_bindings = authoring.get("base_release_frames")
    if not isinstance(base_bindings, list):
        raise InvalidBundleError(
            "cell-author bundle missing base_release_frames bindings",
            reason_code="missing_provenance",
        )
    base_frames: list[list[list[Cell]]] = []
    layout = _layout_from_manifest(manifest)
    for binding in base_bindings:
        if not isinstance(binding, dict):
            raise InvalidBundleError(
                "base_release_frames entry must be an object",
                reason_code="invalid_manifest",
            )
        _verify_hash_binding(bundle_root, binding, label="base_release_frame")
        base_frames.append(
            _load_logical_frame_png(
                bundle_root / str(binding["relative_path"]),
                frame_w=layout.frame_w,
                frame_h=layout.frame_h,
            )
        )
    try:
        validate_cell_delta_ledger(base_frames, ledger)
    except CellDeltaError as exc:
        raise InvalidBundleError(str(exc), reason_code=exc.reason_code) from exc
    draft_frames = _load_frame_sequence(bundle_root, "draft")
    try:
        assert_cell_delta_replay(base_frames, draft_frames, ledger)
    except CellDeltaError as exc:
        raise InvalidBundleError(str(exc), reason_code=exc.reason_code) from exc
    return draft_frames


def _init_ingest_allowed(ingest: IngestResult) -> bool:
    """Allow bundle init on PASS or UNSEPARATED-only REVIEW (issue #173)."""
    if ingest.outcome == "PASS":
        return ingest.pass_
    if ingest.outcome != "REVIEW":
        return False
    gate_outcomes = ingest.coherence.get("gate_outcomes") or {}
    if any(row.get("outcome") == "FAIL" for row in gate_outcomes.values()):
        return False
    review_gates = [
        gate for gate, row in gate_outcomes.items() if row.get("outcome") == "REVIEW"
    ]
    if not review_gates:
        return False
    return all(
        gate_outcomes[gate].get("acceptance_status") == "UNSEPARATED"
        for gate in review_gates
    )


def _unseparated_only_review_coherence_outcome(coherence: Mapping[str, Any]) -> Outcome:
    """Treat UNSEPARATED-only REVIEW coherence as PASS for finalized bundles (issue #173)."""
    outcome = coherence.get("outcome", "FAIL")
    if outcome == "PASS":
        return "PASS"
    gate_outcomes = coherence.get("gate_outcomes") or {}
    if any(row.get("outcome") == "FAIL" for row in gate_outcomes.values()):
        return "FAIL"
    review_gates = [
        gate for gate, row in gate_outcomes.items() if row.get("outcome") == "REVIEW"
    ]
    if not review_gates:
        return outcome
    if all(
        gate_outcomes[gate].get("acceptance_status") == "UNSEPARATED"
        for gate in review_gates
    ):
        return "PASS"
    return outcome


def _effective_provider_outcome(ingest: IngestResult) -> Outcome:
    if _init_ingest_allowed(ingest):
        return "PASS"
    return ingest.outcome


def _aggregate_outcome(
    *,
    provider_outcome: Outcome,
    identity_lock: IdentityLockResult | None,
    structural: StructuralCheckResult,
    coherence: dict[str, Any],
    provider_post_edit: dict[str, Any] | None = None,
) -> Outcome:
    if (
        provider_post_edit is not None
        and provider_post_edit.get("outcome") == "FAIL"
    ):
        return "FAIL"
    if identity_lock is not None and identity_lock.outcome != "PASS":
        return "FAIL"
    if not structural.pass_:
        return structural.outcome
    if provider_outcome != "PASS":
        return provider_outcome
    if (
        provider_post_edit is not None
        and provider_post_edit.get("outcome") != "PASS"
    ):
        return "FAIL"
    return _unseparated_only_review_coherence_outcome(coherence)


def _verify_provider_post_edit(
    bundle_root: Path,
    manifest: Mapping[str, Any],
    *,
    profile_id: str | None,
) -> dict[str, Any] | None:
    """Hard-reject magenta-wiped providers; report edit-source continuity."""
    if _is_cell_authored_manifest(manifest):
        return None
    if not _requires_image_edit_evidence(profile_id, str(manifest["motion_class"])):
        return None
    edit_binding = manifest.get("edit_source")
    if not isinstance(edit_binding, dict):
        return None
    provider_path = bundle_root / str(manifest["provider"]["relative_path"])
    edit_source_path = bundle_root / str(edit_binding["relative_path"])
    if not edit_source_path.is_file():
        return None
    result = evaluate_provider_post_edit(
        provider_path,
        edit_source_path,
        motion_class=str(manifest["motion_class"]),
        layout=_corpus_layout(),
    )
    payload = provider_post_edit_report_payload(result)
    if result.reason_code == "provider_magenta_wipe":
        raise InvalidBundleError(
            "provider transport looks magenta-wiped relative to edit-source "
            "(post-edit stamp pipeline); regenerate instead of painting Gates",
            reason_code="provider_magenta_wipe",
        )
    return payload


def _probe_layout_for_manifest(manifest: Mapping[str, Any]) -> StripLayout:
    if manifest.get("schema") == BUNDLE_SCHEMA:
        return layout_for_motion_class(str(manifest["motion_class"]), margin_cells=0)
    return _corpus_layout()


def _verify_provider_and_drafts(
    bundle_root: Path,
    manifest: dict[str, Any],
) -> tuple[Outcome, AttestationState | None]:
    if _is_cell_authored_manifest(manifest):
        attestation = _verify_cell_author_bindings(bundle_root, manifest)
        ledger_binding = manifest["cell_authoring"]["cell_delta_ledger"]
        ledger = _load_json_object(
            bundle_root / str(ledger_binding["relative_path"]),
            reason_code="invalid_cell_delta_ledger",
            error_class=InvalidBundleError,
        )
        _replay_cell_author_drafts(bundle_root, manifest, ledger)
        for entry in manifest["draft_frames"]:
            rel = entry["relative_path"]
            expected = entry["sha256"]
            actual = sha256_file(bundle_root / rel)
            if actual != expected:
                raise InvalidBundleError(
                    f"draft frame hash mismatch: {rel}",
                    reason_code="draft_hash_mismatch",
                )
        return "PASS", attestation

    attestation: AttestationState | None = None
    if manifest.get("schema") == BUNDLE_SCHEMA:
        _, attestation = _verify_evidence_bindings(bundle_root, manifest)

    provider_rel = manifest["provider"]["relative_path"]
    expected_provider_hash = manifest["provider"]["sha256"]
    provider_path = bundle_root / provider_rel
    actual_provider_hash = sha256_file(provider_path)
    if actual_provider_hash != expected_provider_hash:
        raise InvalidBundleError(
            "bundled provider hash does not match manifest",
            reason_code="provider_hash_mismatch",
        )

    layout = _layout_from_manifest(manifest)
    probe_layout = _probe_layout_for_manifest(manifest)
    for entry in manifest["draft_frames"]:
        rel = entry["relative_path"]
        expected = entry["sha256"]
        actual = sha256_file(bundle_root / rel)
        if actual != expected:
            raise InvalidBundleError(
                f"draft frame hash mismatch: {rel}",
                reason_code="draft_hash_mismatch",
            )

    reproduced = _embed_frames_for_manifest_layout(
        _canonical_draft_frames(provider_path, probe_layout),
        motion_class=str(manifest["motion_class"]),
        layout=layout,
    )
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

    ingest = ingest_strip_provider(
        provider_path,
        probe_layout,
        motion_class=manifest["motion_class"],
    )
    return _effective_provider_outcome(ingest), attestation


def initialize_bundle(
    provider_path: Path,
    motion_class: str,
    bundle_root: Path,
    *,
    provenance_sidecar: Path,
    polish_profile: str | None = None,
    identity_reference: Path | None = None,
    edit_source: Path | None = None,
) -> None:
    """Create a hash-bound bundle when provider ingest PASSes; fail closed otherwise."""
    if bundle_root.exists():
        raise BundleExistsError(
            f"bundle destination already exists: {bundle_root}",
            reason_code="bundle_exists",
        )
    if not provider_path.is_file():
        raise InitializationRejectedError(
            f"missing provider: {provider_path}",
            reason_code="missing_provider",
        )
    profile_source = _profile_source(polish_profile) if polish_profile is not None else None

    try:
        probe_layout = layout_for_motion_class(motion_class, margin_cells=0)
    except ValueError as exc:
        raise InitializationRejectedError(
            f"unknown motion_class: {motion_class!r}",
            reason_code="invalid_motion_class",
        ) from exc
    provenance_record = _validate_provenance_sidecar(
        provider_path,
        provenance_sidecar,
        motion_class,
        probe_layout,
        polish_profile=polish_profile,
        identity_reference_path=identity_reference,
        edit_source_path=edit_source,
    )
    specification_id = str(provenance_record["specification_id"])
    provider_sha256 = sha256_file(provider_path)
    if _legacy_bundle_allowed(specification_id, provider_sha256):
        attempt_ledger = _build_legacy_single_row_attempt_ledger(provenance_record)
    else:
        from pipeline.asset_acquire import acquisition_controls_root, load_asset_attempts

        store_root = acquisition_controls_root(_REPO_ROOT)
        store_rows = load_asset_attempts(store_root, specification_id)
        if not store_rows:
            raise InitializationRejectedError(
                f"no attested Attempt rows for specification {specification_id!r}",
                reason_code="attempt_not_registered",
            )
        _assert_attempt_registered_for_init(
            provenance_record,
            provider_sha256,
            store_rows,
            store_root=store_root,
        )
        attempt_ledger = _build_initial_attempt_ledger(provenance_record, store_rows)

    try:
        _validate_attempt_ledger_document(
            attempt_ledger,
            provenance_record,
            provider_sha256=provider_sha256,
            original_filename=provider_path.name,
            where="initialize_bundle",
        )
    except InvalidBundleError as exc:
        raise InitializationRejectedError(
            str(exc),
            reason_code=(
                "attempt_not_registered"
                if exc.reason_code
                in {"invalid_attempt_ledger", "attempt_ledger_mismatch"}
                else exc.reason_code or "attempt_not_registered"
            ),
        ) from exc

    ingest = ingest_strip_provider(provider_path, probe_layout, motion_class=motion_class)
    if not _init_ingest_allowed(ingest):
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
    anchor_layout = _corpus_layout()
    if probe_layout.frame_w != anchor_layout.frame_w:
        for frame in canonical_frames:
            if not frame or len(frame[0]) != probe_layout.frame_w:
                raise InitializationRejectedError(
                    "frame width does not match class acquisition layout",
                    reason_code="wrong_size",
                )
    class_geometry = resolve_class_frame_geometry(motion_class)
    bundle_layout = StripLayout(
        frame_w=class_geometry.frame_w,
        frame_h=class_geometry.frame_h,
        frame_count=probe_layout.frame_count,
        gutter=probe_layout.gutter,
    )
    canonical_frames = _embed_frames_for_manifest_layout(
        canonical_frames,
        motion_class=motion_class,
        layout=bundle_layout,
    )

    temp_root = bundle_root.parent / f".{bundle_root.name}.tmp"
    _cleanup_partial(temp_root)
    try:
        temp_root.mkdir(parents=True, exist_ok=False)
        provider_dest = temp_root / "provider" / "source.png"
        provider_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(provider_path, provider_dest)

        provenance_dest = temp_root / "provider" / "source.source.json"
        shutil.copy2(provenance_sidecar, provenance_dest)

        identity_manifest: dict[str, Any] | None = None
        if identity_reference is not None:
            identity_dest = temp_root / "reference" / "identity.png"
            identity_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(identity_reference, identity_dest)
            identity_manifest = {
                "relative_path": "reference/identity.png",
                "sha256": sha256_file(identity_dest),
            }

        edit_source_manifest: dict[str, Any] | None = None
        if edit_source is not None:
            edit_dest = temp_root / "provider" / "edit-source.png"
            shutil.copy2(edit_source, edit_dest)
            edit_source_manifest = {
                "relative_path": "provider/edit-source.png",
                "sha256": sha256_file(edit_dest),
            }

        ledger_dest = temp_root / "provider" / "attempts.json"
        ledger_dest.write_text(
            json.dumps(attempt_ledger, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        profile_manifest: dict[str, Any] | None = None
        if profile_source is not None:
            profile_dest = temp_root / "profile.json"
            shutil.copy2(profile_source, profile_dest)
            profile_doc = json.loads(profile_dest.read_text(encoding="utf-8"))
            profile_manifest = {
                "schema": profile_doc["schema"],
                "id": profile_doc["id"],
                "relative_path": "profile.json",
                "sha256": sha256_file(profile_dest),
            }

        draft_hashes: list[dict[str, Any]] = []
        for index, cells in enumerate(canonical_frames):
            rel = f"draft/frame-{index}.png"
            draft_path = temp_root / rel
            write_cells(draft_path, cells)
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

        manifest: dict[str, Any] = {
            "schema": BUNDLE_SCHEMA,
            "motion_class": motion_class,
            "layout": {
                "frame_w": bundle_layout.frame_w,
                "frame_h": bundle_layout.frame_h,
                "frame_count": bundle_layout.frame_count,
                "frame_order": list(range(bundle_layout.frame_count)),
                "gutter": bundle_layout.gutter,
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
            "attempt_ledger": {
                "relative_path": "provider/attempts.json",
                "sha256": sha256_file(ledger_dest),
            },
            "draft_frames": draft_hashes,
            "polish_profile": profile_manifest,
        }
        if identity_manifest is not None:
            manifest["identity_reference"] = identity_manifest
        if edit_source_manifest is not None:
            manifest["edit_source"] = edit_source_manifest

        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp_root / "reports").mkdir()
        temp_root.rename(bundle_root)
    except Exception:
        _cleanup_partial(temp_root)
        raise


def initialize_cell_authored_bundle(
    authored_frames_dir: Path,
    motion_class: str,
    bundle_root: Path,
    *,
    specification_id: str,
    base_bundle_root: Path,
    cell_delta_ledger: Path,
    pose_plan: Path,
    polish_profile: str,
    identity_reference: Path | None,
    authoring_agent: str,
    authoring_session_id: str,
) -> None:
    """Create a providerless /2 bundle from authored Frames and a cell-delta ledger."""
    if bundle_root.exists():
        raise BundleExistsError(
            f"bundle destination already exists: {bundle_root}",
            reason_code="bundle_exists",
        )
    if not cell_delta_ledger.is_file():
        raise InitializationRejectedError(
            f"missing cell delta ledger: {cell_delta_ledger}",
            reason_code="missing_cell_delta_ledger",
        )
    if not pose_plan.is_file():
        raise InitializationRejectedError(
            f"missing pose plan: {pose_plan}",
            reason_code="missing_pose_plan",
        )

    try:
        probe_layout = layout_for_motion_class(motion_class, margin_cells=0)
    except ValueError as exc:
        raise InitializationRejectedError(
            f"unknown motion_class: {motion_class!r}",
            reason_code="invalid_motion_class",
        ) from exc

    _resolve_base_bundle_attestation(base_bundle_root)
    base_manifest = _load_manifest(base_bundle_root)
    base_provenance = _bundle_provenance_record(base_bundle_root, base_manifest)
    if base_provenance is None:
        raise InitializationRejectedError(
            "base bundle missing provenance record",
            reason_code="unattested_base_bundle",
        )
    base_specification_id = str(base_provenance["specification_id"])

    ledger = _load_json_object(
        cell_delta_ledger,
        reason_code="invalid_cell_delta_ledger",
    )
    if str(ledger.get("base_specification_id")) != base_specification_id:
        raise InitializationRejectedError(
            "ledger base_specification_id does not match base bundle",
            reason_code="base_specification_mismatch",
        )

    pose_doc = _load_json_object(
        pose_plan,
        reason_code="invalid_pose_plan",
    )
    base_frame_mapping = [int(value) for value in ledger["base_frame_mapping"]]
    _validate_pose_plan_document(
        pose_doc,
        motion_class=motion_class,
        base_specification_id=base_specification_id,
        base_frame_mapping=base_frame_mapping,
    )

    base_frames = _load_base_release_frames(base_bundle_root, motion_class)
    try:
        validate_cell_delta_ledger(base_frames, ledger)
    except CellDeltaError as exc:
        raise InitializationRejectedError(
            str(exc),
            reason_code=exc.reason_code,
        ) from exc

    class_geometry = resolve_class_frame_geometry(motion_class)
    bundle_layout = StripLayout(
        frame_w=class_geometry.frame_w,
        frame_h=class_geometry.frame_h,
        frame_count=probe_layout.frame_count,
        gutter=probe_layout.gutter,
    )
    authored_frames = _load_authored_frames(
        authored_frames_dir,
        frame_count=bundle_layout.frame_count,
        frame_w=bundle_layout.frame_w,
        frame_h=bundle_layout.frame_h,
    )
    try:
        assert_cell_delta_replay(base_frames, authored_frames, ledger)
    except CellDeltaError as exc:
        raise InitializationRejectedError(
            str(exc),
            reason_code=exc.reason_code,
        ) from exc

    profile_source = _profile_source(polish_profile)
    repository_commit = gc.git_commit(_REPO_ROOT)

    temp_root = bundle_root.parent / f".{bundle_root.name}.tmp"
    _cleanup_partial(temp_root)
    try:
        temp_root.mkdir(parents=True, exist_ok=False)

        authoring_dir = temp_root / "authoring"
        authoring_dir.mkdir()
        ledger_dest = authoring_dir / "cell-delta-ledger.json"
        shutil.copy2(cell_delta_ledger, ledger_dest)
        pose_dest = authoring_dir / "pose-plan.json"
        shutil.copy2(pose_plan, pose_dest)

        base_release_bindings: list[dict[str, Any]] = []
        for index, frame in enumerate(base_frames):
            rel = f"authoring/base/frame-{index}.png"
            base_path = temp_root / rel
            base_path.parent.mkdir(parents=True, exist_ok=True)
            write_cells(base_path, frame)
            base_release_bindings.append(
                {
                    "index": index,
                    "relative_path": rel,
                    "sha256": sha256_file(base_path),
                }
            )

        pose_binding = {
            "relative_path": "authoring/pose-plan.json",
            "sha256": sha256_file(pose_dest),
        }
        ledger_binding = {
            "relative_path": "authoring/cell-delta-ledger.json",
            "sha256": sha256_file(ledger_dest),
        }

        provenance_record: dict[str, Any] = {
            "schema": CELL_AUTHOR_PROVENANCE_SCHEMA,
            "generation_mode": CELL_AUTHOR_GENERATION_MODE,
            "specification_id": specification_id,
            "motion_class": motion_class,
            "base_specification_id": base_specification_id,
            "base_frames_sha256": list(ledger["base_frames_sha256"]),
            "base_frame_mapping": base_frame_mapping,
            "pose_plan": dict(pose_binding),
            "cell_delta_ledger": dict(ledger_binding),
            "authoring_agent": authoring_agent,
            "authoring_session_id": authoring_session_id,
            "repository_commit": repository_commit,
        }
        _validate_cell_author_provenance_record(
            provenance_record,
            motion_class=motion_class,
            specification_id=specification_id,
            base_specification_id=base_specification_id,
            base_frames_sha256=ledger["base_frames_sha256"],
            base_frame_mapping=base_frame_mapping,
            pose_plan_sha256=pose_binding["sha256"],
            ledger_sha256=ledger_binding["sha256"],
        )
        provenance_dest = authoring_dir / "provenance.json"
        provenance_dest.write_text(
            json.dumps(provenance_record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        provenance_binding = {
            "relative_path": "authoring/provenance.json",
            "sha256": sha256_file(provenance_dest),
        }

        identity_manifest: dict[str, Any] | None = None
        if identity_reference is not None:
            identity_dest = temp_root / "reference" / "identity.png"
            identity_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(identity_reference, identity_dest)
            identity_manifest = {
                "relative_path": "reference/identity.png",
                "sha256": sha256_file(identity_dest),
            }

        profile_dest = temp_root / "profile.json"
        shutil.copy2(profile_source, profile_dest)
        profile_doc = json.loads(profile_dest.read_text(encoding="utf-8"))
        profile_manifest = {
            "schema": profile_doc["schema"],
            "id": profile_doc["id"],
            "relative_path": "profile.json",
            "sha256": sha256_file(profile_dest),
        }

        draft_hashes: list[dict[str, Any]] = []
        for index, cells in enumerate(authored_frames):
            rel = f"draft/frame-{index}.png"
            draft_path = temp_root / rel
            write_cells(draft_path, cells)
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

        manifest: dict[str, Any] = {
            "schema": BUNDLE_SCHEMA,
            "generation_mode": CELL_AUTHOR_GENERATION_MODE,
            "motion_class": motion_class,
            "layout": {
                "frame_w": bundle_layout.frame_w,
                "frame_h": bundle_layout.frame_h,
                "frame_count": bundle_layout.frame_count,
                "frame_order": list(range(bundle_layout.frame_count)),
                "gutter": bundle_layout.gutter,
            },
            "cell_authoring": {
                "provenance": provenance_binding,
                "base_specification_id": base_specification_id,
                "base_frames_sha256": list(ledger["base_frames_sha256"]),
                "base_frame_mapping": base_frame_mapping,
                "base_release_frames": base_release_bindings,
                "pose_plan": pose_binding,
                "cell_delta_ledger": ledger_binding,
            },
            "draft_frames": draft_hashes,
            "polish_profile": profile_manifest,
        }
        if identity_manifest is not None:
            manifest["identity_reference"] = identity_manifest

        (temp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp_root / "reports").mkdir()
        temp_root.rename(bundle_root)
    except InitializationRejectedError:
        _cleanup_partial(temp_root)
        raise
    except Exception:
        _cleanup_partial(temp_root)
        raise


def _layout_from_manifest(manifest: dict[str, Any]) -> StripLayout:
    layout = manifest["layout"]
    return StripLayout(
        frame_w=int(layout["frame_w"]),
        frame_h=int(layout["frame_h"]),
        frame_count=int(layout["frame_count"]),
        gutter=int(layout["gutter"]),
    )


def _animation_policy_for_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    motion_class = str(manifest["motion_class"])
    asset_id = _MOTION_CLASS_ASSET_ID.get(motion_class)
    if asset_id is None:
        raise InvalidBundleError(
            f"no first-room animation policy for motion class {motion_class!r}",
            reason_code="missing_animation_policy",
        )
    policy = FIRST_ROOM_ANIMATION_POLICY.get(asset_id)
    if policy is None:
        raise InvalidBundleError(
            f"missing animation policy for asset {asset_id!r}",
            reason_code="missing_animation_policy",
        )
    return policy


def _emit_silhouette_artifacts(
    bundle_root: Path,
    frames: Sequence[list[list[Cell]]],
    manifest: dict[str, Any],
) -> SilhouetteArtifacts:
    layout = _layout_from_manifest(manifest)
    policy = _animation_policy_for_manifest(manifest)
    durations_ms = policy["durations_ms"]
    if len(durations_ms) != layout.frame_count:
        raise InvalidBundleError(
            "animation policy durations_ms length mismatch",
            reason_code="animation_policy_mismatch",
        )
    strip_path = bundle_root / SILHOUETTE_STRIP_RELATIVE_PATH
    gif_path = bundle_root / SILHOUETTE_GIF_RELATIVE_PATH
    write_silhouette_strip(strip_path, frames, layout)
    write_silhouette_gif(
        gif_path,
        frames,
        durations_ms=durations_ms,
        loop=bool(policy["loop"]),
    )
    return SilhouetteArtifacts(
        strip_relative_path=SILHOUETTE_STRIP_RELATIVE_PATH,
        strip_sha256=sha256_file(strip_path),
        gif_relative_path=SILHOUETTE_GIF_RELATIVE_PATH,
        gif_sha256=sha256_file(gif_path),
    )


def _silhouette_artifacts_report_payload(artifacts: SilhouetteArtifacts) -> dict[str, Any]:
    return {
        "strip": {
            "relative_path": artifacts.strip_relative_path,
            "sha256": artifacts.strip_sha256,
        },
        "gif": {
            "relative_path": artifacts.gif_relative_path,
            "sha256": artifacts.gif_sha256,
        },
    }


def check_bundle(bundle_root: Path) -> FinalPolishCheckResult:
    """Validate provenance, logical Frames, structure, delta, and coherence."""
    manifest = _load_manifest(bundle_root)
    profile = _load_bound_profile(bundle_root, manifest)
    manifest_hash = manifest_sha256(bundle_root)
    provider_outcome, attestation = _verify_provider_and_drafts(bundle_root, manifest)
    profile_id = None if profile is None else str(profile["id"])
    provider_post_edit = _verify_provider_post_edit(
        bundle_root,
        manifest,
        profile_id=profile_id,
    )

    draft_frames = _load_frame_sequence(bundle_root, "draft")
    polished_frames = _load_frame_sequence(bundle_root, "polished")
    draft_hashes = _ordered_frame_hashes(bundle_root, "draft")
    polished_hashes = _ordered_frame_hashes(bundle_root, "polished")
    if _is_cell_authored_manifest(manifest):
        provider_sha256 = ""
    else:
        provider_sha256 = sha256_file(_provider_path(bundle_root))

    structural = _structural_check(
        draft_frames,
        polished_frames,
        extra_allowed_palette=_bundle_master_palette_rgb_set(bundle_root),
    )
    delta = _visible_cell_delta(draft_frames, polished_frames)
    coherence = coherence_split(polished_frames, motion_class=manifest["motion_class"])
    polished_roles_path = bundle_root / "polished-roles.json"
    palette_exact_lock = polished_roles_path.is_file()
    identity_lock: IdentityLockResult | None = None
    if identity_lock_applies(profile_id, str(manifest["motion_class"])) and (
        manifest.get("schema") == BUNDLE_SCHEMA or palette_exact_lock
    ):
        identity_lock = evaluate_identity_lock(
            polished_frames,
            str(manifest["motion_class"]),
            palette_exact=palette_exact_lock,
            polished_roles_path=polished_roles_path if palette_exact_lock else None,
        )
    outcome = _aggregate_outcome(
        provider_outcome=provider_outcome,
        identity_lock=identity_lock,
        structural=structural,
        coherence=coherence,
        provider_post_edit=provider_post_edit,
    )
    fingerprint = _fingerprint_polished_hashes(polished_hashes, identity_lock)
    silhouette_artifacts = _emit_silhouette_artifacts(bundle_root, polished_frames, manifest)
    if attestation is None:
        attestation = _resolve_bundle_attestation(bundle_root, manifest)

    return FinalPolishCheckResult(
        outcome=outcome,
        provider_outcome=provider_outcome,
        identity_lock=identity_lock,
        structural=structural,
        delta=delta,
        coherence=coherence,
        manifest_sha256=manifest_hash,
        provider_sha256=provider_sha256,
        draft_hashes=draft_hashes,
        polished_hashes=polished_hashes,
        fingerprint=fingerprint,
        profile_id=profile_id,
        profile_sha256=(
            None
            if profile is None
            else str(manifest["polish_profile"]["sha256"])
        ),
        provider_post_edit=provider_post_edit,
        silhouette_artifacts=silhouette_artifacts,
        attestation=attestation,
    )


def _report_payload(bundle_root: Path, result: FinalPolishCheckResult) -> dict[str, Any]:
    manifest = _load_manifest(bundle_root)
    payload: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "fingerprint": result.fingerprint,
        "manifest_sha256": result.manifest_sha256,
        "motion_class": manifest["motion_class"],
        "layout": manifest["layout"],
        "draft_frames": [
            {"index": index, "sha256": digest}
            for index, digest in enumerate(result.draft_hashes)
        ],
        "polished_frames": [
            {"index": index, "sha256": digest}
            for index, digest in enumerate(result.polished_hashes)
        ],
        "provider_acceptance": {"outcome": result.provider_outcome},
        "provider_post_edit": result.provider_post_edit,
        "identity_lock": (
            None
            if result.identity_lock is None
            else identity_lock_report_payload(result.identity_lock)
        ),
        "polish_profile": (
            None
            if result.profile_id is None
            else {
                "id": result.profile_id,
                "sha256": result.profile_sha256,
            }
        ),
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
    if _is_cell_authored_manifest(manifest):
        payload["generation_mode"] = CELL_AUTHOR_GENERATION_MODE
        if result.attestation is not None:
            payload["base_specification_id"] = result.attestation.base_specification_id
    else:
        payload["provider"] = {
            "relative_path": manifest["provider"]["relative_path"],
            "sha256": result.provider_sha256,
        }
    if result.attestation is not None:
        payload["attestation"] = _attestation_report_payload(result.attestation)
    if result.silhouette_artifacts is not None:
        payload["silhouette_artifacts"] = _silhouette_artifacts_report_payload(
            result.silhouette_artifacts
        )
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
        if sha256_file(source) != result.polished_hashes[index]:
            raise InvalidBundleError(
                f"polished frame hash mismatch: {name}",
                reason_code="release_conflict",
            )
        dest = release_dir / name
        if dest.exists():
            if sha256_file(dest) != result.polished_hashes[index]:
                raise InvalidBundleError(
                    f"release frame conflict: {name}",
                    reason_code="release_conflict",
                )
            continue
        shutil.copy2(source, dest)


def finalize_bundle(bundle_root: Path) -> Path:
    """Write an immutable report; on PASS, copy polished Frames to release/."""
    check = check_bundle(bundle_root)
    from pipeline.polish_review import attestation_state_name, ensure_visual_reviews_for_finalize

    ensure_visual_reviews_for_finalize(
        bundle_root,
        attestation_state_name(check.attestation),
    )
    report_path = _reports_dir(bundle_root) / f"{check.fingerprint}.json"
    payload = _report_payload(bundle_root, check)

    if report_path.exists():
        existing = json.loads(report_path.read_text())
        if canonical.canonical_value(existing) != canonical.canonical_value(payload):
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
