"""Declarative Motion Author for lock-aware Cell pose execution (issue #277)."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from pipeline.canonical import packet_bytes
from pipeline.cell_delta import build_cell_delta_ledger
from pipeline.identity_lock import validate_identity_lock_spec
from pipeline.palette_quantize import MasterPalette
from pipeline.strip import Cell, resolve_class_frame_geometry

__all__ = [
    "AuthoredMotion",
    "MOTION_POSE_PLAN_SCHEMA",
    "MotionAuthorError",
    "author_motion",
]

MOTION_POSE_PLAN_SCHEMA = "motion-pose-plan/0"
REPORT_SCHEMA = "motion-author-report/0"


class MotionAuthorError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AuthoredMotion:
    frames: tuple[list[list[Cell]], ...]
    ledger: dict[str, Any]
    report: dict[str, Any]


def _parse_hex_color(value: object, *, where: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise MotionAuthorError(
            f"invalid color at {where}",
            reason_code="invalid_palette_role",
        )
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise MotionAuthorError(
            f"invalid color at {where}",
            reason_code="invalid_palette_role",
        ) from exc


def _expand_offsets(spec: object) -> list[tuple[int, int]]:
    if isinstance(spec, list):
        offsets: list[tuple[int, int]] = []
        for entry in spec:
            if (
                not isinstance(entry, list)
                or len(entry) != 2
                or not all(isinstance(axis, int) for axis in entry)
            ):
                raise MotionAuthorError(
                    "permitted_offsets list entries must be [dx, dy]",
                    reason_code="authoring_boundary_violation",
                )
            offsets.append((int(entry[0]), int(entry[1])))
        return offsets
    if isinstance(spec, dict):
        dx_values = spec.get("dx")
        dy_values = spec.get("dy")
        if not isinstance(dx_values, list) or not isinstance(dy_values, list):
            raise MotionAuthorError(
                "permitted_offsets object requires dx and dy arrays",
                reason_code="authoring_boundary_violation",
            )
        return [
            (int(dx), int(dy))
            for dx in dx_values
            for dy in dy_values
        ]
    raise MotionAuthorError(
        "permitted_offsets must be a list or dx/dy object",
        reason_code="authoring_boundary_violation",
    )


def _parse_locks(identity_lock_spec: Mapping[str, Any], motion_class: str) -> dict[str, dict[str, Any]]:
    motion_classes = identity_lock_spec.get("motion_classes")
    if not isinstance(motion_classes, dict):
        raise MotionAuthorError(
            "identity lock spec missing motion_classes",
            reason_code="authoring_boundary_violation",
        )
    motion_doc = motion_classes.get(motion_class)
    if not isinstance(motion_doc, dict):
        raise MotionAuthorError(
            f"motion class {motion_class!r} missing from identity lock spec",
            reason_code="authoring_boundary_violation",
        )
    locks = motion_doc.get("locks")
    if not isinstance(locks, list) or not locks:
        raise MotionAuthorError(
            f"motion_classes.{motion_class}.locks must be a non-empty array",
            reason_code="authoring_boundary_violation",
        )
    parsed: dict[str, dict[str, Any]] = {}
    for lock in locks:
        if not isinstance(lock, dict):
            raise MotionAuthorError("lock row must be an object", reason_code="authoring_boundary_violation")
        lock_id = lock.get("id")
        rectangle = lock.get("rectangle")
        offsets = lock.get("permitted_offsets")
        if not isinstance(lock_id, str) or not lock_id:
            raise MotionAuthorError("lock missing id", reason_code="authoring_boundary_violation")
        if not isinstance(rectangle, dict):
            raise MotionAuthorError(f"lock {lock_id} missing rectangle", reason_code="authoring_boundary_violation")
        if offsets is None:
            raise MotionAuthorError(
                f"lock {lock_id} missing permitted_offsets",
                reason_code="authoring_boundary_violation",
            )
        parsed[lock_id] = {
            "rectangle": {
                "x0": int(rectangle["x0"]),
                "x1": int(rectangle["x1"]),
                "y0": int(rectangle["y0"]),
                "y1": int(rectangle["y1"]),
            },
            "offsets": _expand_offsets(offsets),
        }
    return parsed


def _validate_pose_plan(
    pose_plan: Mapping[str, Any],
    *,
    identity_lock_spec: Mapping[str, Any],
) -> tuple[str, int, int, tuple[int, int], str, list[int], list[list[dict[str, Any]]]]:
    schema = pose_plan.get("schema")
    if schema != MOTION_POSE_PLAN_SCHEMA:
        raise MotionAuthorError(
            f"schema must be {MOTION_POSE_PLAN_SCHEMA!r}",
            reason_code="authoring_boundary_violation",
        )
    motion_class = pose_plan.get("motion_class")
    if not isinstance(motion_class, str) or not motion_class:
        raise MotionAuthorError("motion_class required", reason_code="authoring_boundary_violation")
    frame_size = pose_plan.get("frame_size")
    if (
        not isinstance(frame_size, list)
        or len(frame_size) != 2
        or not all(isinstance(axis, int) and axis > 0 for axis in frame_size)
    ):
        raise MotionAuthorError("frame_size invalid", reason_code="authoring_boundary_violation")
    frame_w, frame_h = int(frame_size[0]), int(frame_size[1])
    frame_count = pose_plan.get("frame_count")
    if not isinstance(frame_count, int) or frame_count < 1:
        raise MotionAuthorError("frame_count invalid", reason_code="authoring_boundary_violation")
    canonical_origin = pose_plan.get("canonical_origin")
    if (
        not isinstance(canonical_origin, list)
        or len(canonical_origin) != 2
        or not all(isinstance(axis, int) for axis in canonical_origin)
    ):
        raise MotionAuthorError("canonical_origin invalid", reason_code="authoring_boundary_violation")
    origin = (int(canonical_origin[0]), int(canonical_origin[1]))
    base_specification_id = pose_plan.get("base_specification_id")
    if not isinstance(base_specification_id, str) or not base_specification_id:
        raise MotionAuthorError(
            "base_specification_id required",
            reason_code="authoring_boundary_violation",
        )
    base_frame_mapping = pose_plan.get("base_frame_mapping")
    if not isinstance(base_frame_mapping, list):
        raise MotionAuthorError(
            "base_frame_mapping must be an array",
            reason_code="authoring_boundary_violation",
        )
    mapping = [int(index) for index in base_frame_mapping]
    if len(mapping) != frame_count:
        raise MotionAuthorError(
            "base_frame_mapping length must match frame_count",
            reason_code="authoring_boundary_violation",
        )
    frames = pose_plan.get("frames")
    if not isinstance(frames, list) or len(frames) != frame_count:
        raise MotionAuthorError("frames must match frame_count", reason_code="authoring_boundary_violation")

    geometry = resolve_class_frame_geometry(motion_class)
    if frame_w != geometry.frame_w or frame_h != geometry.frame_h:
        raise MotionAuthorError(
            "frame_size disagrees with motion class geometry",
            reason_code="authoring_boundary_violation",
        )
    if origin != geometry.canonical_origin:
        raise MotionAuthorError(
            "canonical_origin disagrees with motion class geometry",
            reason_code="authoring_boundary_violation",
        )

    motion_classes = identity_lock_spec.get("motion_classes")
    if not isinstance(motion_classes, dict) or motion_class not in motion_classes:
        raise MotionAuthorError(
            f"motion class {motion_class!r} missing from identity lock spec",
            reason_code="authoring_boundary_violation",
        )
    motion_doc = motion_classes[motion_class]
    if isinstance(motion_doc, dict) and "frame_size" in motion_doc:
        class_size = motion_doc["frame_size"]
        if (
            isinstance(class_size, list)
            and len(class_size) == 2
            and (int(class_size[0]), int(class_size[1])) != (frame_w, frame_h)
        ):
            raise MotionAuthorError(
                "frame_size disagrees with identity lock declaration",
                reason_code="authoring_boundary_violation",
            )

    parsed_frames: list[list[dict[str, Any]]] = []
    for index, frame_ops in enumerate(frames):
        if not isinstance(frame_ops, list):
            raise MotionAuthorError(
                f"frames[{index}] must be an operation array",
                reason_code="authoring_boundary_violation",
            )
        ops: list[dict[str, Any]] = []
        for op_index, operation in enumerate(frame_ops):
            if not isinstance(operation, dict):
                raise MotionAuthorError(
                    f"frames[{index}][{op_index}] must be an object",
                    reason_code="authoring_boundary_violation",
                )
            ops.append(dict(operation))
        parsed_frames.append(ops)

    return motion_class, frame_w, frame_h, origin, base_specification_id, mapping, parsed_frames


def _lock_rectangle_at_offset(
    rectangle: Mapping[str, int],
    offset: tuple[int, int],
) -> tuple[int, int, int, int]:
    dx, dy = offset
    return (
        rectangle["x0"] + dx,
        rectangle["x1"] + dx,
        rectangle["y0"] + dy,
        rectangle["y1"] + dy,
    )


def _cell_in_rectangle(x: int, y: int, x0: int, x1: int, y0: int, y1: int) -> bool:
    return x0 <= x <= x1 and y0 <= y <= y1


def _locked_cells(
    locks: Mapping[str, dict[str, Any]],
    offsets: Mapping[str, tuple[int, int]],
) -> set[tuple[int, int]]:
    occupied: set[tuple[int, int]] = set()
    for lock_id, lock in locks.items():
        x0, x1, y0, y1 = _lock_rectangle_at_offset(lock["rectangle"], offsets[lock_id])
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                occupied.add((x, y))
    return occupied


def _assert_in_bounds(x: int, y: int, *, frame_w: int, frame_h: int) -> None:
    if not 0 <= x < frame_w or not 0 <= y < frame_h:
        raise MotionAuthorError(
            f"operation out of bounds at ({x}, {y})",
            reason_code="authoring_boundary_violation",
        )


def _resolve_paint_color(
    palette: MasterPalette,
    *,
    palette_role: object,
    color: object,
    where: str,
) -> tuple[int, int, int]:
    if not isinstance(palette_role, str) or palette_role not in palette.role_colors:
        raise MotionAuthorError(
            f"unknown palette role at {where}",
            reason_code="invalid_palette_role",
        )
    rgb = _parse_hex_color(color, where=where)
    allowed = palette.role_colors[palette_role]
    if rgb not in allowed:
        raise MotionAuthorError(
            f"color not in palette role at {where}",
            reason_code="invalid_palette_role",
        )
    return rgb


def _stroke_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points


def _alpha_bbox(cells: list[list[Cell]]) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, -1, -1
    return min(xs), min(ys), max(xs), max(ys)


def _boundary_column_load(cells: list[list[Cell]]) -> tuple[int, int]:
    width = len(cells[0]) if cells else 0
    left = sum(1 for row in cells if row[0] is not None)
    right = sum(1 for row in cells if row[width - 1] is not None)
    return left, right


def _changed_cell_count(base: list[list[Cell]], target: list[list[Cell]]) -> int:
    return sum(
        1
        for y in range(len(base))
        for x in range(len(base[0]))
        if base[y][x] != target[y][x]
    )


def _apply_operation(
    frame: list[list[Cell]],
    operation: Mapping[str, Any],
    *,
    frame_w: int,
    frame_h: int,
    locks: Mapping[str, dict[str, Any]],
    lock_offsets: dict[str, tuple[int, int]],
    locked: set[tuple[int, int]],
    palette: MasterPalette,
) -> None:
    op = operation.get("op")
    if op == "clear":
        x = operation.get("x")
        y = operation.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise MotionAuthorError("clear requires integer x and y", reason_code="authoring_boundary_violation")
        _assert_in_bounds(x, y, frame_w=frame_w, frame_h=frame_h)
        if (x, y) in locked:
            raise MotionAuthorError(
                f"cannot clear locked cell at ({x}, {y})",
                reason_code="identity_lock_write",
            )
        frame[y][x] = None
        return

    if op == "paint":
        x = operation.get("x")
        y = operation.get("y")
        if not isinstance(x, int) or not isinstance(y, int):
            raise MotionAuthorError("paint requires integer x and y", reason_code="authoring_boundary_violation")
        _assert_in_bounds(x, y, frame_w=frame_w, frame_h=frame_h)
        if (x, y) in locked:
            raise MotionAuthorError(
                f"cannot paint locked cell at ({x}, {y})",
                reason_code="identity_lock_write",
            )
        rgb = _resolve_paint_color(
            palette,
            palette_role=operation.get("palette_role"),
            color=operation.get("color"),
            where="paint",
        )
        frame[y][x] = rgb
        return

    if op == "stroke":
        for key in ("x0", "y0", "x1", "y1"):
            if not isinstance(operation.get(key), int):
                raise MotionAuthorError(
                    f"stroke requires integer {key}",
                    reason_code="authoring_boundary_violation",
                )
        x0 = int(operation["x0"])
        y0 = int(operation["y0"])
        x1 = int(operation["x1"])
        y1 = int(operation["y1"])
        rgb = _resolve_paint_color(
            palette,
            palette_role=operation.get("palette_role"),
            color=operation.get("color"),
            where="stroke",
        )
        for x, y in _stroke_cells(x0, y0, x1, y1):
            _assert_in_bounds(x, y, frame_w=frame_w, frame_h=frame_h)
            if (x, y) in locked:
                raise MotionAuthorError(
                    f"cannot stroke locked cell at ({x}, {y})",
                    reason_code="identity_lock_write",
                )
            frame[y][x] = rgb
        return

    if op == "relocate_lock":
        lock_id = operation.get("lock_id")
        dx = operation.get("dx")
        dy = operation.get("dy")
        if not isinstance(lock_id, str) or lock_id not in locks:
            raise MotionAuthorError(
                f"unknown lock {lock_id!r}",
                reason_code="authoring_boundary_violation",
            )
        if not isinstance(dx, int) or not isinstance(dy, int):
            raise MotionAuthorError(
                "relocate_lock requires integer dx and dy",
                reason_code="authoring_boundary_violation",
            )
        lock = locks[lock_id]
        current = lock_offsets[lock_id]
        target = (current[0] + dx, current[1] + dy)
        if target not in lock["offsets"]:
            raise MotionAuthorError(
                f"lock {lock_id} cannot move to offset {target}",
                reason_code="authoring_boundary_violation",
            )
        if (dx, dy) != (0, 0) and lock["offsets"] == [(0, 0)]:
            raise MotionAuthorError(
                f"lock {lock_id} cannot move",
                reason_code="authoring_boundary_violation",
            )
        x0, x1, y0, y1 = _lock_rectangle_at_offset(lock["rectangle"], current)
        for corner_x, corner_y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            _assert_in_bounds(corner_x, corner_y, frame_w=frame_w, frame_h=frame_h)
        new_x0, new_x1, new_y0, new_y1 = _lock_rectangle_at_offset(lock["rectangle"], target)
        for corner_x, corner_y in ((new_x0, new_y0), (new_x1, new_y0), (new_x0, new_y1), (new_x1, new_y1)):
            _assert_in_bounds(corner_x, corner_y, frame_w=frame_w, frame_h=frame_h)

        extracted: dict[tuple[int, int], Cell] = {}
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                cell = frame[y][x]
                if cell is not None:
                    extracted[(x - x0, y - y0)] = cell
                frame[y][x] = None
        shift_x = target[0] - current[0]
        shift_y = target[1] - current[1]
        for (rel_x, rel_y), cell in extracted.items():
            frame[y0 + rel_y + shift_y][x0 + rel_x + shift_x] = cell
        lock_offsets[lock_id] = target
        return

    raise MotionAuthorError(f"unknown operation {op!r}", reason_code="authoring_boundary_violation")


def author_motion(
    base_frames: Sequence[list[list[Cell]]],
    pose_plan: Mapping[str, Any],
    identity_lock_spec: Mapping[str, Any],
    master_palette: MasterPalette,
) -> AuthoredMotion:
    validate_identity_lock_spec(dict(identity_lock_spec))
    (
        motion_class,
        frame_w,
        frame_h,
        _origin,
        base_specification_id,
        base_frame_mapping,
        frame_operations,
    ) = _validate_pose_plan(pose_plan, identity_lock_spec=identity_lock_spec)

    locks = _parse_locks(identity_lock_spec, motion_class)
    lock_offsets = {lock_id: (0, 0) for lock_id in locks}
    for lock_id, lock in locks.items():
        if lock_offsets[lock_id] not in lock["offsets"]:
            lock_offsets[lock_id] = lock["offsets"][0]

    authored_frames: list[list[list[Cell]]] = []
    applied_lock_offsets: list[dict[str, list[int]]] = []
    frame_reports: list[dict[str, Any]] = []

    for frame_index, operations in enumerate(frame_operations):
        base_index = base_frame_mapping[frame_index]
        if not 0 <= base_index < len(base_frames):
            raise MotionAuthorError(
                f"invalid base frame mapping at {frame_index}",
                reason_code="authoring_boundary_violation",
            )
        base_frame = base_frames[base_index]
        if len(base_frame) != frame_h or (base_frame and len(base_frame[0]) != frame_w):
            raise MotionAuthorError(
                f"base frame dimensions mismatch at {frame_index}",
                reason_code="authoring_boundary_violation",
            )
        frame = copy.deepcopy(base_frame)
        frame_lock_offsets = dict(lock_offsets)
        for operation in operations:
            locked = _locked_cells(locks, frame_lock_offsets)
            _apply_operation(
                frame,
                operation,
                frame_w=frame_w,
                frame_h=frame_h,
                locks=locks,
                lock_offsets=frame_lock_offsets,
                locked=locked,
                palette=master_palette,
            )
        lock_offsets.update(frame_lock_offsets)
        authored_frames.append(frame)
        applied_lock_offsets.append(
            {lock_id: [offset[0], offset[1]] for lock_id, offset in frame_lock_offsets.items()}
        )
        bbox = _alpha_bbox(frame)
        left_load, right_load = _boundary_column_load(frame)
        frame_reports.append(
            {
                "frame": frame_index,
                "opaque_bbox": {
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                },
                "boundary_column_load": {"left": left_load, "right": right_load},
                "changed_cell_count": _changed_cell_count(base_frame, frame),
                "lock_offsets": applied_lock_offsets[-1],
            }
        )

    ledger = build_cell_delta_ledger(
        list(base_frames),
        authored_frames,
        base_specification_id=base_specification_id,
        base_frame_mapping=base_frame_mapping,
    )
    ledger_digest = hashlib.sha256(packet_bytes(ledger)).hexdigest()
    report = {
        "schema": REPORT_SCHEMA,
        "motion_class": motion_class,
        "pose_plan_schema": MOTION_POSE_PLAN_SCHEMA,
        "frame_size": [frame_w, frame_h],
        "frame_count": len(authored_frames),
        "frames": frame_reports,
        "applied_lock_offsets": applied_lock_offsets,
        "ledger_digest": ledger_digest,
    }
    return AuthoredMotion(
        frames=tuple(authored_frames),
        ledger=ledger,
        report=report,
    )
