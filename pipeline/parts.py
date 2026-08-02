"""Canonical dwarf Cell part map loader and review render (issues #295, #298)."""

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
    "REVIEW_SCALE",
    "_REVIEW_COLORS",
    "lattice_orientation",
    "load_part_map",
    "minimum_review_color_delta_e",
    "render_part_map",
    "review_tile_label",
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
REVIEW_SCALE = 12
_REVIEW_COLORS: dict[str, tuple[int, int, int, int]] = {
    "tool_head": (165, 8, 8, 255),
    "tool_handle": (204, 115, 10, 255),
    "helmet": (128, 140, 7, 255),
    "lamp": (12, 242, 18, 255),
    "head_face": (9, 192, 87, 255),
    "beard": (8, 165, 147, 255),
    "arm_near": (10, 160, 216, 255),
    "hand_near": (45, 11, 230, 255),
    "hand_far": (201, 227, 0, 255),
    "belt": (76, 6, 133, 255),
    "legs": (219, 10, 184, 255),
    "boots": (186, 9, 95, 255),
}
_LANDMARK_PART_IDS: dict[str, str] = {
    "lamp": "lamp",
    "eye": "head_face",
    "buckle": "belt",
}
_IDENTITY_LOCKS_PATH = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
_NEUTRAL_REVIEW_RGBA = (48, 48, 48, 255)
_REQUIRED_PART_IDS = frozenset(
    {
        "tool_head",
        "tool_handle",
        "helmet",
        "lamp",
        "head_face",
        "beard",
        "arm_near",
        "hand_near",
        "hand_far",
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


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def _four_connected_blobs(cells: frozenset[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    remaining = set(cells)
    blobs: list[set[tuple[int, int]]] = []
    while remaining:
        start = next(iter(remaining))
        stack = [start]
        blob: set[tuple[int, int]] = set()
        while stack:
            cell = stack.pop()
            if cell not in remaining or cell in blob:
                continue
            blob.add(cell)
            x, y = cell
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                stack.append((x + dx, y + dy))
        blobs.append(blob)
        remaining -= blob
    return blobs


def _load_identity_landmarks() -> dict[str, tuple[int, int]]:
    document = json.loads(_IDENTITY_LOCKS_PATH.read_text(encoding="utf-8"))
    motion_classes = document.get("motion_classes")
    if not isinstance(motion_classes, dict):
        raise PartMapError(
            "identity locks motion_classes must be an object",
            reason_code="invalid_identity_locks",
        )
    walk = motion_classes.get("walk")
    if not isinstance(walk, dict):
        raise PartMapError(
            "identity locks walk motion class is required",
            reason_code="invalid_identity_locks",
        )
    landmarks = walk.get("landmarks")
    if not isinstance(landmarks, list):
        raise PartMapError(
            "identity locks walk landmarks must be an array",
            reason_code="invalid_identity_locks",
        )
    parsed: dict[str, tuple[int, int]] = {}
    for row in landmarks:
        if not isinstance(row, dict):
            continue
        landmark_id = row.get("id")
        canonical = row.get("canonical")
        if not isinstance(landmark_id, str) or not isinstance(canonical, list) or len(canonical) != 2:
            continue
        x, y = canonical
        if isinstance(x, int) and isinstance(y, int):
            parsed[landmark_id] = (x, y)
    return parsed


def _validate_part_connectivity(parsed_parts: dict[str, Part]) -> None:
    for part_id, part in parsed_parts.items():
        blobs = _four_connected_blobs(part.cells)
        if len(blobs) > 1:
            raise PartMapError(
                f"part {part_id!r} must be one 4-connected component, found {len(blobs)}",
                reason_code="part_not_connected",
            )


def _validate_landmark_parts(parsed_parts: dict[str, Part]) -> None:
    landmarks = _load_identity_landmarks()
    cell_owner = {
        cell: part_id
        for part_id, part in parsed_parts.items()
        for cell in part.cells
    }
    for landmark_id, required_part_id in _LANDMARK_PART_IDS.items():
        cell = landmarks.get(landmark_id)
        if cell is None:
            raise PartMapError(
                f"identity lock landmark {landmark_id!r} is missing",
                reason_code="landmark_part_mismatch",
            )
        owner = cell_owner.get(cell)
        if owner != required_part_id:
            raise PartMapError(
                f"landmark {landmark_id!r} at {cell[0]},{cell[1]} must belong to {required_part_id!r}, found {owner!r}",
                reason_code="landmark_part_mismatch",
            )


def _validate_tool_carried(parsed_parts: dict[str, Part]) -> None:
    handle = parsed_parts["tool_handle"]
    parent_id = handle.parent
    if parent_id is None:
        raise PartMapError(
            "tool_handle must declare a parent part",
            reason_code="tool_not_carried",
        )
    parent = parsed_parts.get(parent_id)
    if parent is None:
        raise PartMapError(
            f"tool_handle parent {parent_id!r} is unknown",
            reason_code="tool_not_carried",
        )
    if not any(
        _chebyshev(handle_cell, parent_cell) <= 1
        for handle_cell in handle.cells
        for parent_cell in parent.cells
    ):
        raise PartMapError(
            f"tool_handle is not carried by parent {parent_id!r}",
            reason_code="tool_not_carried",
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
        if parent is not None and pivot is None:
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

    _validate_part_connectivity(parsed_parts)
    _validate_landmark_parts(parsed_parts)
    _validate_tool_carried(parsed_parts)

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


def _rgb_to_lab(r: int, g: int, b: int) -> tuple[float, float, float]:
    def pivot(channel: float) -> float:
        return ((channel + 0.055) / 1.055) ** 2.4 if channel > 0.04045 else channel / 12.92

    red, green, blue = (
        pivot(r / 255.0),
        pivot(g / 255.0),
        pivot(b / 255.0),
    )
    x = red * 0.4124 + green * 0.3576 + blue * 0.1805
    y = red * 0.2126 + green * 0.7152 + blue * 0.0722
    z = red * 0.0193 + green * 0.1192 + blue * 0.9505
    x /= 0.95047
    z /= 1.08883

    def f(channel: float) -> float:
        return channel ** (1 / 3) if channel > 0.008856 else (7.787 * channel) + (16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy) - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)


def _cie76_delta_e(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> float:
    lab_left = _rgb_to_lab(left[0], left[1], left[2])
    lab_right = _rgb_to_lab(right[0], right[1], right[2])
    return sum((a - b) ** 2 for a, b in zip(lab_left, lab_right)) ** 0.5


def minimum_review_color_delta_e() -> float:
    colors = list(_REVIEW_COLORS.values())
    return min(
        _cie76_delta_e(colors[index], colors[other])
        for index in range(len(colors))
        for other in range(index + 1, len(colors))
    )


def review_tile_label(part_id: str, part: Part) -> str:
    count = len(part.cells)
    if part.parent is None:
        return f"{part_id} (root) ({count})"
    return f"{part_id} \u2190 {part.parent} ({count})"


def _contrast_border_rgba(color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    luminance = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    if luminance < 128:
        return (255, 255, 255, 255)
    return (0, 0, 0, 255)


def render_part_map(part_map: PartMap, base_path: Path | str) -> "Image.Image":
    from PIL import Image, ImageDraw

    base_path = Path(base_path)
    base_cells = read_cells(base_path)
    width, height = part_map.frame_size
    color_lookup: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for part_id, part in part_map.parts.items():
        color = _REVIEW_COLORS[part_id]
        for cell in part.cells:
            color_lookup[cell] = color

    def frame_from_rgba(fill_lookup: Mapping[tuple[int, int], tuple[int, int, int, int]]) -> Image.Image:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pixels = image.load()
        for y, row in enumerate(base_cells):
            for x, cell in enumerate(row):
                if cell is None:
                    continue
                pixels[x, y] = fill_lookup.get((x, y), (*cell, 255))
        return image

    base_native = frame_from_rgba({})
    base_scaled = base_native.resize(
        (width * REVIEW_SCALE, height * REVIEW_SCALE),
        Image.NEAREST,
    )
    overlay_scaled = frame_from_rgba(color_lookup).resize(
        (width * REVIEW_SCALE, height * REVIEW_SCALE),
        Image.NEAREST,
    )

    part_ids = sorted(part_map.parts)
    tile_w = width * REVIEW_SCALE
    tile_h = height * REVIEW_SCALE
    label_h = 16
    tiles_per_row = 4
    tile_rows = (len(part_ids) + tiles_per_row - 1) // tiles_per_row
    part_grid_h = tile_rows * (tile_h + label_h + 4)
    panel1_h = height + 4 + height * REVIEW_SCALE
    panel2_h = height * REVIEW_SCALE + 8
    total_h = 8 + panel1_h + 8 + panel2_h + 8 + part_grid_h + 8
    total_w = max(
        width + 4 + width * REVIEW_SCALE,
        overlay_scaled.width,
        tiles_per_row * tile_w + (tiles_per_row - 1) * 4,
    )
    sheet = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    font = None

    y = 4
    sheet.paste(base_native, (0, y))
    sheet.paste(base_scaled, (width + 4, y))
    y += panel1_h + 8
    sheet.paste(overlay_scaled, (0, y))
    y += panel2_h + 8

    for index, part_id in enumerate(part_ids):
        row = index // tiles_per_row
        col = index % tiles_per_row
        x = col * (tile_w + 4)
        tile_y = y + row * (tile_h + label_h + 4)
        part = part_map.parts[part_id]
        part_color = _REVIEW_COLORS[part_id]
        border_color = _contrast_border_rgba(part_color)
        border_cells: set[tuple[int, int]] = set()
        for cell_x, cell_y in part.cells:
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                neighbor = (cell_x + dx, cell_y + dy)
                if neighbor not in part.cells and base_cells[cell_y][cell_x] is not None:
                    border_cells.add(neighbor)
        tile_lookup: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        for cell_y, row_cells in enumerate(base_cells):
            for cell_x, cell in enumerate(row_cells):
                if cell is None:
                    continue
                coord = (cell_x, cell_y)
                if coord in part.cells:
                    tile_lookup[coord] = part_color
                elif coord in border_cells:
                    tile_lookup[coord] = border_color
                else:
                    tile_lookup[coord] = _NEUTRAL_REVIEW_RGBA
        tile = frame_from_rgba(tile_lookup).resize((tile_w, tile_h), Image.NEAREST)
        sheet.paste(tile, (x, tile_y))
        label = review_tile_label(part_id, part)
        draw.text((x, tile_y + tile_h + 2), label, fill=(220, 220, 220, 255), font=font)

    return sheet
