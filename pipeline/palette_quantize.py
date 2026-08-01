"""Role-segmented Master Palette quantization for off-palette rasters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from pipeline.cell_raster import cells_from_rgba
from pipeline.identity_lock import nearest_palette_role
from pipeline.strip import Cell

__all__ = [
    "MasterPalette",
    "PaletteQuantizeError",
    "load_master_palette",
    "propose_seed_role_map",
    "quantize_cells",
    "relative_luminance",
]

RoleAssignment = Mapping[tuple[int, int], str]


class PaletteQuantizeError(ValueError):
    """Fail-closed Master Palette quantization error."""


@dataclass(frozen=True)
class MasterPalette:
    role_ids: tuple[str, ...]
    role_colors: dict[str, tuple[tuple[int, int, int], ...]]
    entries: tuple[tuple[str, tuple[int, int, int]], ...]


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _parse_hex_color(value: object, *, where: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise PaletteQuantizeError(f"invalid color at {where}")
    try:
        return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
    except ValueError as exc:
        raise PaletteQuantizeError(f"invalid color at {where}") from exc


def load_master_palette(path: Path) -> MasterPalette:
    if not path.is_file():
        raise PaletteQuantizeError(f"missing master palette: {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PaletteQuantizeError(f"invalid master palette JSON: {path}") from exc
    groups = doc.get("role_groups") if isinstance(doc, dict) else None
    if not isinstance(groups, list) or not groups:
        raise PaletteQuantizeError("master palette requires non-empty role_groups")
    role_ids: list[str] = []
    role_colors: dict[str, tuple[tuple[int, int, int], ...]] = {}
    entries: list[tuple[str, tuple[int, int, int]]] = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise PaletteQuantizeError("master palette role group must be an object")
        role_id = group.get("id")
        colors = group.get("colors")
        if not isinstance(role_id, str) or not role_id:
            raise PaletteQuantizeError("master palette role group requires id")
        if role_id in role_ids:
            raise PaletteQuantizeError(f"duplicate master palette role {role_id!r}")
        if not isinstance(colors, list) or not colors:
            raise PaletteQuantizeError(f"master palette role {role_id!r} requires colors")
        parsed_colors = tuple(
            _parse_hex_color(color, where=f"role_groups[{index}].colors")
            for color in colors
        )
        role_ids.append(role_id)
        role_colors[role_id] = parsed_colors
        for color in parsed_colors:
            entries.append((role_id, color))
    return MasterPalette(
        role_ids=tuple(role_ids),
        role_colors=role_colors,
        entries=tuple(entries),
    )


def propose_seed_role_map(
    cells: list[list[Cell]],
    palette: MasterPalette,
) -> dict[tuple[int, int], str]:
    """Propose a per-Cell role assignment from global nearest-role.

    The output is a starting point for human correction — never treat it as the
    committed assignment.
    """
    assignment: dict[tuple[int, int], str] = {}
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is None:
                continue
            role = nearest_palette_role(cell, palette.entries)
            if role is None:
                raise PaletteQuantizeError(f"no palette role for opaque cell at ({x}, {y})")
            assignment[(x, y)] = role
    return assignment


def nearest_color_in_role(
    cell: Cell,
    role_id: str,
    palette: MasterPalette,
) -> tuple[int, int, int]:
    """Map an opaque Cell to the nearest palette colour within its material role.

    When two role colours are equidistant, the darker colour (lower relative
    luminance) wins so repeated quantization is idempotent.
    """
    if cell is None:
        raise PaletteQuantizeError("nearest_color_in_role requires an opaque Cell")
    if role_id not in palette.role_colors:
        raise PaletteQuantizeError(f"unknown palette role {role_id!r}")
    return min(
        palette.role_colors[role_id],
        key=lambda color: (
            sum((cell[channel] - color[channel]) ** 2 for channel in range(3)),
            relative_luminance(color),
        ),
    )


def quantize_cells(
    cells: list[list[Cell]],
    palette: MasterPalette,
    role_assignment: RoleAssignment,
) -> list[list[Cell]]:
    """Quantize opaque Cells onto the Master Palette within assigned roles."""
    height = len(cells)
    width = len(cells[0]) if cells else 0
    quantized: list[list[Cell]] = []
    for y, row in enumerate(cells):
        out_row: list[Cell] = []
        for x, cell in enumerate(row):
            if cell is None:
                out_row.append(None)
                continue
            role = role_assignment.get((x, y))
            if role is None:
                raise PaletteQuantizeError(
                    f"missing role assignment for opaque cell at ({x}, {y})"
                )
            out_row.append(nearest_color_in_role(cell, role, palette))
        quantized.append(out_row)
    if height and any(len(row) != width for row in quantized):
        raise PaletteQuantizeError("quantized grid width mismatch")
    return quantized


def quantize_rgba_image(
    image,
    palette: MasterPalette,
    role_assignment: RoleAssignment,
):
    """Quantize a PIL RGBA image via ``quantize_cells``."""
    return quantize_cells(cells_from_rgba(image), palette, role_assignment)
