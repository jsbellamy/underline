"""Identity Lock evaluation and deterministic image-edit seed generation."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from io import BytesIO
from itertools import product
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from PIL import Image, UnidentifiedImageError

from pipeline import canonical
from pipeline.cell_raster import cells_from_rgba
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.strip import Cell

IDENTITY_LOCK_SCHEMA = "identity-lock/1"
IDENTITY_LOCK_NEAR_MISS_SCHEMA = "identity-lock-near-miss/0"
_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IDENTITY_LOCKS_PATH = (
    _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
)
DEFAULT_IDENTITY_PATH = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
TRANSPORT_MAGENTA = (255, 0, 255)
# Idle-provider transport uses soft near-magenta; #159 wiped to exact #FF00FF (~0.6).
MAGENTA_WIPE_MIN_PROVIDER_FRACTION = 0.05
MAGENTA_WIPE_MAX_EDIT_SOURCE_FRACTION = 0.01


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
class EditSourceContinuityResult:
    outcome: Outcome
    reason_code: str | None
    motion_class: str
    first_failure: dict[str, Any] | None
    first_mismatch: IdentityLockMismatch | None


@dataclass(frozen=True)
class ProviderPostEditResult:
    outcome: Outcome
    reason_code: str | None
    magenta_wipe: dict[str, Any]
    continuity: EditSourceContinuityResult | None


@dataclass(frozen=True)
class FrameIdentityLockResult:
    selected_offsets: dict[str, tuple[int, int]]
    anchor_results: dict[str, Outcome]
    check_results: dict[str, dict[str, Any]]
    landmark_results: dict[str, dict[str, Any]]
    first_failure: dict[str, Any] | None
    first_mismatch: IdentityLockMismatch | None


@dataclass(frozen=True)
class IdentityLockResult:
    outcome: Outcome
    identity_sha256: str
    lock_spec_sha256: str
    motion_class: str
    per_frame: tuple[FrameIdentityLockResult, ...]
    first_failure: dict[str, Any] | None
    first_mismatch: IdentityLockMismatch | None


def identity_lock_applies(polish_profile_id: str | None, motion_class: str) -> bool:
    return polish_profile_id == "dwarf-miner" and motion_class in {"walk", "swing"}


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
            return cells_from_rgba(image.convert("RGBA"))
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
    comparison = row.get("comparison")
    if comparison not in {"registered-structure", "exact-occupancy"}:
        raise IdentityLockError(
            f"{where} lock {lock_id} comparison must be registered-structure "
            "or exact-occupancy"
        )
    parsed = {
        "id": lock_id,
        "rectangle": _validate_rectangle(rectangle, where=f"{where} lock {lock_id}"),
        "offsets": _expand_offsets(offsets),
        "comparison": comparison,
    }
    if comparison == "registered-structure":
        for key in ("max_occupancy_difference", "max_palette_role_distance"):
            value = row.get(key)
            if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise IdentityLockError(
                    f"{where} lock {lock_id} {key} must be between 0 and 1"
                )
            parsed[key] = float(value)
    return parsed


def _resolve_bound_repo_file(binding: object, *, label: str) -> Path:
    if not isinstance(binding, dict):
        raise IdentityLockError(f"{label} must be a path/hash binding")
    try:
        return canonical.verify_binding(binding, root=_REPO_ROOT, label=label)
    except canonical.BindingError as exc:
        raise IdentityLockError(str(exc)) from exc


def _load_palette_roles(path: Path) -> tuple[list[str], list[tuple[str, tuple[int, int, int]]]]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityLockError(f"invalid master palette JSON: {path}") from exc
    groups = doc.get("role_groups") if isinstance(doc, dict) else None
    if not isinstance(groups, list) or not groups:
        raise IdentityLockError("master palette requires non-empty role_groups")
    role_ids: list[str] = []
    entries: list[tuple[str, tuple[int, int, int]]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise IdentityLockError("master palette role group must be an object")
        role_id = group.get("id")
        colors = group.get("colors")
        if not isinstance(role_id, str) or not role_id:
            raise IdentityLockError("master palette role group requires id")
        if role_id in role_ids:
            raise IdentityLockError(f"duplicate master palette role {role_id!r}")
        if not isinstance(colors, list) or not colors:
            raise IdentityLockError(f"master palette role {role_id!r} requires colors")
        role_ids.append(role_id)
        for color in colors:
            if (
                not isinstance(color, str)
                or len(color) != 7
                or not color.startswith("#")
            ):
                raise IdentityLockError(f"invalid color in master palette role {role_id!r}")
            try:
                rgb = tuple(int(color[index : index + 2], 16) for index in (1, 3, 5))
            except ValueError as exc:
                raise IdentityLockError(
                    f"invalid color in master palette role {role_id!r}"
                ) from exc
            entries.append((role_id, rgb))
    return role_ids, entries


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
    frame_w, frame_h = int(frame_size[0]), int(frame_size[1])
    palette_path = _resolve_bound_repo_file(
        doc.get("master_palette"),
        label="master_palette",
    )
    palette_roles, _ = _load_palette_roles(palette_path)
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
            raise IdentityLockError(
                f"motion_classes.{motion_class}.locks must be a non-empty array"
            )
        parsed_locks = [
            _validate_lock_row(lock, where=f"motion_classes.{motion_class}")
            for lock in locks
        ]
        for lock in parsed_locks:
            rectangle = lock["rectangle"]
            if (
                rectangle["x0"] < 0
                or rectangle["y0"] < 0
                or rectangle["x1"] >= frame_w
                or rectangle["y1"] >= frame_h
            ):
                raise IdentityLockError(
                    f"motion_classes.{motion_class} lock {lock['id']} "
                    "rectangle exceeds frame_size"
                )
        lock_ids = {lock["id"] for lock in parsed_locks}
        landmarks = motion_doc.get("landmarks", [])
        if not isinstance(landmarks, list):
            raise IdentityLockError(
                f"motion_classes.{motion_class}.landmarks must be an array"
            )
        landmark_ids: set[str] = set()
        for index, landmark in enumerate(landmarks):
            where = f"motion_classes.{motion_class}.landmarks[{index}]"
            if not isinstance(landmark, dict):
                raise IdentityLockError(f"{where} must be an object")
            landmark_id = landmark.get("id")
            canonical = landmark.get("canonical")
            palette_role = landmark.get("palette_role")
            max_distance = landmark.get("max_distance")
            if not isinstance(landmark_id, str) or not landmark_id:
                raise IdentityLockError(f"{where}.id must be a non-empty string")
            if landmark_id in landmark_ids:
                raise IdentityLockError(f"duplicate landmark {landmark_id!r}")
            landmark_ids.add(landmark_id)
            if (
                not isinstance(canonical, list)
                or len(canonical) != 2
                or not all(isinstance(axis, int) for axis in canonical)
                or not 0 <= canonical[0] < frame_w
                or not 0 <= canonical[1] < frame_h
            ):
                raise IdentityLockError(f"{where}.canonical must be within frame_size")
            if palette_role not in palette_roles:
                raise IdentityLockError(f"{where} references unknown palette role")
            if not isinstance(max_distance, int) or max_distance < 0:
                raise IdentityLockError(f"{where}.max_distance must be non-negative")
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
                raise IdentityLockError(
                    "relational_constraints anchors must be a two-element array"
                )
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


def nearest_palette_role(
    cell: Cell,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> str | None:
    if cell is None:
        return None
    return min(
        palette_entries,
        key=lambda entry: sum(
            (cell[channel] - entry[1][channel]) ** 2 for channel in range(3)
        ),
    )[0]


def _registered_cells(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    rectangle: Mapping[str, int],
    dx: int,
    dy: int,
) -> Sequence[tuple[int, int, Cell, Cell]]:
    frame_h = len(canonical)
    frame_w = len(canonical[0])
    pairs: list[tuple[int, int, Cell, Cell]] = []
    for y in range(rectangle["y0"], rectangle["y1"] + 1):
        for x in range(rectangle["x0"], rectangle["x1"] + 1):
            attempt_x = x + dx
            attempt_y = y + dy
            attempt_cell = (
                attempt[attempt_y][attempt_x]
                if 0 <= attempt_x < frame_w and 0 <= attempt_y < frame_h
                else None
            )
            pairs.append((x, y, canonical[y][x], attempt_cell))
    return pairs


def _first_occupancy_mismatch(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    rectangle: Mapping[str, int],
    dx: int,
    dy: int,
    *,
    anchor_id: str,
) -> IdentityLockMismatch | None:
    for x, y, canonical_cell, attempt_cell in _registered_cells(
        canonical,
        attempt,
        rectangle,
        dx,
        dy,
    ):
        if (canonical_cell is None) != (attempt_cell is None):
            return IdentityLockMismatch(
                anchor=anchor_id,
                x=x,
                y=y,
                expected_rgba=_cell_to_rgba(canonical_cell),
                actual_rgba=_cell_to_rgba(attempt_cell),
            )
    return None


def _compare_structural_lock(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    lock: Mapping[str, Any],
    offset: tuple[int, int],
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
    palette_roles: Sequence[str],
) -> tuple[dict[str, Any], IdentityLockMismatch | None]:
    rectangle = lock["rectangle"]
    dx, dy = offset
    occupancy_changes = 0
    occupancy_union = 0
    canonical_counts = {role: 0 for role in palette_roles}
    attempt_counts = {role: 0 for role in palette_roles}
    canonical_opaque = 0
    attempt_opaque = 0

    for _, _, canonical_cell, attempt_cell in _registered_cells(
        canonical,
        attempt,
        rectangle,
        dx,
        dy,
    ):
        canonical_present = canonical_cell is not None
        attempt_present = attempt_cell is not None
        occupancy_union += int(canonical_present or attempt_present)
        occupancy_changes += int(canonical_present != attempt_present)
        canonical_role = nearest_palette_role(canonical_cell, palette_entries)
        attempt_role = nearest_palette_role(attempt_cell, palette_entries)
        if canonical_role is not None:
            canonical_counts[canonical_role] += 1
            canonical_opaque += 1
        if attempt_role is not None:
            attempt_counts[attempt_role] += 1
            attempt_opaque += 1

    occupancy_difference = (
        occupancy_changes / occupancy_union if occupancy_union else 0.0
    )
    comparison = str(lock["comparison"])
    palette_role_distance = 0.0
    if comparison == "registered-structure":
        palette_role_distance = 0.5 * sum(
            abs(
                (
                    canonical_counts[role] / canonical_opaque
                    if canonical_opaque
                    else 0.0
                )
                - (
                    attempt_counts[role] / attempt_opaque
                    if attempt_opaque
                    else 0.0
                )
            )
            for role in palette_roles
        )
        passed = (
            occupancy_difference <= float(lock["max_occupancy_difference"])
            and palette_role_distance <= float(lock["max_palette_role_distance"])
        )
    else:
        passed = occupancy_difference == 0.0

    result: dict[str, Any] = {
        "outcome": "PASS" if passed else "FAIL",
        "comparison": comparison,
        "occupancy_difference": occupancy_difference,
        "palette_role_distance": (
            palette_role_distance if comparison == "registered-structure" else None
        ),
    }
    if comparison == "registered-structure":
        result.update(
            {
                "max_occupancy_difference": lock["max_occupancy_difference"],
                "max_palette_role_distance": lock["max_palette_role_distance"],
            }
        )
    mismatch = None
    if not passed:
        mismatch = _first_occupancy_mismatch(
            canonical,
            attempt,
            rectangle,
            dx,
            dy,
            anchor_id=str(lock["id"]),
        )
    return result, mismatch


def _landmark_anchor(
    landmark: Mapping[str, Any],
    locks: Sequence[Mapping[str, Any]],
) -> str:
    x, y = landmark["canonical"]
    for lock in locks:
        rectangle = lock["rectangle"]
        if (
            rectangle["x0"] <= x <= rectangle["x1"]
            and rectangle["y0"] <= y <= rectangle["y1"]
        ):
            return str(lock["id"])
    return str(locks[0]["id"])


def _evaluate_landmarks(
    canonical: list[list[Cell]],
    attempt: list[list[Cell]],
    landmarks: Sequence[Mapping[str, Any]],
    locks: Sequence[Mapping[str, Any]],
    offsets: Mapping[str, tuple[int, int]],
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> tuple[dict[str, dict[str, Any]], IdentityLockMismatch | None]:
    frame_h = len(attempt)
    frame_w = len(attempt[0])
    results: dict[str, dict[str, Any]] = {}
    first_mismatch: IdentityLockMismatch | None = None
    for landmark in landmarks:
        landmark_id = str(landmark["id"])
        anchor_id = _landmark_anchor(landmark, locks)
        dx, dy = offsets[anchor_id]
        canonical_x, canonical_y = landmark["canonical"]
        expected_x, expected_y = canonical_x + dx, canonical_y + dy
        max_distance = int(landmark["max_distance"])
        expected_role = str(landmark["palette_role"])
        candidates: list[tuple[int, int, int]] = []
        for y in range(expected_y - max_distance, expected_y + max_distance + 1):
            for x in range(expected_x - max_distance, expected_x + max_distance + 1):
                if not 0 <= x < frame_w or not 0 <= y < frame_h:
                    continue
                if nearest_palette_role(attempt[y][x], palette_entries) == expected_role:
                    distance = max(abs(x - expected_x), abs(y - expected_y))
                    candidates.append((distance, y, x))
        actual_position: list[int] | None = None
        actual_role: str | None = None
        if candidates:
            _, actual_y, actual_x = min(candidates)
            actual_position = [actual_x, actual_y]
            actual_role = expected_role
        elif 0 <= expected_x < frame_w and 0 <= expected_y < frame_h:
            actual_role = nearest_palette_role(
                attempt[expected_y][expected_x],
                palette_entries,
            )
        outcome: Outcome = "PASS" if actual_position is not None else "FAIL"
        results[landmark_id] = {
            "outcome": outcome,
            "expected_role": expected_role,
            "actual_role": actual_role,
            "expected_position": [expected_x, expected_y],
            "actual_position": actual_position,
            "max_distance": max_distance,
            "anchor": anchor_id,
        }
        if outcome == "FAIL" and first_mismatch is None:
            actual = (
                attempt[expected_y][expected_x]
                if 0 <= expected_x < frame_w and 0 <= expected_y < frame_h
                else None
            )
            first_mismatch = IdentityLockMismatch(
                anchor=f"landmark:{landmark_id}",
                x=canonical_x,
                y=canonical_y,
                expected_rgba=_cell_to_rgba(canonical[canonical_y][canonical_x]),
                actual_rgba=_cell_to_rgba(actual),
            )
    return results, first_mismatch


def _first_failure(
    check_results: Mapping[str, Mapping[str, Any]],
    landmark_results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    for check_id, check in check_results.items():
        if check["outcome"] == "FAIL":
            return {"kind": "check", "id": check_id, **dict(check)}
    for landmark_id, landmark in landmark_results.items():
        if landmark["outcome"] == "FAIL":
            return {"kind": "landmark", "id": landmark_id, **dict(landmark)}
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
    landmarks: Sequence[Mapping[str, Any]],
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
    palette_roles: Sequence[str],
) -> tuple[
    dict[str, tuple[int, int]],
    dict[str, Outcome],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    IdentityLockMismatch | None,
]:
    canonical_offsets = {lock["id"]: (0, 0) for lock in locks}
    offset_lists = [lock["offsets"] for lock in locks]
    lock_ids = [lock["id"] for lock in locks]

    best_failure: tuple[
        dict[str, tuple[int, int]],
        dict[str, Outcome],
        dict[str, dict[str, Any]],
        IdentityLockMismatch | None,
    ] | None = None
    best_success: tuple[
        dict[str, tuple[int, int]],
        dict[str, Outcome],
        dict[str, dict[str, Any]],
    ] | None = None
    best_pass_count = -1
    best_success_score = float("inf")
    best_failure_score = float("inf")

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
        check_results: dict[str, dict[str, Any]] = {}
        first_mismatch: IdentityLockMismatch | None = None
        for lock in locks:
            check, mismatch = _compare_structural_lock(
                canonical,
                attempt,
                lock,
                offsets[lock["id"]],
                palette_entries,
                palette_roles,
            )
            check_results[lock["id"]] = check
            if check["outcome"] == "FAIL":
                anchor_results[lock["id"]] = "FAIL"
                if mismatch is not None and first_mismatch is None:
                    first_mismatch = mismatch
            else:
                anchor_results[lock["id"]] = "PASS"
        structural_score = sum(
            float(check["occupancy_difference"])
            + float(check.get("palette_role_distance") or 0.0)
            for check in check_results.values()
        )
        structural_score += 0.000001 * sum(
            abs(dx) + abs(dy) for dx, dy in offsets.values()
        )
        if all(outcome == "PASS" for outcome in anchor_results.values()):
            if structural_score < best_success_score:
                best_success_score = structural_score
                best_success = (offsets, anchor_results, check_results)
            continue
        pass_count = sum(
            1 for outcome in anchor_results.values() if outcome == "PASS"
        )
        if pass_count > best_pass_count or (
            pass_count == best_pass_count and structural_score < best_failure_score
        ):
            best_pass_count = pass_count
            best_failure_score = structural_score
            best_failure = (
                offsets,
                anchor_results,
                check_results,
                first_mismatch,
            )

    if best_success is not None:
        offsets, anchor_results, check_results = best_success
        landmark_results, landmark_mismatch = _evaluate_landmarks(
            canonical,
            attempt,
            landmarks,
            locks,
            offsets,
            palette_entries,
        )
        return (
            offsets,
            anchor_results,
            check_results,
            landmark_results,
            landmark_mismatch,
        )

    if best_failure is not None:
        offsets, anchor_results, check_results, first_mismatch = best_failure
        landmark_results, landmark_mismatch = _evaluate_landmarks(
            canonical,
            attempt,
            landmarks,
            locks,
            offsets,
            palette_entries,
        )
        return (
            offsets,
            anchor_results,
            check_results,
            landmark_results,
            first_mismatch or landmark_mismatch,
        )

    offsets = {lock["id"]: lock["offsets"][0] for lock in locks}
    anchor_results = {lock["id"]: "FAIL" for lock in locks}
    check_results: dict[str, dict[str, Any]] = {}
    first_mismatch: IdentityLockMismatch | None = None
    for lock in locks:
        check, mismatch = _compare_structural_lock(
            canonical,
            attempt,
            lock,
            offsets[lock["id"]],
            palette_entries,
            palette_roles,
        )
        check_results[lock["id"]] = check
        if mismatch is not None and first_mismatch is None:
            first_mismatch = mismatch
    landmark_results, landmark_mismatch = _evaluate_landmarks(
        canonical,
        attempt,
        landmarks,
        locks,
        offsets,
        palette_entries,
    )
    return (
        offsets,
        anchor_results,
        check_results,
        landmark_results,
        first_mismatch or landmark_mismatch,
    )


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
        raise IdentityLockError(
            f"motion class {motion_class!r} has no Identity Lock rules"
        )

    frame_size = (int(spec["frame_size"][0]), int(spec["frame_size"][1]))
    canonical = load_canonical_cells(identity_path, frame_size)
    if sha256_file(identity_path) != spec["identity_sha256"]:
        raise IdentityLockError(
            "evaluated identity image does not match bound identity_sha256"
        )
    locks = [
        _validate_lock_row(lock, where=f"motion_classes.{motion_class}")
        for lock in motion_doc["locks"]
    ]
    constraints = motion_doc.get("relational_constraints", []) or []
    landmarks = motion_doc.get("landmarks", []) or []
    palette_path = _resolve_bound_repo_file(
        spec["master_palette"],
        label="master_palette",
    )
    palette_roles, palette_entries = _load_palette_roles(palette_path)

    per_frame: list[FrameIdentityLockResult] = []
    overall_failure: dict[str, Any] | None = None
    overall_mismatch: IdentityLockMismatch | None = None

    for frame_index, attempt in enumerate(frames):
        if len(attempt) != frame_size[1] or any(
            len(row) != frame_size[0] for row in attempt
        ):
            raise IdentityLockError(
                "attempt frame size does not match Identity Lock frame_size"
            )
        (
            offsets,
            anchor_results,
            check_results,
            landmark_results,
            mismatch,
        ) = _find_frame_offsets(
            canonical,
            list(attempt),
            locks,
            constraints,
            landmarks,
            palette_entries,
            palette_roles,
        )
        failure = _first_failure(check_results, landmark_results)
        per_frame.append(
            FrameIdentityLockResult(
                selected_offsets=offsets,
                anchor_results=anchor_results,
                check_results=check_results,
                landmark_results=landmark_results,
                first_failure=failure,
                first_mismatch=mismatch,
            )
        )
        if failure is not None and overall_failure is None:
            overall_failure = {"frame_index": frame_index, **failure}
        if mismatch is not None and overall_mismatch is None:
            overall_mismatch = mismatch

    outcome: Outcome = "PASS" if overall_failure is None else "FAIL"
    return IdentityLockResult(
        outcome=outcome,
        identity_sha256=str(spec["identity_sha256"]),
        lock_spec_sha256=sha256_file(spec_path),
        motion_class=motion_class,
        per_frame=tuple(per_frame),
        first_failure=overall_failure,
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


def identity_lock_rejection_detail(result: IdentityLockResult) -> dict[str, Any] | None:
    """Summarize a FAIL Identity Lock result as a near-miss ledger detail payload."""
    if result.outcome == "PASS":
        return None

    first_failure = result.first_failure
    if first_failure is None:
        return {
            "schema": IDENTITY_LOCK_NEAR_MISS_SCHEMA,
            "primary_reason_code": "identity_lock",
        }

    detail: dict[str, Any] = {
        "schema": IDENTITY_LOCK_NEAR_MISS_SCHEMA,
        "primary_reason_code": "identity_lock",
    }

    frame_index = first_failure.get("frame_index")
    kind = first_failure.get("kind")
    failure_id = first_failure.get("id")
    if frame_index is not None:
        detail["frame_index"] = frame_index
    if kind is not None:
        detail["kind"] = kind
    if failure_id is not None:
        detail["id"] = failure_id

    if isinstance(frame_index, int) and 0 <= frame_index < len(result.per_frame):
        frame = result.per_frame[frame_index]
        detail["selected_offsets"] = {
            anchor: [offsets[0], offsets[1]]
            for anchor, offsets in frame.selected_offsets.items()
        }

    if kind == "check":
        occupancy_difference = first_failure.get("occupancy_difference")
        max_occupancy_difference = first_failure.get("max_occupancy_difference")
        if occupancy_difference is not None:
            detail["occupancy_difference"] = occupancy_difference
        if max_occupancy_difference is not None:
            detail["max_occupancy_difference"] = max_occupancy_difference
            if occupancy_difference is not None:
                detail["occupancy_margin"] = (
                    float(max_occupancy_difference) - float(occupancy_difference)
                )
            if (
                occupancy_difference is not None
                and float(occupancy_difference)
                <= float(max_occupancy_difference) + 0.05
            ):
                detail["primary_reason_code"] = "identity_lock_near_miss"

        palette_role_distance = first_failure.get("palette_role_distance")
        max_palette_role_distance = first_failure.get("max_palette_role_distance")
        if palette_role_distance is not None:
            detail["palette_role_distance"] = palette_role_distance
        if max_palette_role_distance is not None:
            detail["max_palette_role_distance"] = max_palette_role_distance

    mismatch_payload = _mismatch_payload(result.first_mismatch)
    if mismatch_payload is not None:
        detail["first_mismatch"] = mismatch_payload

    return detail


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
                "check_results": dict(frame.check_results),
                "landmark_results": dict(frame.landmark_results),
                "first_failure": frame.first_failure,
                "first_mismatch": _mismatch_payload(frame.first_mismatch),
            }
            for frame in result.per_frame
        ],
        "first_failure": result.first_failure,
        "first_mismatch": _mismatch_payload(result.first_mismatch),
    }


def exact_magenta_fraction(image_path: Path) -> float:
    """Fraction of pixels whose RGB is exactly transport magenta ``#FF00FF``."""
    if not image_path.is_file():
        raise IdentityLockError(f"missing image for magenta fraction: {image_path}")
    try:
        with Image.open(image_path) as image:
            rgba = np.asarray(image.convert("RGBA"))
    except UnidentifiedImageError as exc:
        raise IdentityLockError(f"unreadable image: {image_path}") from exc
    if rgba.size == 0:
        return 0.0
    exact = (
        (rgba[:, :, 0] == TRANSPORT_MAGENTA[0])
        & (rgba[:, :, 1] == TRANSPORT_MAGENTA[1])
        & (rgba[:, :, 2] == TRANSPORT_MAGENTA[2])
    )
    return float(exact.mean())


