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
from pipeline.parts import Footprint, ORIENTATION_IDS, Part, PartMap
from pipeline.strip import Cell, resolve_class_frame_geometry

__all__ = [
    "AuthoredMotion",
    "MOTION_POSE_PLAN_SCHEMA",
    "MOTION_POSE_PLAN_SCHEMA_V1",
    "MotionAuthorError",
    "author_motion",
]

MOTION_POSE_PLAN_SCHEMA = "motion-pose-plan/0"
MOTION_POSE_PLAN_SCHEMA_V1 = "motion-pose-plan/1"
REPORT_SCHEMA = "motion-author-report/0"
_PART_OPS = frozenset({"translate_part", "orient_part"})


class MotionAuthorError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AuthoredMotion:
    frames: tuple[list[list[Cell]], ...]
    ledger: dict[str, Any]
    report: dict[str, Any]
    part_maps: tuple[dict[str, Any], ...] | None = None


@dataclass
class _MutablePart:
    part_id: str
    rigid: bool
    parent: str | None
    pivot: tuple[int, int] | None
    grip: tuple[int, int] | None
    cells: set[tuple[int, int]]
    orientations: dict[str, Footprint] | None


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
) -> tuple[str, str, int, int, tuple[int, int], str, list[int], list[list[dict[str, Any]]]]:
    schema = pose_plan.get("schema")
    if schema not in {MOTION_POSE_PLAN_SCHEMA, MOTION_POSE_PLAN_SCHEMA_V1}:
        raise MotionAuthorError(
            f"schema must be {MOTION_POSE_PLAN_SCHEMA!r} or {MOTION_POSE_PLAN_SCHEMA_V1!r}",
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

    return (
        str(schema),
        motion_class,
        frame_w,
        frame_h,
        origin,
        base_specification_id,
        mapping,
        parsed_frames,
    )


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


def _opaque_column_loads(cells: list[list[Cell]]) -> list[int]:
    width = len(cells[0]) if cells else 0
    return [sum(1 for row in cells if row[x] is not None) for x in range(width)]


def _changed_cell_count(base: list[list[Cell]], target: list[list[Cell]]) -> int:
    return sum(
        1
        for y in range(len(base))
        for x in range(len(base[0]))
        if base[y][x] != target[y][x]
    )


def _embed_part_map_on_canvas(
    part_map: PartMap,
    *,
    origin: tuple[int, int],
    frame_size: tuple[int, int],
) -> PartMap:
    if part_map.frame_size == frame_size:
        return part_map
    ox, oy = origin
    embedded_parts: dict[str, Part] = {}
    for part_id, part in part_map.parts.items():
        embedded_parts[part_id] = Part(
            part_id=part.part_id,
            rigid=part.rigid,
            parent=part.parent,
            pivot=None
            if part.pivot is None
            else (part.pivot[0] + ox, part.pivot[1] + oy),
            grip=None
            if part.grip is None
            else (part.grip[0] + ox, part.grip[1] + oy),
            cells=frozenset((x + ox, y + oy) for x, y in part.cells),
            orientations=part.orientations,
        )
    return PartMap(
        schema=part_map.schema,
        base_raster_sha256=part_map.base_raster_sha256,
        frame_size=frame_size,
        parts=embedded_parts,
    )


def _mutable_parts_from_map(part_map: PartMap) -> dict[str, _MutablePart]:
    return {
        part_id: _MutablePart(
            part_id=part.part_id,
            rigid=part.rigid,
            parent=part.parent,
            pivot=part.pivot,
            grip=part.grip,
            cells=set(part.cells),
            orientations=part.orientations,
        )
        for part_id, part in part_map.parts.items()
    }


def _explicit_part_ids(operations: Sequence[Mapping[str, Any]]) -> set[str]:
    explicit: set[str] = set()
    for operation in operations:
        if operation.get("op") in _PART_OPS:
            part_id = operation.get("part_id")
            if isinstance(part_id, str):
                explicit.add(part_id)
    return explicit


def _descendants_in_parent_order(
    part_id: str,
    parts: Mapping[str, _MutablePart],
    *,
    explicit: set[str],
) -> list[str]:
    children = sorted(pid for pid, part in parts.items() if part.parent == part_id)
    ordered: list[str] = []
    for child in children:
        if child in explicit:
            continue
        ordered.append(child)
        ordered.extend(_descendants_in_parent_order(child, parts, explicit=explicit))
    return ordered


def _footprint_to_payload(footprint: Footprint) -> dict[str, Any]:
    return {
        "width": footprint.width,
        "height": footprint.height,
        "cells": {
            f"{x},{y}": [rgba[0], rgba[1], rgba[2]]
            for x, y, rgba in footprint.cells
        },
    }


def _part_map_document(
    parts: Mapping[str, _MutablePart],
    *,
    base_raster_sha256: str,
    frame_size: tuple[int, int],
) -> dict[str, Any]:
    payload_parts: dict[str, Any] = {}
    for part_id in sorted(parts):
        part = parts[part_id]
        entry: dict[str, Any] = {
            "rigid": part.rigid,
            "parent": part.parent,
            "cells": [f"{x},{y}" for x, y in sorted(part.cells)],
        }
        if part.pivot is not None:
            entry["pivot"] = [part.pivot[0], part.pivot[1]]
        if part.grip is not None:
            entry["grip"] = [part.grip[0], part.grip[1]]
        if part.rigid and part.orientations is not None:
            entry["orientations"] = {
                orientation_id: _footprint_to_payload(footprint)
                for orientation_id, footprint in part.orientations.items()
            }
        payload_parts[part_id] = entry
    return {
        "schema": "cell-part-map/0",
        "base_raster_sha256": base_raster_sha256,
        "frame_size": [frame_size[0], frame_size[1]],
        "parts": payload_parts,
    }


def _validate_part_map_coverage(frame: list[list[Cell]], part_map_doc: Mapping[str, Any]) -> None:
    opaque = {
        (x, y)
        for y, row in enumerate(frame)
        for x, cell in enumerate(row)
        if cell is not None
    }
    claimed: set[tuple[int, int]] = set()
    parts = part_map_doc.get("parts")
    if not isinstance(parts, Mapping):
        raise MotionAuthorError("part map missing parts", reason_code="authoring_boundary_violation")
    for part in parts.values():
        if not isinstance(part, Mapping):
            continue
        raw_cells = part.get("cells")
        if not isinstance(raw_cells, list):
            continue
        for key in raw_cells:
            if not isinstance(key, str) or "," not in key:
                continue
            x_text, y_text = key.split(",", 1)
            cell = (int(x_text), int(y_text))
            if cell in claimed:
                raise MotionAuthorError(
                    f"duplicate cell assignment at {cell[0]},{cell[1]}",
                    reason_code="authoring_boundary_violation",
                )
            claimed.add(cell)
    if claimed != opaque:
        raise MotionAuthorError(
            "posed part map does not cover every opaque cell exactly once",
            reason_code="authoring_boundary_violation",
        )


def _resolve_part_id(
    operation: Mapping[str, Any],
    *,
    parts: Mapping[str, _MutablePart],
    part_map_bound: bool,
) -> str:
    if not part_map_bound:
        raise MotionAuthorError(
            "part-addressed operation requires a bound part map",
            reason_code="part_map_unbound",
        )
    part_id = operation.get("part_id")
    if not isinstance(part_id, str) or not part_id:
        raise MotionAuthorError("part_id required", reason_code="authoring_boundary_violation")
    if part_id not in parts:
        raise MotionAuthorError(
            f"unknown part {part_id!r}",
            reason_code="unknown_part_id",
        )
    return part_id


def _footprint_origin(part_cells: set[tuple[int, int]], footprint: Footprint) -> tuple[int, int]:
    fp_min_x = min(x for x, _, _ in footprint.cells)
    fp_min_y = min(y for _, y, _ in footprint.cells)
    part_min_x = min(x for x, _ in part_cells)
    part_min_y = min(y for _, y in part_cells)
    return part_min_x - fp_min_x, part_min_y - fp_min_y


def _transform_local_point(
    x: int,
    y: int,
    *,
    width: int,
    height: int,
    orientation_id: str,
) -> tuple[int, int]:
    base_id, mirrored = orientation_id.split("+", 1) if "+" in orientation_id else (orientation_id, None)
    quarter_turns = {"rot0": 0, "rot90": 1, "rot180": 2, "rot270": 3}[base_id]
    rx, ry = x, y
    in_width, in_height = width, height
    for _ in range(quarter_turns):
        rx, ry = in_height - 1 - ry, rx
        in_width, in_height = in_height, in_width
    if mirrored == "mirror":
        rx = in_width - 1 - rx
    return rx, ry


def _world_cells_for_footprint(
    footprint: Footprint,
    origin: tuple[int, int],
) -> dict[tuple[int, int], tuple[int, int, int]]:
    ox, oy = origin
    return {(ox + x, oy + y): rgba for x, y, rgba in footprint.cells}


def _translate_part_cells(
    frame: list[list[Cell]],
    *,
    part_ids: Sequence[str],
    parts: dict[str, _MutablePart],
    dx: int,
    dy: int,
    frame_w: int,
    frame_h: int,
    locked: set[tuple[int, int]],
) -> None:
    moving_cells: set[tuple[int, int]] = set()
    for part_id in part_ids:
        moving_cells.update(parts[part_id].cells)

    extracted: dict[tuple[int, int], Cell] = {}
    for x, y in sorted(moving_cells):
        if (x, y) in locked:
            raise MotionAuthorError(
                f"cannot move locked cell at ({x}, {y})",
                reason_code="identity_lock_write",
            )
        extracted[(x, y)] = frame[y][x]
        frame[y][x] = None

    for (x, y), cell in extracted.items():
        nx, ny = x + dx, y + dy
        _assert_in_bounds(nx, ny, frame_w=frame_w, frame_h=frame_h)
        if (nx, ny) in locked:
            raise MotionAuthorError(
                f"cannot move into locked cell at ({nx}, {ny})",
                reason_code="identity_lock_write",
            )
        if frame[ny][nx] is not None and (nx, ny) not in moving_cells:
            raise MotionAuthorError(
                f"part translation collides at ({nx}, {ny})",
                reason_code="authoring_boundary_violation",
            )
        frame[ny][nx] = cell

    for part_id in part_ids:
        part = parts[part_id]
        part.cells = {(x + dx, y + dy) for x, y in part.cells}
        if part.pivot is not None:
            part.pivot = (part.pivot[0] + dx, part.pivot[1] + dy)
        if part.grip is not None:
            part.grip = (part.grip[0] + dx, part.grip[1] + dy)


def _orient_part_cells(
    frame: list[list[Cell]],
    *,
    part: _MutablePart,
    orientation_id: str,
    frame_w: int,
    frame_h: int,
    locked: set[tuple[int, int]],
) -> None:
    if not part.rigid:
        raise MotionAuthorError(
            f"part {part.part_id!r} cannot be rigidly reoriented",
            reason_code="non_rigid_part_orientation",
        )
    if part.orientations is None or orientation_id not in part.orientations:
        raise MotionAuthorError(
            f"unknown orientation {orientation_id!r} for part {part.part_id!r}",
            reason_code="authoring_boundary_violation",
        )
    if part.pivot is None:
        raise MotionAuthorError(
            f"part {part.part_id!r} missing pivot",
            reason_code="authoring_boundary_violation",
        )
    rot0 = part.orientations["rot0"]
    target = part.orientations[orientation_id]
    origin_rot0 = _footprint_origin(part.cells, rot0)
    pivot_local_rot0 = (part.pivot[0] - origin_rot0[0], part.pivot[1] - origin_rot0[1])
    pivot_local_target = _transform_local_point(
        pivot_local_rot0[0],
        pivot_local_rot0[1],
        width=rot0.width,
        height=rot0.height,
        orientation_id=orientation_id,
    )
    origin_target = (
        part.pivot[0] - pivot_local_target[0],
        part.pivot[1] - pivot_local_target[1],
    )
    target_world = _world_cells_for_footprint(target, origin_target)

    for x, y in sorted(part.cells):
        if (x, y) in locked:
            raise MotionAuthorError(
                f"cannot reorient locked cell at ({x}, {y})",
                reason_code="identity_lock_write",
            )
        frame[y][x] = None

    for (x, y), rgba in target_world.items():
        _assert_in_bounds(x, y, frame_w=frame_w, frame_h=frame_h)
        if (x, y) in locked:
            raise MotionAuthorError(
                f"cannot reorient into locked cell at ({x}, {y})",
                reason_code="identity_lock_write",
            )
        if frame[y][x] is not None and (x, y) not in part.cells:
            raise MotionAuthorError(
                f"part reorientation collides at ({x}, {y})",
                reason_code="authoring_boundary_violation",
            )
        frame[y][x] = rgba

    part.cells = set(target_world)


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
    parts: dict[str, _MutablePart] | None,
    explicit_parts: set[str],
    part_map_bound: bool,
) -> None:
    op = operation.get("op")
    if op == "translate_part":
        part_id = _resolve_part_id(operation, parts=parts or {}, part_map_bound=part_map_bound)
        dx = operation.get("dx")
        dy = operation.get("dy")
        if not isinstance(dx, int) or not isinstance(dy, int):
            raise MotionAuthorError(
                "translate_part requires integer dx and dy",
                reason_code="authoring_boundary_violation",
            )
        assert parts is not None
        move_ids = [part_id, *_descendants_in_parent_order(part_id, parts, explicit=explicit_parts)]
        _translate_part_cells(
            frame,
            part_ids=move_ids,
            parts=parts,
            dx=dx,
            dy=dy,
            frame_w=frame_w,
            frame_h=frame_h,
            locked=locked,
        )
        return

    if op == "orient_part":
        part_id = _resolve_part_id(operation, parts=parts or {}, part_map_bound=part_map_bound)
        orientation_id = operation.get("orientation")
        if not isinstance(orientation_id, str) or orientation_id not in ORIENTATION_IDS:
            raise MotionAuthorError(
                "orient_part requires a valid orientation id",
                reason_code="authoring_boundary_violation",
            )
        assert parts is not None
        _orient_part_cells(
            frame,
            part=parts[part_id],
            orientation_id=orientation_id,
            frame_w=frame_w,
            frame_h=frame_h,
            locked=locked,
        )
        return

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

    if op in _PART_OPS:
        raise MotionAuthorError(
            "part-addressed operation requires a bound part map",
            reason_code="part_map_unbound",
        )

    raise MotionAuthorError(f"unknown operation {op!r}", reason_code="authoring_boundary_violation")


