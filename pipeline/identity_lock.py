"""Identity Lock evaluation and deterministic image-edit seed generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from PIL import Image, UnidentifiedImageError

from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.recovery import MAGENTA
from pipeline.strip import Cell

IDENTITY_LOCK_SCHEMA = "identity-lock/0"
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDENTITY_LOCKS_PATH = (
    _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
)
DEFAULT_IDENTITY_PATH = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity.png"

SEED_SCALE = 16
SEED_FRAME_COUNT = 4
SEED_GUTTER_LOGICAL_CELLS = 2
SEED_WIDTH = 1120
SEED_HEIGHT = 384


class IdentityLockError(ValueError):
    """Fail-closed Identity Lock specification or evaluation error."""


Outcome = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class IdentityLockMismatch:
    anchor: str
    x: int
    y: int
    expected_rgba: tuple[int, int, int, int]
    actual_rgba: tuple[int, int, int, int]


@dataclass(frozen=True)
class FrameIdentityLockResult:
    selected_offsets: dict[str, tuple[int, int]]
    anchor_results: dict[str, Outcome]
    first_mismatch: IdentityLockMismatch | None


@dataclass(frozen=True)
class IdentityLockResult:
    outcome: Outcome
    identity_sha256: str
    lock_spec_sha256: str
    motion_class: str
    per_frame: tuple[FrameIdentityLockResult, ...]
    first_mismatch: IdentityLockMismatch | None


def identity_lock_applies(polish_profile_id: str | None, motion_class: str) -> bool:
    return polish_profile_id == "dwarf-miner" and motion_class in {"walk", "swing"}


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


def load_canonical_cells(
    identity_path: Path,
    frame_size: tuple[int, int],
) -> list[list[Cell]]:
    if not identity_path.is_file():
        raise IdentityLockError(f"missing canonical identity: {identity_path}")
    try:
        with Image.open(identity_path) as image:
            if image.size != frame_size:
                raise IdentityLockError(
                    f"identity frame size must be {frame_size[0]}x{frame_size[1]}"
                )
            return _cells_from_rgba_image(image.convert("RGBA"))
    except UnidentifiedImageError as exc:
        raise IdentityLockError(f"unreadable identity image: {identity_path}") from exc


def _expand_offsets(spec: object) -> list[tuple[int, int]]:
    if isinstance(spec, list):
        offsets: list[tuple[int, int]] = []
        for entry in spec:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or not all(isinstance(axis, int) for axis in entry)
            ):
                raise IdentityLockError("permitted_offsets list entries must be [dx, dy]")
            offsets.append((int(entry[0]), int(entry[1])))
        return offsets
    if isinstance(spec, dict):
        dx_values = spec.get("dx")
        dy_values = spec.get("dy")
        if not isinstance(dx_values, list) or not isinstance(dy_values, list):
            raise IdentityLockError("permitted_offsets object requires dx and dy arrays")
        return [
            (int(dx), int(dy))
            for dx, dy in product(dx_values, dy_values)
        ]
    raise IdentityLockError("permitted_offsets must be a list or dx/dy object")


def _validate_rectangle(rect: Mapping[str, Any], *, where: str) -> dict[str, int]:
    for key in ("x0", "x1", "y0", "y1"):
        value = rect.get(key)
        if not isinstance(value, int):
            raise IdentityLockError(f"{where} rectangle missing integer {key}")
    if rect["x0"] > rect["x1"] or rect["y0"] > rect["y1"]:
        raise IdentityLockError(f"{where} rectangle bounds are inverted")
    return {
        "x0": int(rect["x0"]),
        "x1": int(rect["x1"]),
        "y0": int(rect["y0"]),
        "y1": int(rect["y1"]),
    }


def _validate_lock_row(row: Mapping[str, Any], *, where: str) -> dict[str, Any]:
    lock_id = row.get("id")
    if not isinstance(lock_id, str) or not lock_id:
        raise IdentityLockError(f"{where} lock missing id")
    rectangle = row.get("rectangle")
    if not isinstance(rectangle, dict):
        raise IdentityLockError(f"{where} lock missing rectangle")
    offsets = row.get("permitted_offsets")
    if offsets is None:
        raise IdentityLockError(f"{where} lock missing permitted_offsets")
    return {
        "id": lock_id,
        "rectangle": _validate_rectangle(rectangle, where=f"{where} lock {lock_id}"),
        "offsets": _expand_offsets(offsets),
    }


def validate_identity_lock_spec(doc: Mapping[str, Any], *, spec_path: Path | None = None) -> None:
    if doc.get("schema") != IDENTITY_LOCK_SCHEMA:
        raise IdentityLockError(f"schema must be {IDENTITY_LOCK_SCHEMA!r}")
    identity_sha = doc.get("identity_sha256")
    if not isinstance(identity_sha, str) or len(identity_sha) != 64:
        raise IdentityLockError("identity_sha256 must be a 64-char hex digest")
    frame_size = doc.get("frame_size")
    if (
        not isinstance(frame_size, list)
        or len(frame_size) != 2
        or not all(isinstance(axis, int) and axis > 0 for axis in frame_size)
    ):
        raise IdentityLockError("frame_size must be a two-element positive integer array")
    if doc.get("comparison") != "exact-rgba":
        raise IdentityLockError("comparison must be exact-rgba")
    motion_classes = doc.get("motion_classes")
    if not isinstance(motion_classes, dict) or not motion_classes:
        raise IdentityLockError("motion_classes must be a non-empty object")
    for motion_class, motion_doc in motion_classes.items():
        if not isinstance(motion_class, str) or not motion_class:
            raise IdentityLockError("motion_classes keys must be non-empty strings")
        if not isinstance(motion_doc, dict):
            raise IdentityLockError(f"motion_classes.{motion_class} must be an object")
        locks = motion_doc.get("locks")
        if not isinstance(locks, list) or not locks:
            raise IdentityLockError(f"motion_classes.{motion_class}.locks must be a non-empty array")
        parsed_locks = [
            _validate_lock_row(lock, where=f"motion_classes.{motion_class}")
            for lock in locks
        ]
        lock_ids = {lock["id"] for lock in parsed_locks}
        constraints = motion_doc.get("relational_constraints", [])
        if constraints is None:
            constraints = []
        if not isinstance(constraints, list):
            raise IdentityLockError(
                f"motion_classes.{motion_class}.relational_constraints must be an array"
            )
        for index, constraint in enumerate(constraints):
            if not isinstance(constraint, dict):
                raise IdentityLockError(
                    f"motion_classes.{motion_class}.relational_constraints[{index}] invalid"
                )
            anchors = constraint.get("anchors")
            if not isinstance(anchors, list) or len(anchors) != 2:
                raise IdentityLockError("relational_constraints anchors must be a two-element array")
            for anchor in anchors:
                if anchor not in lock_ids:
                    raise IdentityLockError(
                        f"relational_constraints references unknown anchor {anchor!r}"
                    )
            for key in ("max_dx_delta", "max_vertical_separation_delta"):
                value = constraint.get(key)
                if not isinstance(value, int) or value < 0:
                    raise IdentityLockError(
                        f"relational_constraints.{key} must be a non-negative integer"
                    )
    if spec_path is not None and spec_path.is_file():
        identity_path = DEFAULT_IDENTITY_PATH
        if sha256_file(identity_path) != identity_sha:
            raise IdentityLockError("identity_sha256 does not match canonical identity.png")


def load_identity_lock_spec(path: Path = DEFAULT_IDENTITY_LOCKS_PATH) -> dict[str, Any]:
    if not path.is_file():
        raise IdentityLockError(f"missing identity lock spec: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IdentityLockError(f"invalid identity lock JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise IdentityLockError("identity lock spec must be an object")
    validate_identity_lock_spec(doc, spec_path=path)
    return doc


def _cell_to_rgba(cell: Cell) -> tuple[int, int, int, int]:
    if cell is None:
        return (0, 0, 0, 0)
    return (cell[0], cell[1], cell[2], 255)


def _cells_match(canonical: Cell, attempt: Cell) -> bool:
    return _cell_to_rgba(canonical) == _cell_to_rgba(attempt)


def _compare_shifted_rectangle(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    rectangle: Mapping[str, int],
    dx: int,
    dy: int,
    *,
    anchor_id: str,
) -> IdentityLockMismatch | None:
    frame_h = len(canonical)
    frame_w = len(canonical[0])
    for y in range(rectangle["y0"], rectangle["y1"] + 1):
        for x in range(rectangle["x0"], rectangle["x1"] + 1):
            attempt_x = x + dx
            attempt_y = y + dy
            if not (0 <= attempt_x < frame_w and 0 <= attempt_y < frame_h):
                expected = _cell_to_rgba(canonical[y][x])
                return IdentityLockMismatch(
                    anchor=anchor_id,
                    x=x,
                    y=y,
                    expected_rgba=expected,
                    actual_rgba=(0, 0, 0, 0),
                )
            if not _cells_match(canonical[y][x], attempt[attempt_y][attempt_x]):
                return IdentityLockMismatch(
                    anchor=anchor_id,
                    x=x,
                    y=y,
                    expected_rgba=_cell_to_rgba(canonical[y][x]),
                    actual_rgba=_cell_to_rgba(attempt[attempt_y][attempt_x]),
                )
    return None


def _canonical_vertical_separation(
    locks: Sequence[Mapping[str, Any]],
    offsets: Mapping[str, tuple[int, int]],
    anchor_a: str,
    anchor_b: str,
) -> int:
    rect_a = next(lock["rectangle"] for lock in locks if lock["id"] == anchor_a)
    rect_b = next(lock["rectangle"] for lock in locks if lock["id"] == anchor_b)
    dx_a, dy_a = offsets[anchor_a]
    dx_b, dy_b = offsets[anchor_b]
    return (rect_b["y0"] + dy_b) - (rect_a["y0"] + dy_a)


def _relational_constraints_hold(
    locks: Sequence[Mapping[str, Any]],
    offsets: Mapping[str, tuple[int, int]],
    constraints: Sequence[Mapping[str, Any]],
    canonical_offsets: Mapping[str, tuple[int, int]],
) -> bool:
    for constraint in constraints:
        anchor_a, anchor_b = constraint["anchors"]
        dx_a, dy_a = offsets[anchor_a]
        dx_b, dy_b = offsets[anchor_b]
        if abs(dx_a - dx_b) > int(constraint["max_dx_delta"]):
            return False
        canonical_sep = _canonical_vertical_separation(
            locks,
            canonical_offsets,
            anchor_a,
            anchor_b,
        )
        attempted_sep = _canonical_vertical_separation(locks, offsets, anchor_a, anchor_b)
        if abs(attempted_sep - canonical_sep) > int(constraint["max_vertical_separation_delta"]):
            return False
    return True


def _find_frame_offsets(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    locks: Sequence[Mapping[str, Any]],
    constraints: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, tuple[int, int]], dict[str, Outcome], IdentityLockMismatch | None]:
    canonical_offsets = {lock["id"]: (0, 0) for lock in locks}
    offset_lists = [lock["offsets"] for lock in locks]
    lock_ids = [lock["id"] for lock in locks]

    best_failure: tuple[dict[str, tuple[int, int]], dict[str, Outcome], IdentityLockMismatch] | None = None
    best_pass_count = -1

    for offset_combo in product(*offset_lists):
        offsets = dict(zip(lock_ids, offset_combo, strict=True))
        if constraints and not _relational_constraints_hold(
            locks,
            offsets,
            constraints,
            canonical_offsets,
        ):
            continue
        anchor_results: dict[str, Outcome] = {}
        first_mismatch: IdentityLockMismatch | None = None
        for lock in locks:
            mismatch = _compare_shifted_rectangle(
                canonical,
                attempt,
                lock["rectangle"],
                offsets[lock["id"]][0],
                offsets[lock["id"]][1],
                anchor_id=lock["id"],
            )
            if mismatch is not None:
                anchor_results[lock["id"]] = "FAIL"
                if first_mismatch is None:
                    first_mismatch = mismatch
            else:
                anchor_results[lock["id"]] = "PASS"
        if first_mismatch is None:
            return offsets, anchor_results, None
        pass_count = sum(1 for outcome in anchor_results.values() if outcome == "PASS")
        if pass_count > best_pass_count:
            best_pass_count = pass_count
            best_failure = (offsets, anchor_results, first_mismatch)

    if best_failure is not None:
        offsets, anchor_results, first_mismatch = best_failure
        return offsets, anchor_results, first_mismatch

    offsets = {lock["id"]: lock["offsets"][0] for lock in locks}
    anchor_results = {lock["id"]: "FAIL" for lock in locks}
    first_mismatch = None
    for lock in locks:
        mismatch = _compare_shifted_rectangle(
            canonical,
            attempt,
            lock["rectangle"],
            offsets[lock["id"]][0],
            offsets[lock["id"]][1],
            anchor_id=lock["id"],
        )
        if mismatch is not None:
            first_mismatch = mismatch
            break
    return offsets, anchor_results, first_mismatch


def evaluate_identity_lock(
    frames: Sequence[Sequence[Sequence[Cell]]],
    motion_class: str,
    *,
    spec_path: Path = DEFAULT_IDENTITY_LOCKS_PATH,
    identity_path: Path = DEFAULT_IDENTITY_PATH,
) -> IdentityLockResult:
    spec = load_identity_lock_spec(spec_path)
    motion_doc = spec["motion_classes"].get(motion_class)
    if motion_doc is None:
        raise IdentityLockError(f"motion class {motion_class!r} has no Identity Lock rules")

    frame_size = (int(spec["frame_size"][0]), int(spec["frame_size"][1]))
    canonical = load_canonical_cells(identity_path, frame_size)
    locks = [_validate_lock_row(lock, where=f"motion_classes.{motion_class}") for lock in motion_doc["locks"]]
    constraints = motion_doc.get("relational_constraints", []) or []

    per_frame: list[FrameIdentityLockResult] = []
    overall_mismatch: IdentityLockMismatch | None = None

    for attempt in frames:
        if len(attempt) != frame_size[1] or any(len(row) != frame_size[0] for row in attempt):
            raise IdentityLockError("attempt frame size does not match Identity Lock frame_size")
        offsets, anchor_results, mismatch = _find_frame_offsets(
            canonical,
            list(attempt),
            locks,
            constraints,
        )
        per_frame.append(
            FrameIdentityLockResult(
                selected_offsets=offsets,
                anchor_results=anchor_results,
                first_mismatch=mismatch,
            )
        )
        if mismatch is not None and overall_mismatch is None:
            overall_mismatch = mismatch

    outcome: Outcome = "PASS" if overall_mismatch is None else "FAIL"
    return IdentityLockResult(
        outcome=outcome,
        identity_sha256=str(spec["identity_sha256"]),
        lock_spec_sha256=sha256_file(spec_path),
        motion_class=motion_class,
        per_frame=tuple(per_frame),
        first_mismatch=overall_mismatch,
    )


def _mismatch_payload(mismatch: IdentityLockMismatch | None) -> dict[str, Any] | None:
    if mismatch is None:
        return None
    return {
        "anchor": mismatch.anchor,
        "x": mismatch.x,
        "y": mismatch.y,
        "expected_rgba": list(mismatch.expected_rgba),
        "actual_rgba": list(mismatch.actual_rgba),
    }


def identity_lock_report_payload(result: IdentityLockResult) -> dict[str, Any]:
    return {
        "outcome": result.outcome,
        "identity_sha256": result.identity_sha256,
        "lock_spec_sha256": result.lock_spec_sha256,
        "motion_class": result.motion_class,
        "per_frame": [
            {
                "selected_offsets": {
                    anchor: [offsets[0], offsets[1]]
                    for anchor, offsets in frame.selected_offsets.items()
                },
                "anchor_results": dict(frame.anchor_results),
                "first_mismatch": _mismatch_payload(frame.first_mismatch),
            }
            for frame in result.per_frame
        ],
        "first_mismatch": _mismatch_payload(result.first_mismatch),
    }


def build_identity_seed(
    identity_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    if not identity_path.is_file():
        raise IdentityLockError(f"missing identity image: {identity_path}")

    with Image.open(identity_path) as source:
        if source.size != (16, 24):
            raise IdentityLockError("identity seed requires a 16×24 identity frame")
        frame_rgba = source.convert("RGBA")

    scaled_w = 16 * SEED_SCALE
    scaled_h = 24 * SEED_SCALE
    gutter_px = SEED_GUTTER_LOGICAL_CELLS * SEED_SCALE
    canvas = Image.new("RGBA", (SEED_WIDTH, SEED_HEIGHT), MAGENTA)

    scaled_frame = frame_rgba.resize((scaled_w, scaled_h), Image.Resampling.NEAREST)
    x = 0
    for index in range(SEED_FRAME_COUNT):
        canvas.paste(scaled_frame, (x, 0))
        x += scaled_w
        if index < SEED_FRAME_COUNT - 1:
            x += gutter_px

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path)

    return {
        "identity_path": str(identity_path.resolve()),
        "out_path": str(out_path.resolve()),
        "dimensions": [SEED_WIDTH, SEED_HEIGHT],
        "sha256": sha256_file(out_path),
        "frame_count": SEED_FRAME_COUNT,
        "scale": SEED_SCALE,
        "gutter_logical_cells": SEED_GUTTER_LOGICAL_CELLS,
    }