def evaluate_edit_source_continuity(
    provider_frames: Sequence[Sequence[Sequence[Cell]]],
    edit_source_frames: Sequence[Sequence[Sequence[Cell]]],
    motion_class: str,
    *,
    spec_path: Path = DEFAULT_IDENTITY_LOCKS_PATH,
) -> EditSourceContinuityResult:
    """Compare provider lock regions to the edit-source Frames (not identity.png).

    A clean idle-seed image-edit keeps locked Cells continuous with the edit
    source under the same offsets/thresholds as Identity Lock. Corpus redraws
    that do not share idle lock construction FAIL this check.
    """
    if not provider_frames:
        raise IdentityLockError("provider frames required for edit-source continuity")
    if not edit_source_frames:
        raise IdentityLockError("edit-source frames required for edit-source continuity")

    spec = load_identity_lock_spec(spec_path)
    motion_doc = spec["motion_classes"].get(motion_class)
    if motion_doc is None:
        raise IdentityLockError(
            f"motion class {motion_class!r} has no Identity Lock rules"
        )

    frame_size = (int(spec["frame_size"][0]), int(spec["frame_size"][1]))
    locks = [
        _validate_lock_row(lock, where=f"motion_classes.{motion_class}")
        for lock in motion_doc["locks"]
    ]
    constraints = motion_doc.get("relational_constraints", []) or []
    # Landmarks are absolute identity anchors — skip them for edit-source continuity.
    landmarks: list[Any] = []
    palette_path = _resolve_bound_repo_file(
        spec["master_palette"],
        label="master_palette",
    )
    palette_roles, palette_entries = _load_palette_roles(palette_path)

    overall_failure: dict[str, Any] | None = None
    overall_mismatch: IdentityLockMismatch | None = None
    for frame_index, attempt in enumerate(provider_frames):
        if len(attempt) != frame_size[1] or any(
            len(row) != frame_size[0] for row in attempt
        ):
            raise IdentityLockError(
                "provider frame size does not match Identity Lock frame_size"
            )
        source_index = min(frame_index, len(edit_source_frames) - 1)
        canonical = list(edit_source_frames[source_index])
        if len(canonical) != frame_size[1] or any(
            len(row) != frame_size[0] for row in canonical
        ):
            raise IdentityLockError(
                "edit-source frame size does not match Identity Lock frame_size"
            )
        (
            _offsets,
            _anchor_results,
            check_results,
            landmark_results,
            mismatch,
        ) = _find_frame_offsets(
            canonical,
            list(attempt),
            locks,
            constraints,
            landmarks,
            palette_entries,
            palette_roles,
        )
        failure = _first_failure(check_results, landmark_results)
        if failure is not None and overall_failure is None:
            overall_failure = {"frame_index": frame_index, **failure}
        if mismatch is not None and overall_mismatch is None:
            overall_mismatch = mismatch

    if overall_failure is None:
        return EditSourceContinuityResult(
            outcome="PASS",
            reason_code=None,
            motion_class=motion_class,
            first_failure=None,
            first_mismatch=None,
        )
    return EditSourceContinuityResult(
        outcome="FAIL",
        reason_code="edit_source_continuity_fail",
        motion_class=motion_class,
        first_failure=overall_failure,
        first_mismatch=overall_mismatch,
    )


