"""Behavioral proof for pipeline.palette_quantize (issue #172).

The quantizer is characterized against the soft-shaded raster it was written for:
the pre-migration dwarf identity, retired from the canonical path by #179 and
preserved byte-for-byte as the idle draft Frame 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.cell_raster import read_cells
from pipeline.identity_lock import nearest_palette_role
from pipeline.palette_quantize import (
    MasterPalette,
    load_master_palette,
    nearest_color_in_role,
    propose_seed_role_map,
    quantize_cells,
    relative_luminance,
)

ROOT = Path(__file__).resolve().parents[1]
SOFT_SHADED_IDENTITY_PNG = (
    ROOT / "assets" / "first-room" / "dwarf" / "idle" / "draft" / "frame-0.png"
)
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
BEARD_CHEST_RECT = {"x0": 10, "x1": 13, "y0": 6, "y1": 14}
GLOBAL_AMBER_EMISSION_COUNT = 40
OPAQUE_IDENTITY_CELL_COUNT = 268
LANDMARK_AMBER_CELLS = {(12, 4), (11, 16)}


def _load_identity_cells() -> list[list[tuple[int, int, int] | None]]:
    return read_cells(SOFT_SHADED_IDENTITY_PNG)


def _load_palette() -> MasterPalette:
    return load_master_palette(MASTER_PALETTE_PATH)


def _beard_chest_cells() -> set[tuple[int, int]]:
    return {
        (x, y)
        for x in range(BEARD_CHEST_RECT["x0"], BEARD_CHEST_RECT["x1"] + 1)
        for y in range(BEARD_CHEST_RECT["y0"], BEARD_CHEST_RECT["y1"] + 1)
    }


def _corrected_identity_role_map(
    cells: list[list[tuple[int, int, int] | None]],
    palette: MasterPalette,
) -> dict[tuple[int, int], str]:
    """Human-corrected assignment: beard/chest off amber-emission."""
    assignment = propose_seed_role_map(cells, palette)
    beard_cluster = _beard_chest_cells()
    for coord, role in list(assignment.items()):
        if role == "amber-emission" and coord in beard_cluster:
            assignment[coord] = "earth-leather-beard"
    return assignment


def _alpha_mask(cells: list[list[tuple[int, int, int] | None]]) -> list[list[bool]]:
    return [[cell is not None for cell in row] for row in cells]


def _palette_color_set(palette: MasterPalette) -> set[tuple[int, int, int]]:
    colors: set[tuple[int, int, int]] = set()
    for role_colors in palette.role_colors.values():
        colors.update(role_colors)
    return colors


def test_global_nearest_role_assigns_forty_identity_cells_to_amber_emission() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    seed = propose_seed_role_map(cells, palette)
    amber_cells = [coord for coord, role in seed.items() if role == "amber-emission"]
    assert len(amber_cells) == GLOBAL_AMBER_EMISSION_COUNT
    beard_overlap = [coord for coord in amber_cells if coord in _beard_chest_cells()]
    assert beard_overlap, "expected beard/chest cluster in global amber-emission set"


def test_quantize_preserves_alpha_mask_on_synthetic_raster() -> None:
    palette = _load_palette()
    cells: list[list[tuple[int, int, int] | None]] = [
        [(200, 100, 50), None],
        [None, (10, 20, 30)],
    ]
    role_assignment = {
        (0, 0): "skin",
        (1, 1): "dark-outline",
    }
    quantized = quantize_cells(cells, palette, role_assignment)
    assert _alpha_mask(quantized) == _alpha_mask(cells)


def test_quantize_confines_each_cell_to_its_role_colors() -> None:
    palette = _load_palette()
    cells: list[list[tuple[int, int, int] | None]] = [
        [(200, 100, 50), (114, 226, 210)],
    ]
    role_assignment = {
        (0, 0): "skin",
        (1, 0): "cyan-crystal",
    }
    quantized = quantize_cells(cells, palette, role_assignment)
    for (x, y), role in role_assignment.items():
        cell = quantized[y][x]
        assert cell is not None
        assert cell in palette.role_colors[role]


def test_quantized_identity_is_palette_exact() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    role_map = _corrected_identity_role_map(cells, palette)
    quantized = quantize_cells(cells, palette, role_map)
    allowed = _palette_color_set(palette)
    for row in quantized:
        for cell in row:
            if cell is not None:
                assert cell in allowed


def test_quantized_identity_preserves_alpha_mask() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    role_map = _corrected_identity_role_map(cells, palette)
    quantized = quantize_cells(cells, palette, role_map)
    assert _alpha_mask(quantized) == _alpha_mask(cells)


def test_corrected_role_map_excludes_beard_cluster_from_amber_emission() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    role_map = _corrected_identity_role_map(cells, palette)
    amber_coords = {coord for coord, role in role_map.items() if role == "amber-emission"}
    assert amber_coords.isdisjoint(_beard_chest_cells())
    quantized = quantize_cells(cells, palette, role_map)
    amber_palette = set(palette.role_colors["amber-emission"])
    for coord in amber_coords:
        x, y = coord
        cell = quantized[y][x]
        assert cell is not None
        assert cell in amber_palette
    for coord in _beard_chest_cells():
        if cells[coord[1]][coord[0]] is None:
            continue
        assert role_map.get(coord) != "amber-emission"


def test_quantize_is_idempotent_on_already_quantized_raster() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    role_map = _corrected_identity_role_map(cells, palette)
    once = quantize_cells(cells, palette, role_map)
    twice = quantize_cells(once, palette, role_map)
    assert twice == once


def test_equidistant_role_colors_resolve_to_darker_luminance() -> None:
    palette = MasterPalette(
        role_ids=("test-role",),
        role_colors={
            "test-role": ((0, 0, 0), (2, 0, 0)),
        },
        entries=(("test-role", (0, 0, 0)), ("test-role", (2, 0, 0))),
    )
    cell = (1, 0, 0)
    chosen = nearest_color_in_role(cell, "test-role", palette)
    assert chosen == (0, 0, 0)
    assert relative_luminance(chosen) < relative_luminance((2, 0, 0))


def test_propose_seed_role_map_matches_nearest_palette_role_per_cell() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    seed = propose_seed_role_map(cells, palette)
    opaque_count = sum(1 for row in cells for cell in row if cell is not None)
    assert len(seed) == opaque_count
    for (x, y), role in seed.items():
        cell = cells[y][x]
        assert cell is not None
        assert role == nearest_palette_role(cell, palette.entries)


def test_load_master_palette_matches_first_room_role_groups() -> None:
    palette = _load_palette()
    assert palette.role_ids == (
        "dark-outline",
        "stone",
        "earth-leather-beard",
        "skin",
        "green-cloth",
        "blue-metal",
        "amber-emission",
        "cyan-crystal",
    )
    assert len(palette.role_colors["amber-emission"]) == 4


def test_quantize_cells_rejects_missing_role_assignment() -> None:
    palette = _load_palette()
    cells: list[list[tuple[int, int, int] | None]] = [[(100, 100, 100)]]
    with pytest.raises(Exception, match="missing role assignment"):
        quantize_cells(cells, palette, {})


def test_identity_opaque_cell_count_matches_contract() -> None:
    cells = _load_identity_cells()
    assert sum(1 for row in cells for cell in row if cell is not None) == OPAQUE_IDENTITY_CELL_COUNT


def test_landmark_amber_cells_remain_amber_in_seed_map() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    seed = propose_seed_role_map(cells, palette)
    for coord in LANDMARK_AMBER_CELLS:
        assert seed[coord] == "amber-emission"


def test_corrected_role_map_amber_cells_match_quantized_palette_roles() -> None:
    cells = _load_identity_cells()
    palette = _load_palette()
    role_map = _corrected_identity_role_map(cells, palette)
    quantized = quantize_cells(cells, palette, role_map)
    amber_palette = set(palette.role_colors["amber-emission"])
    for coord, role in role_map.items():
        x, y = coord
        cell = quantized[y][x]
        assert cell is not None
        if role == "amber-emission":
            assert cell in amber_palette
        else:
            assert cell in palette.role_colors[role]
    assert LANDMARK_AMBER_CELLS <= {
        coord for coord, role in role_map.items() if role == "amber-emission"
    }