def _validate_part_map_binding(
    pose_plan_schema: str,
    pose_plan: Mapping[str, Any],
    part_map: PartMap | None,
) -> None:
    if pose_plan_schema == MOTION_POSE_PLAN_SCHEMA_V1:
        digest = pose_plan.get("part_map_digest")
        if not isinstance(digest, str) or not digest:
            raise MotionAuthorError(
                "motion-pose-plan/1 requires part_map_digest",
                reason_code="authoring_boundary_violation",
            )
        if part_map is None:
            raise MotionAuthorError(
                "motion-pose-plan/1 requires a bound part map",
                reason_code="part_map_unbound",
            )
        if part_map.base_raster_sha256 != digest:
            raise MotionAuthorError(
                "bound part map digest does not match pose plan",
                reason_code="authoring_boundary_violation",
            )


def author_motion(
    base_frames: Sequence[list[list[Cell]]],
    pose_plan: Mapping[str, Any],
    identity_lock_spec: Mapping[str, Any],
    master_palette: MasterPalette,
    *,
    part_map: PartMap | None = None,
) -> AuthoredMotion:
    validate_identity_lock_spec(dict(identity_lock_spec))
    (
        pose_plan_schema,
        motion_class,
        frame_w,
        frame_h,
        origin,
        base_specification_id,
        base_frame_mapping,
        frame_operations,
    ) = _validate_pose_plan(pose_plan, identity_lock_spec=identity_lock_spec)
    _validate_part_map_binding(pose_plan_schema, pose_plan, part_map)

    embedded_part_map: PartMap | None = None
    if part_map is not None:
        embedded_part_map = _embed_part_map_on_canvas(
            part_map,
            origin=origin,
            frame_size=(frame_w, frame_h),
        )

    part_map_bound = embedded_part_map is not None
    locks = _parse_locks(identity_lock_spec, motion_class)
    lock_offsets = {lock_id: (0, 0) for lock_id in locks}
    for lock_id, lock in locks.items():
        if lock_offsets[lock_id] not in lock["offsets"]:
            lock_offsets[lock_id] = lock["offsets"][0]

    authored_frames: list[list[list[Cell]]] = []
    applied_lock_offsets: list[dict[str, list[int]]] = []
    frame_reports: list[dict[str, Any]] = []
    emitted_part_maps: list[dict[str, Any]] = []

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
        mutable_parts = (
            _mutable_parts_from_map(embedded_part_map) if embedded_part_map is not None else None
        )
        explicit_parts = _explicit_part_ids(operations)
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
                parts=mutable_parts,
                explicit_parts=explicit_parts,
                part_map_bound=part_map_bound,
            )
        lock_offsets.update(frame_lock_offsets)
        authored_frames.append(frame)
        applied_lock_offsets.append(
            {lock_id: [offset[0], offset[1]] for lock_id, offset in frame_lock_offsets.items()}
        )
        bbox = _alpha_bbox(frame)
        column_loads = _opaque_column_loads(frame)
        frame_reports.append(
            {
                "frame": frame_index,
                "opaque_bbox": {
                    "x0": bbox[0],
                    "y0": bbox[1],
                    "x1": bbox[2],
                    "y1": bbox[3],
                },
                "opaque_column_loads": column_loads,
                "changed_cell_count": _changed_cell_count(base_frame, frame),
                "lock_offsets": applied_lock_offsets[-1],
            }
        )
        if mutable_parts is not None and embedded_part_map is not None:
            part_map_doc = _part_map_document(
                mutable_parts,
                base_raster_sha256=embedded_part_map.base_raster_sha256,
                frame_size=(frame_w, frame_h),
            )
            _validate_part_map_coverage(frame, part_map_doc)
            emitted_part_maps.append(part_map_doc)

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
        "pose_plan_schema": pose_plan_schema,
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
        part_maps=tuple(emitted_part_maps) if emitted_part_maps else None,
    )