def evaluate_provider_post_edit(
    provider_path: Path,
    edit_source_path: Path,
    *,
    motion_class: str,
    layout: Any | None = None,
) -> ProviderPostEditResult:
    """Reject provider rasters post-edited to clear Gates (magenta wipe; lock drift).

    Magenta wipe is a hard integrity signal from the #159 stamp pipeline. Edit-source
    continuity compares recovered lock regions to the idle edit source.
    """
    from pipeline.strip import (  # local import avoids cycle at module load
        DEFAULT_LAYOUT,
        StripLayout,
        canonicalize_frame,
        load_provider_frames,
    )

    provider_frac = exact_magenta_fraction(provider_path)
    edit_frac = exact_magenta_fraction(edit_source_path)
    magenta_wipe = {
        "outcome": "PASS",
        "provider_exact_fraction": provider_frac,
        "edit_source_exact_fraction": edit_frac,
        "min_provider_fraction": MAGENTA_WIPE_MIN_PROVIDER_FRACTION,
        "max_edit_source_fraction": MAGENTA_WIPE_MAX_EDIT_SOURCE_FRACTION,
    }
    if (
        provider_frac >= MAGENTA_WIPE_MIN_PROVIDER_FRACTION
        and edit_frac <= MAGENTA_WIPE_MAX_EDIT_SOURCE_FRACTION
    ):
        magenta_wipe["outcome"] = "FAIL"
        return ProviderPostEditResult(
            outcome="FAIL",
            reason_code="provider_magenta_wipe",
            magenta_wipe=magenta_wipe,
            continuity=None,
        )

    probe = layout
    if probe is None:
        probe = StripLayout(
            frame_w=DEFAULT_LAYOUT.frame_w,
            frame_h=DEFAULT_LAYOUT.frame_h,
            frame_count=DEFAULT_LAYOUT.frame_count,
            gutter=DEFAULT_LAYOUT.gutter,
            pitch_px=24,
            margin_cells=0,
        )
    provider_raw = load_provider_frames(provider_path, probe)
    edit_raw = load_provider_frames(edit_source_path, probe)
    if provider_raw is None or edit_raw is None:
        return ProviderPostEditResult(
            outcome="FAIL",
            reason_code="edit_source_continuity_fail",
            magenta_wipe=magenta_wipe,
            continuity=EditSourceContinuityResult(
                outcome="FAIL",
                reason_code="edit_source_continuity_fail",
                motion_class=motion_class,
                first_failure={"kind": "recovery", "id": "load_provider_frames"},
                first_mismatch=None,
            ),
        )

    provider_frames = [
        canonicalize_frame(frame, frame_w=probe.frame_w, frame_h=probe.frame_h)
        for frame in provider_raw
    ]
    edit_frames = [
        canonicalize_frame(frame, frame_w=probe.frame_w, frame_h=probe.frame_h)
        for frame in edit_raw
    ]
    continuity = evaluate_edit_source_continuity(
        provider_frames,
        edit_frames,
        motion_class,
    )
    if continuity.outcome != "PASS":
        return ProviderPostEditResult(
            outcome="FAIL",
            reason_code=continuity.reason_code,
            magenta_wipe=magenta_wipe,
            continuity=continuity,
        )
    return ProviderPostEditResult(
        outcome="PASS",
        reason_code=None,
        magenta_wipe=magenta_wipe,
        continuity=continuity,
    )


