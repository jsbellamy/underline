"""Pure re-canvas, mask, and measurement logic for the swing action canvas spike."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from pipeline.cell_raster import Cell, read_cells
from pipeline.identity_lock import _load_palette_roles, nearest_palette_role
from pipeline.strip import StripLayout
from PIL import Image

CellGrid = list[list[Cell]]
BoolMask = list[list[bool]]

SOURCE_FRAME_W = StripLayout().frame_w
SOURCE_FRAME_H = StripLayout().frame_h
TOOL_ROLES = frozenset({"blue-metal", "earth-leather-beard"})
GRIP_NEIGHBOR_ROLES = frozenset({"skin", "green-cloth"})

BASELINE_MOTIONS = ("walk", "idle", "swing")
VARIANTS = ("24x24", "32x24", "overlay")
ADJACENT_PAIRS = ((0, 1), (1, 2), (2, 3), (3, 0))


@dataclass(frozen=True)
class AlphaBbox:
    x0: int
    x1: int
    y0: int
    y1: int

    def format(self) -> str:
        return f"x{self.x0}-{self.x1} y{self.y0}-{self.y1}"


@dataclass(frozen=True)
class FrameMeasurements:
    alpha_bbox: AlphaBbox
    occupancy: float
    boundary_left: int
    boundary_right: int
    boundary_top: int
    boundary_bottom: int

    def as_dict(self) -> dict[str, object]:
        return {
            "alpha_bbox": self.alpha_bbox.format(),
            "occupancy": round(self.occupancy, 3),
            "boundary_columns": {
                "left": self.boundary_left,
                "right": self.boundary_right,
            },
            "boundary_rows": {
                "top": self.boundary_top,
                "bottom": self.boundary_bottom,
            },
        }


def load_palette_entries(
    palette_path: Path,
) -> list[tuple[str, tuple[int, int, int]]]:
    _, entries = _load_palette_roles(palette_path)
    return list(entries)


def cell_role(
    cell: Cell,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> str | None:
    if cell is None:
        return None
    return nearest_palette_role(cell, palette_entries)


def role_grid(
    cells: CellGrid,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> list[list[str | None]]:
    return [
        [cell_role(cell, palette_entries) for cell in row]
        for row in cells
    ]


def alpha_bbox(cells: CellGrid) -> AlphaBbox | None:
    opaque = [
        (x, y)
        for y, row in enumerate(cells)
        for x, cell in enumerate(row)
        if cell is not None
    ]
    if not opaque:
        return None
    xs = [point[0] for point in opaque]
    ys = [point[1] for point in opaque]
    return AlphaBbox(min(xs), max(xs), min(ys), max(ys))


def occupancy(cells: CellGrid) -> float:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    if width == 0 or height == 0:
        return 0.0
    opaque = sum(1 for row in cells for cell in row if cell is not None)
    return opaque / (width * height)


def boundary_counts(cells: CellGrid) -> tuple[int, int, int, int]:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    left = sum(1 for row in cells if row[0] is not None)
    right = sum(1 for row in cells if row[width - 1] is not None)
    top = sum(1 for x in range(width) if cells[0][x] is not None)
    bottom = sum(1 for x in range(width) if cells[height - 1][x] is not None)
    return left, right, top, bottom


def measure_frame(cells: CellGrid) -> FrameMeasurements:
    bbox = alpha_bbox(cells)
    if bbox is None:
        raise ValueError("cannot measure an empty frame")
    left, right, top, bottom = boundary_counts(cells)
    return FrameMeasurements(
        alpha_bbox=bbox,
        occupancy=occupancy(cells),
        boundary_left=left,
        boundary_right=right,
        boundary_top=top,
        boundary_bottom=bottom,
    )


def static_silhouette_fraction(a: CellGrid, b: CellGrid) -> float:
    if len(a) != len(b) or not a or len(a[0]) != len(b[0]):
        raise ValueError("frames must share dimensions")
    height = len(a)
    width = len(a[0])
    total = width * height
    if total == 0:
        return 1.0
    changed = 0
    for y in range(height):
        for x in range(width):
            occupied_a = a[y][x] is not None
            occupied_b = b[y][x] is not None
            if occupied_a != occupied_b:
                changed += 1
    return 1.0 - (changed / total)


def adjacent_silhouette_fractions(
    frames: Sequence[CellGrid],
) -> dict[str, float]:
    labels = ("0-1", "1-2", "2-3", "3-0")
    return {
        label: round(static_silhouette_fraction(frames[a], frames[b]), 4)
        for label, (a, b) in zip(labels, ADJACENT_PAIRS, strict=True)
    }


def empty_grid(width: int, height: int) -> CellGrid:
    return [[None for _ in range(width)] for _ in range(height)]


def blit_cells(
    target: CellGrid,
    source: CellGrid,
    *,
    offset_x: int,
    offset_y: int,
) -> None:
    for y, row in enumerate(source):
        for x, cell in enumerate(row):
            if cell is None:
                continue
            target_y = offset_y + y
            target_x = offset_x + x
            if 0 <= target_y < len(target) and 0 <= target_x < len(target[0]):
                target[target_y][target_x] = cell


def expand_canvas(
    cells: CellGrid,
    *,
    canvas_w: int,
    canvas_h: int,
    left_pad: int,
) -> CellGrid:
    if len(cells) != canvas_h:
        raise ValueError("expanded canvas height must match source frame height")
    if left_pad + SOURCE_FRAME_W > canvas_w:
        raise ValueError("canvas is too narrow for the requested padding")
    target = empty_grid(canvas_w, canvas_h)
    blit_cells(target, cells, offset_x=left_pad, offset_y=0)
    return target


def grip_seeds(
    roles: list[list[str | None]],
) -> list[tuple[int, int]]:
    height = len(roles)
    width = len(roles[0]) if roles else 0
    seeds: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            if roles[y][x] != "earth-leather-beard":
                continue
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx = x + dx
                ny = y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    if roles[ny][nx] in GRIP_NEIGHBOR_ROLES:
                        seeds.append((x, y))
                        break
    return seeds


def flood_tool_mask(
    roles: list[list[str | None]],
    seeds: Iterable[tuple[int, int]],
) -> BoolMask:
    height = len(roles)
    width = len(roles[0]) if roles else 0
    mask = [[False for _ in range(width)] for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()
    for seed in seeds:
        x, y = seed
        if roles[y][x] not in TOOL_ROLES:
            continue
        if mask[y][x]:
            continue
        mask[y][x] = True
        queue.append((x, y))
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx = x + dx
            ny = y + dy
            if not (0 <= nx < width and 0 <= ny < height):
                continue
            if mask[ny][nx]:
                continue
            if roles[ny][nx] not in TOOL_ROLES:
                continue
            mask[ny][nx] = True
            queue.append((nx, ny))
    return mask


def separation_mask(
    cells: CellGrid,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> dict[str, object]:
    roles = role_grid(cells, palette_entries)
    seeds = grip_seeds(roles)
    if not seeds:
        return {
            "status": "failed",
            "reason": "no grip seed found",
            "attachment_cell": None,
            "tool_cells": [],
        }
    tool_mask = flood_tool_mask(roles, seeds)
    tool_cells = [
        [mask_row[x] for x in range(len(mask_row))]
        for mask_row in tool_mask
    ]
    attachment = min(seeds)
    return {
        "status": "ok",
        "attachment_cell": list(attachment),
        "tool_cells": tool_cells,
    }


def split_overlay_layers(
    cells: CellGrid,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> tuple[CellGrid, CellGrid, dict[str, object]]:
    separation = separation_mask(cells, palette_entries)
    body = empty_grid(SOURCE_FRAME_W, SOURCE_FRAME_H)
    tool = empty_grid(SOURCE_FRAME_W, SOURCE_FRAME_H)
    if separation["status"] != "ok":
        blit_cells(body, cells, offset_x=0, offset_y=0)
        return body, tool, separation
    tool_mask = separation["tool_cells"]
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is None:
                continue
            if tool_mask[y][x]:
                tool[y][x] = cell
            else:
                body[y][x] = cell
    return body, tool, separation


def composite_overlay(
    body: CellGrid,
    tool: CellGrid,
    *,
    canvas_w: int = 24,
    canvas_h: int = 24,
    left_pad: int = 4,
) -> CellGrid:
    composite = empty_grid(canvas_w, canvas_h)
    blit_cells(composite, body, offset_x=left_pad, offset_y=0)
    blit_cells(composite, tool, offset_x=left_pad, offset_y=0)
    return composite


def overlay_body_cells_preserved(
    body: CellGrid,
    reference: CellGrid,
    tool_mask: list[list[bool]],
) -> bool:
    for y, row in enumerate(reference):
        for x, cell in enumerate(row):
            if cell is None:
                continue
            if tool_mask[y][x]:
                continue
            if body[y][x] != cell:
                return False
    return True


def render_variant_frames(
    source_frames: Sequence[CellGrid],
    variant: str,
    palette_entries: Sequence[tuple[str, tuple[int, int, int]]],
) -> tuple[list[CellGrid], list[dict[str, object]], list[bool]]:
    if variant == "24x24":
        return (
            [
                expand_canvas(frame, canvas_w=24, canvas_h=24, left_pad=4)
                for frame in source_frames
            ],
            [],
            [],
        )
    if variant == "32x24":
        return (
            [
                expand_canvas(frame, canvas_w=32, canvas_h=24, left_pad=8)
                for frame in source_frames
            ],
            [],
            [],
        )
    if variant == "overlay":
        rendered: list[CellGrid] = []
        separations: list[dict[str, object]] = []
        body_identity: list[bool] = []
        for frame in source_frames:
            body, tool, separation = split_overlay_layers(frame, palette_entries)
            rendered.append(
                composite_overlay(body, tool, canvas_w=24, canvas_h=24, left_pad=4)
            )
            separations.append(separation)
            tool_mask = separation.get("tool_cells")
            if separation["status"] != "ok" or tool_mask is None:
                body_identity.append(False)
            else:
                body_identity.append(
                    overlay_body_cells_preserved(body, frame, tool_mask)
                )
        return rendered, separations, body_identity
    raise ValueError(f"unknown variant: {variant}")


def load_motion_frames(
    assets_root: Path,
    motion: str,
) -> list[CellGrid]:
    bundle = assets_root / "first-room" / "dwarf" / motion / "polished"
    return [
        read_cells(bundle / f"frame-{index}.png")
        for index in range(StripLayout().frame_count)
    ]


def measure_motion_baseline(
    frames: Sequence[CellGrid],
) -> dict[str, object]:
    measured = [measure_frame(frame) for frame in frames]
    per_frame = [frame.as_dict() for frame in measured]
    edge_left = [frame.boundary_left for frame in measured]
    edge_right = [frame.boundary_right for frame in measured]
    return {
        "per_frame": per_frame,
        "edge_load": {
            "left": edge_left,
            "right": edge_right,
        },
        "static_silhouette_fraction": adjacent_silhouette_fractions(frames),
    }


def measure_variant(
    frames: Sequence[CellGrid],
    *,
    separations: Sequence[dict[str, object]] | None = None,
) -> dict[str, object]:
    measured = {
        "per_frame": [measure_frame(frame).as_dict() for frame in frames],
        "static_silhouette_fraction": adjacent_silhouette_fractions(frames),
    }
    if separations is not None:
        measured["separation"] = list(separations)
    return measured


def cells_to_rgba(cells: CellGrid) -> Image.Image:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                pixels[x, y] = (*cell, 255)
    return image


def silhouette_render(cells: CellGrid) -> Image.Image:
    return cells_to_rgba(
        [
            [(0, 0, 0) if cell is None else (255, 255, 255) for cell in row]
            for row in cells
        ]
    )
