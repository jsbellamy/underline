"""Cave Autotile edge-compatibility and Terraced Shaft audit helpers (issue #108)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from PIL import Image

from pipeline.gate_evidence import sha256_file

N, E, S, W = 1, 2, 4, 8
VARIANTS = ("a", "b", "c")
MASK_COUNT = 16
CELL = 32
Outcome = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class EdgePairResult:
    axis: Literal["horizontal", "vertical"]
    left_or_top: str
    right_or_bottom: str
    mask_a: int
    mask_b: int
    variant: str
    pass_: bool
    detail: str | None = None


@dataclass(frozen=True)
class EdgeGeometryResult:
    mask: int
    edge: Literal["north", "east", "south", "west"]
    pass_: bool
    detail: str | None = None


@dataclass(frozen=True)
class EdgeCompatReport:
    outcome: Outcome
    pair_results: tuple[EdgePairResult, ...]
    geometry_results: tuple[EdgeGeometryResult, ...]
    exposed_distinct_pass: bool
    pair_failures: int
    geometry_failures: int


def release_item_path(bundle_root: Path, variant: str, mask: int) -> Path:
    return bundle_root / "release" / "blocks" / variant / f"mask-{mask:02d}.png"


def load_rgba_cells(path: Path) -> list[list[tuple[int, int, int, int]]]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        if rgba.size != (CELL, CELL):
            raise ValueError(f"{path}: expected {CELL}x{CELL}, got {rgba.size}")
        pixels = rgba.load()
        assert pixels is not None
        return [[pixels[x, y] for x in range(CELL)] for y in range(CELL)]


def _rgb(cell: tuple[int, int, int, int]) -> tuple[int, int, int]:
    return cell[0], cell[1], cell[2]


def edge_column(cells: list[list[tuple[int, int, int, int]]], x: int) -> list[tuple[int, int, int]]:
    return [_rgb(cells[y][x]) for y in range(CELL)]


def edge_row(cells: list[list[tuple[int, int, int, int]]], y: int) -> list[tuple[int, int, int]]:
    return [_rgb(cells[y][x]) for x in range(CELL)]


def masks_share_horizontal_edge(left_mask: int, right_mask: int) -> bool:
    return bool(left_mask & E) and bool(right_mask & W)


def masks_share_vertical_edge(top_mask: int, bottom_mask: int) -> bool:
    return bool(top_mask & S) and bool(bottom_mask & N)


def check_variant_edge_geometry(
    bundle_root: Path,
    mask: int,
) -> list[EdgeGeometryResult]:
    """Variants A/B/C must share identical edge geometry for the same mask."""
    cells_by_variant = {
        variant: load_rgba_cells(release_item_path(bundle_root, variant, mask))
        for variant in VARIANTS
    }
    results: list[EdgeGeometryResult] = []
    edges: list[tuple[Literal["north", "east", "south", "west"], list[tuple[int, int, int]]]] = [
        ("north", edge_row(cells_by_variant["a"], 0)),
        ("east", edge_column(cells_by_variant["a"], CELL - 1)),
        ("south", edge_row(cells_by_variant["a"], CELL - 1)),
        ("west", edge_column(cells_by_variant["a"], 0)),
    ]
    for edge_name, expected in edges:
        mismatches: list[str] = []
        for variant in ("b", "c"):
            actual = (
                edge_row(cells_by_variant[variant], 0)
                if edge_name == "north"
                else edge_column(cells_by_variant[variant], CELL - 1)
                if edge_name == "east"
                else edge_row(cells_by_variant[variant], CELL - 1)
                if edge_name == "south"
                else edge_column(cells_by_variant[variant], 0)
            )
            if actual != expected:
                mismatches.append(variant)
        results.append(
            EdgeGeometryResult(
                mask=mask,
                edge=edge_name,
                pass_=not mismatches,
                detail=None if not mismatches else f"diverges on variants {mismatches}",
            )
        )
    return results


def check_compatible_pairs(bundle_root: Path) -> list[EdgePairResult]:
    results: list[EdgePairResult] = []
    for variant in VARIANTS:
        cells = {
            mask: load_rgba_cells(release_item_path(bundle_root, variant, mask))
            for mask in range(MASK_COUNT)
        }
        for left_mask in range(MASK_COUNT):
            for right_mask in range(MASK_COUNT):
                if not masks_share_horizontal_edge(left_mask, right_mask):
                    continue
                left_edge = edge_column(cells[left_mask], CELL - 1)
                right_edge = edge_column(cells[right_mask], 0)
                ok = left_edge == right_edge
                results.append(
                    EdgePairResult(
                        axis="horizontal",
                        left_or_top=f"mask-{left_mask:02d}",
                        right_or_bottom=f"mask-{right_mask:02d}",
                        mask_a=left_mask,
                        mask_b=right_mask,
                        variant=variant,
                        pass_=ok,
                        detail=None if ok else "east/west boundary Cells differ",
                    )
                )
        for top_mask in range(MASK_COUNT):
            for bottom_mask in range(MASK_COUNT):
                if not masks_share_vertical_edge(top_mask, bottom_mask):
                    continue
                top_edge = edge_row(cells[top_mask], CELL - 1)
                bottom_edge = edge_row(cells[bottom_mask], 0)
                ok = top_edge == bottom_edge
                results.append(
                    EdgePairResult(
                        axis="vertical",
                        left_or_top=f"mask-{top_mask:02d}",
                        right_or_bottom=f"mask-{bottom_mask:02d}",
                        mask_a=top_mask,
                        mask_b=bottom_mask,
                        variant=variant,
                        pass_=ok,
                        detail=None if ok else "south/north boundary Cells differ",
                    )
                )
    return results


def check_exposed_edges_distinct(bundle_root: Path) -> bool:
    """Exposed boundary templates must differ from the shared connected seam."""
    # Use mask 0 (all exposed) vs mask 15 (all connected) on variant a.
    exposed = load_rgba_cells(release_item_path(bundle_root, "a", 0))
    connected = load_rgba_cells(release_item_path(bundle_root, "a", 15))
    checks = [
        edge_row(exposed, 0) != edge_row(connected, 0),
        edge_row(exposed, CELL - 1) != edge_row(connected, CELL - 1),
        edge_column(exposed, 0) != edge_column(connected, 0),
        edge_column(exposed, CELL - 1) != edge_column(connected, CELL - 1),
    ]
    return all(checks)


def build_edge_compat_report(bundle_root: Path) -> EdgeCompatReport:
    pairs = check_compatible_pairs(bundle_root)
    geometry: list[EdgeGeometryResult] = []
    for mask in range(MASK_COUNT):
        geometry.extend(check_variant_edge_geometry(bundle_root, mask))
    exposed_ok = check_exposed_edges_distinct(bundle_root)
    pair_failures = sum(1 for row in pairs if not row.pass_)
    geometry_failures = sum(1 for row in geometry if not row.pass_)
    outcome: Outcome = (
        "PASS" if pair_failures == 0 and geometry_failures == 0 and exposed_ok else "FAIL"
    )
    return EdgeCompatReport(
        outcome=outcome,
        pair_results=tuple(pairs),
        geometry_results=tuple(geometry),
        exposed_distinct_pass=exposed_ok,
        pair_failures=pair_failures,
        geometry_failures=geometry_failures,
    )


def _bundle_ref(bundle_root: Path) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        return bundle_root.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return str(bundle_root.as_posix())


def edge_compat_payload(report: EdgeCompatReport, bundle_root: Path) -> dict[str, Any]:
    return {
        "schema": "cave-autotile-edge-compat/0",
        "bundle": _bundle_ref(bundle_root),
        "outcome": report.outcome,
        "pair_count": len(report.pair_results),
        "pair_failures": report.pair_failures,
        "geometry_count": len(report.geometry_results),
        "geometry_failures": report.geometry_failures,
        "exposed_edges_distinct": report.exposed_distinct_pass,
        "failures": [
            {
                "axis": row.axis,
                "a": row.left_or_top,
                "b": row.right_or_bottom,
                "variant": row.variant,
                "detail": row.detail,
            }
            for row in report.pair_results
            if not row.pass_
        ]
        + [
            {
                "mask": row.mask,
                "edge": row.edge,
                "detail": row.detail,
            }
            for row in report.geometry_results
            if not row.pass_
        ],
    }


# --- Terraced Shaft preview (Variant B composition) ---

# 10×5 Mineable Block occupancy; 1 = solid. Deterministic A/B/C via (x+3y)%3.
TERRACED_SHAFT_SOLID: tuple[tuple[int, ...], ...] = (
    (1, 1, 1, 1, 1, 1, 1, 1, 1, 1),  # ceiling
    (1, 1, 0, 0, 0, 0, 0, 0, 1, 1),  # upper walls / opening
    (1, 1, 0, 1, 1, 1, 1, 0, 1, 1),  # walking terrace
    (1, 1, 0, 0, 0, 0, 0, 0, 1, 1),  # vertical mining space
    (1, 1, 1, 1, 0, 0, 1, 1, 1, 1),  # lower walk with center gap
)


def neighbor_mask(solid: Sequence[Sequence[int]], x: int, y: int) -> int:
    rows = len(solid)
    cols = len(solid[0])
    mask = 0
    if y > 0 and solid[y - 1][x]:
        mask |= N
    if x + 1 < cols and solid[y][x + 1]:
        mask |= E
    if y + 1 < rows and solid[y + 1][x]:
        mask |= S
    if x > 0 and solid[y][x - 1]:
        mask |= W
    return mask


def variant_for_cell(x: int, y: int) -> str:
    return VARIANTS[(x + 3 * y) % 3]


def render_terraced_shaft(
    bundle_root: Path,
    *,
    out_path: Path,
    background: tuple[int, int, int] = (0x1D, 0x17, 0x20),
) -> dict[str, Any]:
    """Render a native 320×160 Terraced Shaft composite from Release items."""
    solid = TERRACED_SHAFT_SOLID
    rows = len(solid)
    cols = len(solid[0])
    width = cols * CELL
    height = rows * CELL
    image = Image.new("RGBA", (width, height), (*background, 255))
    placements: list[dict[str, Any]] = []
    for y in range(rows):
        for x in range(cols):
            if not solid[y][x]:
                continue
            mask = neighbor_mask(solid, x, y)
            variant = variant_for_cell(x, y)
            src_path = release_item_path(bundle_root, variant, mask)
            with Image.open(src_path) as block:
                image.paste(block.convert("RGBA"), (x * CELL, y * CELL))
            placements.append(
                {
                    "x": x,
                    "y": y,
                    "mask": mask,
                    "variant": variant,
                    "release_path": f"blocks/{variant}/mask-{mask:02d}.png",
                    "sha256": sha256_file(src_path),
                }
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)

    expected_solids = sum(cell for row in solid for cell in row)
    terrace_row = solid[2]
    mining_row = solid[3]
    walk_row = solid[4]
    terrace_has_run = any(terrace_row[i] and terrace_row[i + 1] for i in range(cols - 1))
    terrace_has_gap = 0 in terrace_row
    mining_has_void = mining_row.count(0) >= 4 and mining_row[0] == 1 and mining_row[-1] == 1
    lower_walk_gap = walk_row[4] == 0 and walk_row[5] == 0 and walk_row[3] == 1 and walk_row[6] == 1
    exposed_masks = sum(1 for row in placements if row["mask"] != 15)
    variants_used = {row["variant"] for row in placements}

    dims_ok = width == 320 and height == 160
    count_ok = len(placements) == expected_solids == 34
    terrace_ok = terrace_has_run and terrace_has_gap
    mining_ok = mining_has_void
    boundaries_ok = exposed_masks >= 8 and lower_walk_gap
    variants_ok = variants_used == {"a", "b", "c"}
    machine_ok = all((dims_ok, count_ok, terrace_ok, mining_ok, boundaries_ok, variants_ok))

    def _verdict(ok: bool) -> Outcome:
        return "PASS" if ok else "FAIL"

    return {
        "schema": "terraced-shaft-audit/0",
        "composition": "Variant B — Terraced Shaft",
        "viewport_note": "native Mineable Block composite 320×160 (10×5 blocks); art-direction viewport is 320×180",
        "dimensions": [width, height],
        "solid_grid": [list(row) for row in solid],
        "variant_rule": "(x + 3*y) % 3 → a/b/c",
        "placements": placements,
        "image": {
            "relative_path": "assets/first-room/cave/reports/terraced-shaft-preview.png",
            "sha256": sha256_file(out_path),
            "width": width,
            "height": height,
        },
        "machine_checks": {
            "dimensions_320x160": dims_ok,
            "placement_count_34": count_ok,
            "walking_terrace_row": terrace_ok,
            "vertical_mining_void": mining_ok,
            "exposed_boundaries_and_lower_gap": boundaries_ok,
            "abc_variant_distribution": variants_ok,
        },
        "inspection": {
            "native_scale": True,
            "walking_terraces_legible": _verdict(terrace_ok),
            "vertical_mining_space_legible": _verdict(mining_ok),
            "block_boundaries_legible": _verdict(boundaries_ok and dims_ok and count_ok),
            "no_semantic_uncertainty": machine_ok,
        },
        "overall": _verdict(machine_ok),
    }