def provider_post_edit_report_payload(
    result: ProviderPostEditResult,
) -> dict[str, Any]:
    continuity_payload: dict[str, Any] | None = None
    if result.continuity is not None:
        continuity_payload = {
            "outcome": result.continuity.outcome,
            "reason_code": result.continuity.reason_code,
            "motion_class": result.continuity.motion_class,
            "first_failure": result.continuity.first_failure,
            "first_mismatch": _mismatch_payload(result.continuity.first_mismatch),
        }
    return {
        "outcome": result.outcome,
        "reason_code": result.reason_code,
        "magenta_wipe": dict(result.magenta_wipe),
        "continuity": continuity_payload,
    }


def _parse_seed_pad_px(raw: object) -> int:
    if not isinstance(raw, int) or raw <= 0:
        raise IdentityLockError("seed_pad_px must be a positive integer")
    return raw


def magenta_pad_generation_source_png(
    generation_source_png_bytes: bytes,
    seed_pad_px: int,
) -> bytes:
    """Return a PNG whose border ring is exact transport magenta and interior matches source."""
    pad_px = _parse_seed_pad_px(seed_pad_px)
    try:
        with Image.open(BytesIO(generation_source_png_bytes)) as generation_source:
            source_rgba = generation_source.convert("RGBA")
            gen_w, gen_h = source_rgba.size
    except UnidentifiedImageError as exc:
        raise IdentityLockError("generation source must be a readable PNG") from exc

    out_w = gen_w + 2 * pad_px
    out_h = gen_h + 2 * pad_px
    padded = Image.new(
        "RGBA",
        (out_w, out_h),
        (*TRANSPORT_MAGENTA, 255),
    )
    padded.paste(source_rgba, (pad_px, pad_px))
    out_buf = BytesIO()
    padded.save(out_buf, format="PNG")
    return out_buf.getvalue()


