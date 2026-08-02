"""Canonical dwarf Cell part map loader (issue #295)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pipeline.cell_raster import read_cells
from pipeline.gate_evidence import sha256_file

__all__ = [
    "ORIENTATION_IDS",
    "Footprint",
    "Part",
    "PartMap",
    "PartMapError",
    "lattice_orientation",
    "load_part_map",
]

SCHEMA = "cell-part-map/0"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
ORIENTATION_IDS = (
    "rot0",
    "rot0+mirror",
    "rot90",
    "rot90+mirror",
    "rot180",
    "rot180+mirror",
    "rot270",
    "rot270+mirror",
)
_REQUIRED_PART_IDS = frozenset(
    {
        "tool_head",
        "tool_handle",
        "helmet",
        "lamp",
        "head_face",
        "beard",
        "torso",
        "arm_near",
        "hand_near",
        "belt",
        "legs",
        "boots",
    }
)


class PartMapError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class Footprint:
    width: int
    height: int
    cells: tuple[tuple[int, int, tuple[int, int, int]], ...]


@dataclass(frozen=True)
class Part:
    part_id: str
    rigid: bool
    parent: str | None
    pivot: tuple[int, int] | None
    grip: tuple[int, int] | None
    cells: frozenset[tuple[int, int]]
    orientations: dict[str, Footprint] | None


@dataclass(frozen=True)
class PartMap:
    schema: str
    base_raster_sha256: str
    frame_size: tuple[int, int]
    parts: dict[str, Part]


def _parse_cell_key(key: object, *, where: str) -> tuple[int, int]:
    if not isinstance(key, str) or "," not in key:
        raise PartMapError(
            f"invalid cell key at {where}",
            reason_code="invalid_part_map_cell",
        )
    x_text, y_text = key.split(",", 1)
    try:
        return int(x_text), int(y_text)
    except ValueError as exc:
        raise PartMapError(
            f"invalid cell key at {where}",
            reason_code="invalid_part_map_cell",
        ) from exc


def _parse_anchor_cell(value: object, *, where: str) -> tuple[int, int]:
    if isinstance(value, list) and len(value) == 2:
        x, y = value
        if isinstance(x, int) and isinstance(y, int):
            return x, y
    raise PartMapError(
        f"invalid anchor cell at {where}",
        reason_code="invalid_part_map_anchor",
    )


def _footprint_from_payload(payload: Mapping[str, Any], *, where: str) -> Footprint:
    width = payload.get("width")
    height = payload.get("height")
    raw_cells = payload.get("cells")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        raise PartMapError(
            f"invalid footprint size at {where}",
            reason_code="invalid_part_map_orientation",
        )
    if not isinstance(raw_cells, Mapping):
        raise PartMapError(
            f"invalid footprint cells at {where}",
            reason_code="invalid_part_map_orientation",
        )
    cells: list[tuple[int, int, tuple[int, int, int]]] = []
    for key, rgba in raw_cells.items():
        x, y = _parse_cell_key(key, where=f"{where}.cells[{key!r}]")
        if not (0 <= x < width and 0 <= y < height):
            raise PartMapError(
                f"footprint cell out of bounds at {where}",
                reason_code="invalid_part_map_orientation",
            )
        if not isinstance(rgba, list) or len(rgba) != 3 or not all(isinstance(channel, int) for channel in rgba):
            raise PartMapError(
                f"invalid rgba at {where}.cells[{key!r}]",
                reason_code="invalid_part_map_orientation",
            )
        cells.append((x, y, (rgba[0], rgba[1], rgba[2])))
    cells.sort()
    return Footprint(width=width, height=height, cells=tuple(cells))


def _footprint_to_payload(footprint: Footprint) -> dict[str, Any]:
    return {
        "width": footprint.width,
        "height": footprint.height,
        "cells": {
            f"{x},{y}": [rgba[0], rgba[1], rgba[2]]
            for x, y, rgba in footprint.cells
        },
    }


def _opaque_cells_from_frame(
    cells: list[list[tuple[int, int, int] | None]],
    frame_size: tuple[int, int],
) -> set[tuple[int, int]]:
    width, height = frame_size
    if len(cells[0]) != width or len(cells) != height:
        raise PartMapError(
            "base raster dimensions do not match frame_size",
            reason_code="invalid_part_map_base",
        )
    return {
        (x, y)
        for y in range(height)
        for x in range(width)
        if cells[y][x] is not None
    }


def _rotate_footprint(footprint: Footprint, quarter_turns: int) -> Footprint:
    quarter_turns %= 4
    if quarter_turns == 0:
        return footprint
    in_width = footprint.width
    in_height = footprint.height
    out_width, out_height = in_width, in_height
    for _ in range(quarter_turns):
        out_width, out_height = out_height, out_width
    rotated: list[tuple[int, int, tuple[int, int, int]]] = []
    for x, y, rgba in footprint.cells:
        rx, ry = x, y
        width, height = in_width, in_height
        for _ in range(quarter_turns):
            rx, ry = height - 1 - ry, rx
            width, height = height, width
        rotated.append((rx, ry, rgba))
    return Footprint(width=out_width, height=out_height, cells=tuple(sorted(rotated)))


def _mirror_footprint(footprint: Footprint) -> Footprint:
    mirrored = tuple(
        (footprint.width - 1 - x, y, rgba) for x, y, rgba in footprint.cells
    )
    return Footprint(
        width=footprint.width,
        height=footprint.height,
        cells=tuple(sorted(mirrored)),
    )


def lattice_orientation(footprint: Footprint, orientation_id: str) -> Footprint:
    if orientation_id not in ORIENTATION_IDS:
        raise PartMapError(
            f"unknown orientation id: {orientation_id!r}",
            reason_code="invalid_part_map_orientation",
        )
    base_id, mirrored = orientation_id.split("+", 1) if "+" in orientation_id else (orientation_id, None)
    quarter_turns = {"rot0": 0, "rot90": 1, "rot180": 2, "rot270": 3}[base_id]
    oriented = _rotate_footprint(footprint, quarter_turns)
    if mirrored == "mirror":
        oriented = _mirror_footprint(oriented)
    return oriented


def _footprint_from_part_cells(
    cells: frozenset[tuple[int, int]],
    rgba_lookup: Mapping[tuple[int, int], tuple[int, int, int]],
) -> Footprint:
    if not cells:
        raise PartMapError(
            "cannot build an empty rigid footprint",
            reason_code="invalid_part_map_orientation",
        )
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    min_x, min_y = min(xs), min(ys)
    max_x, max_y = max(xs), max(ys)
    normalized = tuple(
        sorted(
            (x - min_x, y - min_y, rgba_lookup[(x, y)])
            for x, y in cells
        )
    )
    return Footprint(
        width=max_x - min_x + 1,
        height=max_y - min_y + 1,
        cells=normalized,
    )


def load_part_map(path: Path | str) -> PartMap:
    document_path = Path(path)
    document = json.loads(document_path.read_text(encoding="utf-8"))
    schema = document.get("schema")
    if schema != SCHEMA:
        raise PartMapError(
            f"unknown cell part map schema: {schema!r}",
            reason_code="invalid_part_map_schema",
        )

    digest = document.get("base_raster_sha256")
    if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
        raise PartMapError(
            "base_raster_sha256 must be a sha-256 hex digest",
            reason_code="invalid_part_map_digest",
        )

    frame_size_raw = document.get("frame_size")
    if (
        not isinstance(frame_size_raw, list)
        or len(frame_size_raw) != 2
        or not all(isinstance(value, int) for value in frame_size_raw)
    ):
        raise PartMapError(
            "frame_size must be a two-element integer list",
            reason_code="invalid_part_map_frame_size",
        )
    frame_size = (frame_size_raw[0], frame_size_raw[1])

    base_relative = document.get("base_raster_relative_path")
    if not isinstance(base_relative, str):
        raise PartMapError(
            "base_raster_relative_path must be a string",
            reason_code="invalid_part_map_base",
        )
    base_path = _REPO_ROOT / base_relative
    if sha256_file(base_path) != digest:
        raise PartMapError(
            "base raster digest does not match document",
            reason_code="base_raster_digest_mismatch",
        )

    base_cells = read_cells(base_path)
    rgba_lookup: dict[tuple[int, int], tuple[int, int, int]] = {}
    for y, row in enumerate(base_cells):
        for x, cell in enumerate(row):
            if cell is not None:
                rgba_lookup[(x, y)] = cell
    opaque_cells = _opaque_cells_from_frame(base_cells, frame_size)

    raw_parts = document.get("parts")
    if not isinstance(raw_parts, Mapping):
        raise PartMapError(
            "parts must be an object",
            reason_code="invalid_part_map_parts",
        )

    missing = _REQUIRED_PART_IDS - set(raw_parts)
    if missing:
        raise PartMapError(
            f"missing required part ids: {sorted(missing)}",
            reason_code="missing_required_part",
        )

    parsed_parts: dict[str, Part] = {}
    claimed: dict[tuple[int, int], str] = {}

    for part_id, payload in raw_parts.items():
        if not isinstance(payload, Mapping):
            raise PartMapError(
                f"part {part_id!r} must be an object",
                reason_code="invalid_part_map_parts",
            )
        rigid = payload.get("rigid")
        if not isinstance(rigid, bool):
            raise PartMapError(
                f"part {part_id!r} rigid must be a boolean",
                reason_code="invalid_part_map_parts",
            )
        parent = payload.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise PartMapError(
                f"part {part_id!r} parent must be a string or null",
                reason_code="invalid_part_map_parent",
            )
        pivot_raw = payload.get("pivot")
        pivot = None if pivot_raw is None else _parse_anchor_cell(
            pivot_raw,
            where=f"parts.{part_id}.pivot",
        )
        if parent is None:
            if pivot is not None:
                raise PartMapError(
                    f"part {part_id!r} root cannot declare a pivot",
                    reason_code="invalid_part_map_parent",
                )
        elif pivot is None:
            raise PartMapError(
                f"part {part_id!r} must declare a pivot",
                reason_code="invalid_part_map_parent",
            )

        grip_raw = payload.get("grip")
        grip = None if grip_raw is None else _parse_anchor_cell(
            grip_raw,
            where=f"parts.{part_id}.grip",
        )

        raw_cell_list = payload.get("cells")
        if not isinstance(raw_cell_list, list):
            raise PartMapError(
                f"part {part_id!r} cells must be a list",
                reason_code="invalid_part_map_cell",
            )
        part_cells: set[tuple[int, int]] = set()
        for index, key in enumerate(raw_cell_list):
            cell = _parse_cell_key(key, where=f"parts.{part_id}.cells[{index}]")
            if cell in claimed:
                raise PartMapError(
                    f"duplicate cell assignment at {cell[0]},{cell[1]}",
                    reason_code="duplicate_cell_assignment",
                )
            if cell not in opaque_cells:
                raise PartMapError(
                    f"cell {cell[0]},{cell[1]} is not opaque in the base raster",
                    reason_code="invalid_part_map_cell",
                )
            claimed[cell] = part_id
            part_cells.add(cell)

        orientations: dict[str, Footprint] | None = None
        if rigid:
            raw_orientations = payload.get("orientations")
            if not isinstance(raw_orientations, Mapping):
                raise PartMapError(
                    f"rigid part {part_id!r} must declare orientations",
                    reason_code="invalid_part_map_orientation",
                )
            missing_orientations = set(ORIENTATION_IDS) - set(raw_orientations)
            if missing_orientations:
                raise PartMapError(
                    f"rigid part {part_id!r} is missing orientations: {sorted(missing_orientations)}",
                    reason_code="invalid_part_map_orientation",
                )
            rot0 = _footprint_from_payload(
                raw_orientations["rot0"],
                where=f"parts.{part_id}.orientations.rot0",
            )
            orientations = {}
            for orientation_id in ORIENTATION_IDS:
                footprint = _footprint_from_payload(
                    raw_orientations[orientation_id],
                    where=f"parts.{part_id}.orientations.{orientation_id}",
                )
                expected = lattice_orientation(rot0, orientation_id)
                if footprint != expected:
                    raise PartMapError(
                        f"orientation {orientation_id!r} does not match lattice transform for part {part_id!r}",
                        reason_code="invalid_part_map_orientation",
                    )
                orientations[orientation_id] = footprint
        elif payload.get("orientations") is not None:
            raise PartMapError(
                f"non-rigid part {part_id!r} cannot declare orientations",
                reason_code="invalid_part_map_orientation",
            )

        parsed_parts[part_id] = Part(
            part_id=part_id,
            rigid=rigid,
            parent=parent,
            pivot=pivot,
            grip=grip,
            cells=frozenset(part_cells),
            orientations=orientations,
        )

    for part_id, part in parsed_parts.items():
        if part.parent is not None and part.parent not in parsed_parts:
            raise PartMapError(
                f"part {part_id!r} parent {part.parent!r} is unknown",
                reason_code="unknown_parent",
            )

    unassigned = opaque_cells - set(claimed)
    if unassigned:
        sample = sorted(unassigned)[:3]
        raise PartMapError(
            f"unassigned opaque cells remain, e.g. {sample}",
            reason_code="unassigned_opaque_cell",
        )

    return PartMap(
        schema=SCHEMA,
        base_raster_sha256=digest,
        frame_size=frame_size,
        parts=parsed_parts,
    )


def build_rigid_orientations(
    cells: frozenset[tuple[int, int]],
    rgba_lookup: Mapping[tuple[int, int], tuple[int, int, int]],
) -> dict[str, dict[str, Any]]:
    rot0 = _footprint_from_part_cells(cells, rgba_lookup)
    return {
        orientation_id: _footprint_to_payload(lattice_orientation(rot0, orientation_id))
        for orientation_id in ORIENTATION_IDS
    }