def expected_image_edit_source_sha256(
    declaration: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> str:
    """SHA-256 of the image-edit seed implied by a dwarf-identity/0 declaration."""
    generation_binding = declaration.get("generation_source")
    if not isinstance(generation_binding, dict):
        raise IdentityLockError(
            "identity declaration requires generation_source bindings"
        )
    generation_sha = generation_binding.get("sha256")
    if not isinstance(generation_sha, str) or len(generation_sha) != 64:
        raise IdentityLockError("generation_source.sha256 must be a 64-char hex digest")
    seed_pad_px = declaration.get("seed_pad_px")
    if seed_pad_px is None:
        return generation_sha
    pad_px = _parse_seed_pad_px(seed_pad_px)
    repo_root = root if root is not None else _REPO_ROOT
    try:
        generation_path = canonical.verify_binding(
            generation_binding,
            root=repo_root,
            label="generation source",
        )
    except canonical.BindingError as exc:
        raise IdentityLockError(str(exc)) from exc
    padded_bytes = magenta_pad_generation_source_png(
        generation_path.read_bytes(),
        pad_px,
    )
    return sha256_bytes(padded_bytes)


def build_identity_seed(
    identity_declaration_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Emit the image-edit seed from ``identity.json`` bindings.

    Without ``seed_pad_px``, copies ``generation_source`` byte-for-byte. When
    ``seed_pad_px`` is declared, writes a uniform ``#FF00FF`` pad of that width
    on all four sides around the generation-source raster (interior unchanged).
    ``identity_png`` (16×24) is validated but never copied — it is the Identity
    Lock anchor, not the image-edit canvas.
    """
    if not identity_declaration_path.is_file():
        raise IdentityLockError(
            f"missing identity declaration: {identity_declaration_path}"
        )
    try:
        declaration = json.loads(identity_declaration_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityLockError("identity declaration must be valid JSON") from exc
    if not isinstance(declaration, dict) or declaration.get("schema") != "dwarf-identity/0":
        raise IdentityLockError("identity declaration must use schema dwarf-identity/0")

    identity_binding = declaration.get("identity_png")
    generation_binding = declaration.get("generation_source")
    if not isinstance(identity_binding, dict) or not isinstance(generation_binding, dict):
        raise IdentityLockError(
            "identity declaration requires identity_png and generation_source bindings"
        )

    identity_path = _resolve_bound_repo_file(
        identity_binding,
        label="identity anchor",
    )
    generation_source_path = _resolve_bound_repo_file(
        generation_binding,
        label="generation source",
    )
    identity_sha = str(identity_binding["sha256"])
    generation_source_sha = str(generation_binding["sha256"])
    with Image.open(identity_path) as identity:
        if identity.size != (16, 24):
            raise IdentityLockError("identity anchor must be a 16×24 Release Frame")
    with Image.open(generation_source_path) as generation_source:
        gen_w, gen_h = generation_source.size

    seed_pad_px_raw = declaration.get("seed_pad_px")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "identity_declaration_path": str(identity_declaration_path.resolve()),
        "generation_source_path": str(generation_source_path),
        "generation_source_sha256": generation_source_sha,
        "identity_anchor_path": str(identity_path),
        "identity_anchor_sha256": identity_sha,
        "out_path": str(out_path.resolve()),
    }
    if seed_pad_px_raw is None:
        shutil.copyfile(generation_source_path, out_path)
        result["dimensions"] = [gen_w, gen_h]
        result["sha256"] = sha256_file(out_path)
        return result

    seed_pad_px = _parse_seed_pad_px(seed_pad_px_raw)
    padded_bytes = magenta_pad_generation_source_png(
        generation_source_path.read_bytes(),
        seed_pad_px,
    )
    out_path.write_bytes(padded_bytes)
    result.update(
        {
            "seed_pad_px": seed_pad_px,
            "dimensions": [gen_w + 2 * seed_pad_px, gen_h + 2 * seed_pad_px],
            "sha256": sha256_bytes(padded_bytes),
        }
    )
    return result
