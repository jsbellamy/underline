"""Strip animation ingest — pure logic for the underline prototype.

Recovers a wide logical grid from one provider render, slices into frames, and emits a
deterministic coherence report. Imports Nightglass acquire primitives only; no I/O here.
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any

from PIL import Image

# Nightglass pipeline lives beside this repo under game_idea/
_NIGHTGLASS_PIPELINE = pathlib.Path(__file__).resolve().parents[3] / "nightglass" / "pipeline"
if str(_NIGHTGLASS_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_NIGHTGLASS_PIPELINE))

import acquire  # noqa: E402
from icons.constants import MIN_GRID_SCORE  # noqa: E402

Cell = tuple[int, int, int] | None
MIN_LONG_AXIS = 20
DEFAULT_MAX_PALETTE = 16
MERGE_DIST_RGB = 36  # collapse anti-aliased neighbors before palette build
PROVIDER_MERGE_DIST_RGB = 64

REGISTRATION_SPAN = 1


@dataclass(frozen=True)
class ClassBudget:
    max_silhouette: float | None
    max_loop: float | None
    max_drift: float
    grounded: bool
    loops: bool


# Per-motion-class budgets — derived in docs/strip-acquisition-contract.md.
MOTION_CLASSES: dict[str, ClassBudget] = {
    "idle": ClassBudget(
        max_silhouette=0.17,
        max_loop=0.30,
        max_drift=0.14,
        grounded=True,
        loops=True,
    ),
    "blob_idle": ClassBudget(
        max_silhouette=0.36,
        max_loop=0.36,
        max_drift=0.17,
        grounded=True,
        loops=True,
    ),
    "walk": ClassBudget(
        max_silhouette=0.42,
        max_loop=0.17,
        max_drift=0.14,
        grounded=True,
        loops=True,
    ),
    "swing": ClassBudget(
        max_silhouette=0.59,
        max_loop=None,
        max_drift=0.20,
        grounded=True,
        loops=False,
    ),
    "airborne": ClassBudget(
        max_silhouette=None,
        max_loop=0.68,
        max_drift=0.17,
        grounded=False,
        loops=True,
    ),
    "emissive": ClassBudget(
        max_silhouette=0.18,
        max_loop=0.16,
        max_drift=0.17,
        grounded=True,
        loops=True,
    ),
}


@dataclass(frozen=True)
class StripLayout:
    frame_w: int = 16
    frame_h: int = 24
    frame_count: int = 4
    gutter: int = 2
    pitch_px: int = 24
    margin_cells: int = 2
    grounded: bool = True

    def strip_width(self) -> int:
        return self.frame_count * self.frame_w + (self.frame_count - 1) * self.gutter

    def raster_width(self) -> int:
        return self.strip_width() + 2 * self.margin_cells

    def raster_height(self) -> int:
        return self.frame_h + 2 * self.margin_cells


@dataclass(frozen=True)
class IngestResult:
    layout: StripLayout
    source: str
    recovered: dict[str, Any]
    slice_meta: dict[str, Any]
    coherence: dict[str, Any]
    pass_: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "layout": {
                "frame_w": self.layout.frame_w,
                "frame_h": self.layout.frame_h,
                "frame_count": self.layout.frame_count,
                "gutter": self.layout.gutter,
                "strip_width": self.layout.strip_width(),
            },
            "source": self.source,
            "recovered": self.recovered,
            "slice": self.slice_meta,
            "coherence": self.coherence,
            "pass": self.pass_,
        }


def _rgb_dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _nearest_rgb(rgb: tuple[int, int, int], palette: tuple[tuple[int, int, int], ...]) -> tuple[int, int, int]:
    return min(palette, key=lambda sw: _rgb_dist2(rgb, sw))


def collect_opaque_rgbs(frames: list[list[list[Cell]]]) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    for frame in frames:
        for row in frame:
            for rgb in row:
                if rgb is not None:
                    out.append(rgb)
    return out


def build_shared_palette(
    rgbs: list[tuple[int, int, int]],
    *,
    max_colors: int = DEFAULT_MAX_PALETTE,
    merge_dist: int = MERGE_DIST_RGB,
) -> tuple[tuple[tuple[int, int, int], ...], dict[str, Any]]:
    """Deterministic frequency palette with optional merge of near-duplicates."""
    merge2 = merge_dist * merge_dist
    clusters: list[list[tuple[int, int, int]]] = []
    for rgb, _count in Counter(rgbs).most_common():
        placed = False
        for cluster in clusters:
            if _rgb_dist2(rgb, cluster[0]) <= merge2:
                cluster.append(rgb)
                placed = True
                break
        if not placed:
            clusters.append([rgb])
    ranked = sorted(clusters, key=lambda c: (-sum(Counter(rgbs)[r] for r in c), c[0]))
    reps = tuple(cluster[0] for cluster in ranked[:max_colors])
    stats = {
        "input_unique": len(set(rgbs)),
        "clusters": len(clusters),
        "palette_size": len(reps),
        "palette": [list(rgb) for rgb in reps],
    }
    return reps, stats


def quantize_frames(
    frames: list[list[list[Cell]]],
    *,
    max_colors: int = DEFAULT_MAX_PALETTE,
) -> tuple[list[list[list[Cell]]], dict[str, Any]]:
    rgbs = collect_opaque_rgbs(frames)
    palette, stats = build_shared_palette(rgbs, max_colors=max_colors)
    if not palette:
        return frames, {**stats, "mode": "quantize-shared"}
    out: list[list[list[Cell]]] = []
    for frame in frames:
        qframe: list[list[Cell]] = []
        for row in frame:
            qframe.append(
                [None if rgb is None else _nearest_rgb(rgb, palette) for rgb in row]
            )
        out.append(qframe)
    return out, {**stats, "mode": "quantize-shared"}


def baseline_row_cells(frame: list[list[Cell]], baseline: int) -> list[Cell]:
    if baseline < 0 or baseline >= len(frame):
        return []
    return list(frame[baseline])


def baseline_cells_match(a: list[list[Cell]], b: list[list[Cell]]) -> bool:
    ba, bb = baseline_row(a), baseline_row(b)
    if ba is None or bb is None:
        return ba == bb
    return baseline_row_cells(a, ba) == baseline_row_cells(b, bb)


def cell_diff_motion(
    a: list[list[Cell]],
    b: list[list[Cell]],
) -> tuple[int, int]:
    """Cell diff above the planted baseline row (feet must not move)."""
    changed = 0
    union_opaque = 0
    baseline = baseline_row(a)
    if baseline is None:
        return cell_diff(a, b)
    for y in range(len(a)):
        if y >= baseline:
            continue
        for x in range(len(a[y])):
            a_cell = a[y][x]
            b_cell = b[y][x]
            if a_cell is None and b_cell is None:
                continue
            union_opaque += 1
            if a_cell != b_cell:
                changed += 1
    return changed, union_opaque


def _silhouette_diff_at_shift(
    a: list[list[Cell]],
    b: list[list[Cell]],
    dx: int,
    *,
    anchor: int | None = None,
) -> tuple[int, int]:
    """Occupancy flips above the anchor row with b shifted by dx columns."""
    changed = 0
    union_opaque = 0
    if anchor is None:
        anchor = baseline_row(a)
    if anchor is None:
        anchor = len(a)
    for y in range(min(len(a), len(b))):
        if y >= anchor:
            continue
        for x in range(len(a[y])):
            a_cell = a[y][x]
            xb = x + dx
            if 0 <= xb < len(b[y]):
                b_cell = b[y][xb]
            else:
                b_cell = None
            if a_cell is None and b_cell is None:
                continue
            union_opaque += 1
            if (a_cell is None) != (b_cell is None):
                changed += 1
    return changed, union_opaque


def silhouette_diff(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = REGISTRATION_SPAN,
    anchor: int | None = None,
) -> tuple[int, int]:
    """Occupancy flips above the anchor row — real motion, colour-blind.

    When anchor is None, uses baseline_row(a) so existing callers keep today's
    behaviour. When span > 0, return the (changed, union_opaque) pair for the
    x-shift in [-span, +span] that minimises changed / union_opaque. Shifted-out
    positions read as transparent.
    """
    best_changed = 0
    best_union = 0
    best_frac = float("inf")
    for dx in range(-span, span + 1):
        changed, union = _silhouette_diff_at_shift(a, b, dx, anchor=anchor)
        frac = changed / union if union else 0.0
        if frac < best_frac:
            best_frac = frac
            best_changed = changed
            best_union = union
    return best_changed, best_union


def silhouette_pair_frac(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    anchor: int | None = None,
) -> float:
    changed, union = silhouette_diff(a, b, anchor=anchor)
    return round(changed / union, 4) if union else 0.0


def silhouette_pairwise(
    frames: list[list[list[Cell]]],
    *,
    anchor: int | None = None,
) -> dict[str, Any]:
    """Pairwise silhouette stats — cohort signal alongside adjacent max-pair."""
    n = len(frames)
    pairs: list[dict[str, Any]] = []
    fracs: list[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            frac = silhouette_pair_frac(frames[i], frames[j], anchor=anchor)
            pairs.append({"pair": [i, j], "frac": frac})
            fracs.append(frac)

    orphan_fracs: list[float] = []
    for i in range(n):
        others = [
            silhouette_pair_frac(frames[i], frames[j], anchor=anchor)
            for j in range(n)
            if j != i
        ]
        orphan_fracs.append(min(others) if others else 0.0)

    return {
        "pairs": pairs,
        "max_pair": round(max(fracs), 4) if fracs else 0.0,
        "min_pair": round(min(fracs), 4) if fracs else 0.0,
        "orphan_max": round(max(orphan_fracs), 4) if orphan_fracs else 0.0,
    }


def palette_histogram(frame: list[list[Cell]]) -> dict[tuple[int, int, int], float]:
    counts = Counter(rgb for row in frame for rgb in row if rgb is not None)
    total = sum(counts.values()) or 1
    return {rgb: n / total for rgb, n in counts.items()}


def palette_drift(frames: list[list[list[Cell]]]) -> list[dict[str, Any]]:
    """Total-variation distance between per-frame colour histograms.

    A re-shade keeps the colour mix (~0.02-0.11); a recolour moves it (~0.74).
    """
    hists = [palette_histogram(f) for f in frames]
    keys: set[tuple[int, int, int]] = set()
    for h in hists:
        keys |= set(h)
    pairs = [(i, i + 1) for i in range(len(frames) - 1)]
    if len(frames) >= 2:
        pairs.append((len(frames) - 1, 0))
    return [
        {
            "pair": [i, j],
            "tv": round(
                0.5 * sum(abs(hists[i].get(k, 0.0) - hists[j].get(k, 0.0)) for k in keys),
                4,
            ),
        }
        for i, j in pairs
    ]


def coherence_split(
    frames: list[list[list[Cell]]],
    *,
    motion_class: str,
    max_colors: int = DEFAULT_MAX_PALETTE,
    merge_dist: int = PROVIDER_MERGE_DIST_RGB,
    anchor_row: int | None = None,
) -> dict[str, Any]:
    """Gate motion and recolour separately, on a shared quantized palette."""
    if not frames:
        return {"pass": False, "reason": "no frames"}
    if motion_class not in MOTION_CLASSES:
        raise ValueError(f"unknown motion_class: {motion_class!r}")

    budget = MOTION_CLASSES[motion_class]
    grounded = budget.grounded
    max_silhouette_diff = budget.max_silhouette
    max_loop_diff = budget.max_loop
    max_palette_drift = budget.max_drift

    rgbs = collect_opaque_rgbs(frames)
    palette, stats = build_shared_palette(
        rgbs, max_colors=max_colors, merge_dist=merge_dist
    )
    if palette:
        q = [
            [[None if rgb is None else _nearest_rgb(rgb, palette) for rgb in row]
             for row in frame]
            for frame in frames
        ]
    else:
        q = frames

    dims = {(len(f[0]), len(f)) for f in q}
    baselines = [baseline_row(f) for f in q]

    if grounded:
        anchor = anchor_row if anchor_row is not None else baselines[0]
        sil_anchor: int | None = anchor
        baseline_stable = all(b == anchor for b in baselines)
    else:
        anchor = None
        sil_anchor = len(q[0]) if q else 0
        baseline_stable = None

    adjacent: list[dict[str, Any]] = []
    for i in range(len(q) - 1):
        changed, union = silhouette_diff(q[i], q[i + 1], anchor=sil_anchor)
        adjacent.append(
            {
                "pair": [i, i + 1],
                "changed_cells": changed,
                "union_opaque": union,
                "frac": round(changed / union, 4) if union else 0.0,
            }
        )

    loop: dict[str, Any] | None = None
    loop_closure_pass: bool | None = None
    if len(q) >= 2:
        changed, union = silhouette_diff(q[-1], q[0], anchor=sil_anchor)
        frac = round(changed / union, 4) if union else 0.0
        loop = {
            "pair": [len(q) - 1, 0],
            "changed_cells": changed,
            "union_opaque": union,
            "frac": frac,
        }
        if budget.loops and max_loop_diff is not None:
            loop_closure_pass = frac <= max_loop_diff
            loop["pass"] = loop_closure_pass

    drift = palette_drift(q)
    worst_drift = max((d["tv"] for d in drift), default=0.0)
    pairwise = silhouette_pairwise(q, anchor=sil_anchor)
    adjacent_max = max((row["frac"] for row in adjacent), default=0.0)

    silhouette_budget: bool | None = None
    if max_silhouette_diff is not None:
        silhouette_budget = all(row["frac"] <= max_silhouette_diff for row in adjacent)

    gates = {
        "quantize": {**stats, "mode": "quantize-shared", "merge_dist": merge_dist},
        "motion_class": motion_class,
        "dimension_parity": len(dims) == 1,
        "dimensions": sorted(dims),
        "grounded": grounded,
        "anchor_row": anchor,
        "baseline_row_stable": baseline_stable,
        "baseline_rows": baselines,
        "silhouette_adjacent": adjacent,
        "silhouette_adjacent_max": adjacent_max,
        "silhouette_pairwise": pairwise,
        "silhouette_budget": silhouette_budget,
        "loop_closure": loop,
        "loop_closure_pass": loop_closure_pass,
        "palette_drift": drift,
        "worst_palette_drift": worst_drift,
        "palette_drift_pass": worst_drift <= max_palette_drift,
        "budgets": {
            "silhouette": max_silhouette_diff,
            "loop": max_loop_diff,
            "palette_drift": max_palette_drift,
        },
    }
    pass_parts: list[bool] = [gates["dimension_parity"]]
    if gates["baseline_row_stable"] is not None:
        pass_parts.append(gates["baseline_row_stable"])
    if gates["silhouette_budget"] is not None:
        pass_parts.append(gates["silhouette_budget"])
    if gates["loop_closure_pass"] is not None:
        pass_parts.append(gates["loop_closure_pass"])
    pass_parts.append(gates["palette_drift_pass"])
    gates["pass"] = all(pass_parts)
    return gates


def coherence_report(
    frames: list[list[list[Cell]]],
    *,
    max_adjacent_diff_frac: float = 0.28,
    max_loop_diff_frac: float = 0.28,
    motion_only: bool = False,
    require_baseline_cells_locked: bool = True,
    require_palette_set_equal: bool = True,
) -> dict[str, Any]:
    if not frames:
        return {"pass": False, "reason": "no frames"}

    diff_fn = cell_diff_motion if motion_only else cell_diff
    dims = {(len(f[0]), len(f)) for f in frames}
    baselines = [baseline_row(f) for f in frames]

    baseline_locked = True
    for i in range(len(frames) - 1):
        if not baseline_cells_match(frames[i], frames[i + 1]):
            baseline_locked = False
            break
    if len(frames) >= 2 and not baseline_cells_match(frames[-1], frames[0]):
        baseline_locked = False

    palettes = [palette_set(f) for f in frames]

    adjacent: list[dict[str, Any]] = []
    for i in range(len(frames) - 1):
        changed, union = diff_fn(frames[i], frames[i + 1])
        adjacent.append(
            {
                "pair": [i, i + 1],
                "changed_cells": changed,
                "union_opaque": union,
                "frac": round(changed / union, 4) if union else 0.0,
            }
        )

    loop: dict[str, Any] | None = None
    if len(frames) >= 2:
        changed, union = diff_fn(frames[-1], frames[0])
        frac = round(changed / union, 4) if union else 0.0
        loop = {
            "pair": [len(frames) - 1, 0],
            "changed_cells": changed,
            "union_opaque": union,
            "frac": frac,
            "pass": frac <= max_loop_diff_frac,
        }

    gates = {
        "motion_only": motion_only,
        "dimension_parity": len(dims) == 1,
        "dimensions": sorted(dims),
        "baseline_row_stable": len(set(baselines)) == 1,
        "baseline_rows": baselines,
        "baseline_cells_locked": baseline_locked,
        "palette_set_equal": len(set(palettes)) == 1,
        "palette_counts": [len(p) for p in palettes],
        "adjacent_diff_budget": all(
            row["frac"] <= max_adjacent_diff_frac for row in adjacent
        ),
        "adjacent": adjacent,
        "loop_closure": loop,
        "loop_closure_pass": loop["pass"] if loop else True,
    }
    pass_parts: list[bool] = [
        gates["dimension_parity"],
        gates["baseline_row_stable"],
        gates["adjacent_diff_budget"],
        gates["loop_closure_pass"],
    ]
    if require_baseline_cells_locked:
        pass_parts.insert(2, gates["baseline_cells_locked"])
    if require_palette_set_equal:
        pass_parts.append(gates["palette_set_equal"])
    gates["pass"] = all(pass_parts)
    return gates


def expected_strip_width(layout: StripLayout) -> int:
    return layout.strip_width()


def recover_strip_cells(
    raw_path: pathlib.Path,
    layout: StripLayout,
) -> tuple[list[list[Cell]], dict[str, Any]]:
    gate_errs = acquire.raw_gates(raw_path)
    gate_errs = [e for e in gate_errs if "missing provenance" not in e]
    if gate_errs:
        raise ValueError("; ".join(gate_errs))

    clip = acquire.raw_clipping(raw_path)
    if clip:
        raise ValueError("; ".join(clip))

    src, fg, bbox = acquire._key(raw_path)
    x0, y0, x1, y1 = bbox
    # Tight fg bbox drops magenta gutters between frames; sample the full raster.
    x0, y0, x1, y1 = 0, 0, src.width - 1, src.height - 1
    bbox = (x0, y0, x1, y1)
    bbox_w = x1 - x0 + 1
    bbox_h = y1 - y0 + 1
    strip_w = layout.strip_width()
    pitch_val = float(layout.pitch_px)
    # Phase-only search around the declared render pitch (prompt pins block size; bbox height
    # reflects silhouette rows, not full frame_h, so bbox_h/frame_h is not a pitch estimator).
    band_lo, band_hi = pitch_val * 0.98, pitch_val * 1.02
    pitch_y_fit = acquire.detect_pitch(src, fg, "y", band_lo, band_hi)
    pitch_x_fit = acquire.detect_pitch(src, fg, "x", band_lo, band_hi)
    pitch_y = {
        "pitch": pitch_val,
        "phase": pitch_y_fit["phase"],
        "score": pitch_y_fit["score"],
    }
    pitch_x = {
        "pitch": pitch_val,
        "phase": pitch_x_fit["phase"],
        "score": pitch_x_fit["score"],
    }
    if pitch_y["score"] < MIN_GRID_SCORE:
        raise ValueError(
            f"pitch-fail y={pitch_y['score']:.3f} (floor={MIN_GRID_SCORE}); "
            f"try --pitch or regenerate with clearer blocks"
        )

    cells = acquire.sample_cells(src, fg, bbox, pitch_x, pitch_y)
    grid_h = len(cells)
    grid_w = len(cells[0]) if cells else 0
    meta: dict[str, Any] = {
        "bbox": list(bbox),
        "pitch_x": {"pitch": pitch_x["pitch"], "score": pitch_x["score"]},
        "pitch_y": {"pitch": pitch_y["pitch"], "score": pitch_y["score"]},
        "grid": [grid_w, grid_h],
        "expected_grid": [layout.raster_width(), layout.raster_height()],
    }
    long_axis = max(grid_w, grid_h)
    if long_axis < MIN_LONG_AXIS:
        meta["size_review"] = "thin"
    return cells, meta


def trim_margin(
    cells: list[list[Cell]],
    layout: StripLayout,
) -> list[list[Cell]]:
    m = layout.margin_cells
    if m <= 0:
        return cells
    return [row[m:-m] for row in cells[m:-m]]


def empty_column_runs(cells: list[list[Cell]]) -> list[tuple[int, int]]:
    """Inclusive ranges of columns that are entirely transparent."""
    if not cells:
        return []
    w = len(cells[0])
    runs: list[tuple[int, int]] = []
    x = 0
    while x < w:
        while x < w and any(cells[y][x] is not None for y in range(len(cells))):
            x += 1
        if x >= w:
            break
        start = x
        while x < w and all(cells[y][x] is None for y in range(len(cells))):
            x += 1
        runs.append((start, x - 1))
    return runs


def opaque_segments(cells: list[list[Cell]]) -> list[tuple[int, int]]:
    """Inclusive column spans between empty-column gutters."""
    if not cells:
        return []
    w = len(cells[0])
    gutters = empty_column_runs(cells)
    segments: list[tuple[int, int]] = []
    cursor = 0
    for g0, g1 in gutters:
        if cursor < g0:
            segments.append((cursor, g0 - 1))
        cursor = g1 + 1
    if cursor < w:
        segments.append((cursor, w - 1))
    return segments


def slice_frames_pitch(
    cells: list[list[Cell]],
    *,
    frame_count: int,
) -> tuple[list[list[list[Cell]]] | None, dict[str, Any]]:
    """Slice the recovered grid at uniform pitch so frame position survives."""
    grid_h = len(cells)
    grid_w = len(cells[0]) if cells else 0
    meta: dict[str, Any] = {
        "mode": "pitch",
        "grid": [grid_w, grid_h],
    }
    if frame_count <= 0 or grid_w % frame_count != 0:
        meta["reason"] = f"grid width {grid_w} not divisible by {frame_count}"
        return None, meta
    pitch = grid_w // frame_count
    frame_starts = [i * pitch for i in range(frame_count)]
    meta["pitch"] = pitch
    meta["frame_starts"] = frame_starts
    frames = [
        [row[start : start + pitch] for row in cells] for start in frame_starts
    ]
    return frames, meta


def slice_frames(
    cells: list[list[Cell]],
    layout: StripLayout,
) -> tuple[list[list[list[Cell]]] | None, dict[str, Any]]:
    grid_h = len(cells)
    grid_w = len(cells[0]) if cells else 0
    expected_raster = [layout.raster_width(), layout.raster_height()]
    meta: dict[str, Any] = {
        "grid": [grid_w, grid_h],
        "expected_raster": expected_raster,
        "raster_match": grid_w == expected_raster[0] and grid_h == expected_raster[1],
    }
    if not meta["raster_match"]:
        meta["shape_match"] = False
        meta["expected"] = [layout.strip_width(), layout.frame_h]
        return None, meta

    inner = trim_margin(cells, layout)
    inner_h = len(inner)
    inner_w = len(inner[0]) if inner else 0
    expected_w = layout.strip_width()
    meta["expected"] = [expected_w, layout.frame_h]
    meta["shape_match"] = inner_w == expected_w and inner_h == layout.frame_h
    if not meta["shape_match"]:
        return None, meta

    frames: list[list[list[Cell]]] = []
    x = 0
    for _ in range(layout.frame_count):
        frame = [row[x : x + layout.frame_w] for row in inner]
        frames.append(frame)
        x += layout.frame_w + layout.gutter
    return frames, meta


def baseline_row(frame: list[list[Cell]]) -> int | None:
    for y in range(len(frame) - 1, -1, -1):
        if any(frame[y][x] is not None for x in range(len(frame[y]))):
            return y
    return None


def palette_set(frame: list[list[Cell]]) -> frozenset[tuple[int, int, int]]:
    colors: set[tuple[int, int, int]] = set()
    for row in frame:
        for rgb in row:
            if rgb is not None:
                colors.add(rgb)
    return frozenset(colors)


def cell_diff(
    a: list[list[Cell]],
    b: list[list[Cell]],
) -> tuple[int, int]:
    changed = 0
    union_opaque = 0
    for y in range(len(a)):
        for x in range(len(a[y])):
            a_cell = a[y][x]
            b_cell = b[y][x]
            if a_cell is None and b_cell is None:
                continue
            union_opaque += 1
            if a_cell != b_cell:
                changed += 1
    return changed, union_opaque


def ingest_strip(
    raw_path: pathlib.Path,
    layout: StripLayout,
    *,
    motion_class: str = "idle",
) -> IngestResult:
    cells, recovered = recover_strip_cells(raw_path, layout)
    frames, slice_meta = slice_frames(cells, layout)
    if frames is None:
        coherence = {
            "pass": False,
            "reason": "grid shape mismatch",
            "expected": slice_meta["expected"],
            "got": slice_meta["grid"],
        }
    else:
        coherence = coherence_split(frames, motion_class=motion_class)

    pitch_ok = (
        recovered["pitch_x"]["score"] >= MIN_GRID_SCORE
        and recovered["pitch_y"]["score"] >= MIN_GRID_SCORE
    )
    pass_ = pitch_ok and coherence.get("pass", False)

    return IngestResult(
        layout=layout,
        source=str(raw_path),
        recovered=recovered,
        slice_meta=slice_meta,
        coherence=coherence,
        pass_=pass_,
    )


def ingest_strip_provider(
    raw_path: pathlib.Path,
    layout: StripLayout,
    *,
    motion_class: str = "idle",
) -> IngestResult:
    """Recover full raster and slice at uniform pitch (provider slop tolerant)."""
    probe = StripLayout(
        frame_w=layout.frame_w,
        frame_h=layout.frame_h,
        frame_count=layout.frame_count,
        gutter=layout.gutter,
        pitch_px=layout.pitch_px,
        margin_cells=0,
    )
    cells, recovered = recover_strip_cells(raw_path, probe)
    frames, slice_meta = slice_frames_pitch(cells, frame_count=layout.frame_count)
    if frames is None:
        coherence = {
            "pass": False,
            "reason": slice_meta.get("reason", "auto-slice failed"),
            "slice": slice_meta,
        }
    else:
        coherence = coherence_split(frames, motion_class=motion_class)

    pitch_ok = (
        recovered["pitch_x"]["score"] >= MIN_GRID_SCORE
        or recovered["pitch_y"]["score"] >= MIN_GRID_SCORE
    )
    pass_ = pitch_ok and coherence.get("pass", False)

    return IngestResult(
        layout=layout,
        source=str(raw_path),
        recovered=recovered,
        slice_meta=slice_meta,
        coherence=coherence,
        pass_=pass_,
    )


# --- synthetic fixtures (no provider required) ---


def _draw_block(
    px: Any,
    gx: int,
    gy: int,
    pitch: int,
    pad: int,
    rgb: tuple[int, int, int],
) -> None:
    x0 = pad + gx * pitch
    y0 = pad + gy * pitch
    for y in range(y0, y0 + pitch):
        for x in range(x0, x0 + pitch):
            px[x, y] = (*rgb, 255)


def _frame_miner(
    frame_index: int,
    layout: StripLayout,
    *,
    baseline_shift: int = 0,
    palette_swap: bool = False,
    subtle: bool = False,
) -> list[list[Cell]]:
    """Simple standing miner: feet on bottom row, optional torso bob."""
    grid = [[None for _ in range(layout.frame_w)] for _ in range(layout.frame_h)]
    foot = layout.frame_h - 2 if baseline_shift else layout.frame_h - 1
    body_rgb = (90, 140, 80) if not palette_swap else (200, 90, 60)
    helm_rgb = (70, 110, 160)
    pick_rgb = (120, 90, 50)
    cx = layout.frame_w // 2

    for x in range(cx - 2, cx + 3):
        if 0 <= x < layout.frame_w and 0 <= foot < layout.frame_h:
            grid[foot][x] = body_rgb
    bob = 0 if subtle else frame_index % 2
    torso_top = layout.frame_h - 6 - bob
    for y in range(torso_top, foot):
        for x in range(cx - 1, cx + 2):
            grid[y][x] = body_rgb
    helm_y = torso_top - 2
    for y in range(helm_y, torso_top):
        for x in range(cx - 1, cx + 2):
            grid[y][x] = helm_rgb
    if not subtle:
        arm_y = torso_top + 1
        pick_x = cx + 2 + (frame_index % 2)
        if 0 <= pick_x < layout.frame_w:
            grid[arm_y][pick_x] = pick_rgb
            if arm_y + 1 < layout.frame_h:
                grid[arm_y + 1][pick_x] = pick_rgb
    else:
        pick_x = cx + 2
        if 0 <= pick_x < layout.frame_w:
            grid[torso_top + 1][pick_x] = pick_rgb
    return grid


def render_logical_strip(
    layout: StripLayout,
    scenario: str,
) -> Image.Image:
    """Rasterize a logical strip to a large magenta PNG for recovery testing."""
    strip_w = layout.strip_width()
    strip_h = layout.frame_h
    pad = layout.margin_cells * layout.pitch_px
    pitch = layout.pitch_px
    img_w = strip_w * pitch + pad * 2
    img_h = strip_h * pitch + pad * 2
    im = Image.new("RGBA", (img_w, img_h), (*acquire.MAGENTA, 255))
    px = im.load()

    for fi in range(layout.frame_count):
        shift = 1 if scenario == "baseline_fail" and fi >= 2 else 0
        swap = scenario == "palette_fail" and fi >= 3
        subtle = scenario == "pass"
        frame = _frame_miner(
            fi, layout, baseline_shift=shift, palette_swap=swap, subtle=subtle
        )
        origin_gx = fi * (layout.frame_w + layout.gutter)
        for gy in range(layout.frame_h):
            for gx in range(layout.frame_w):
                rgb = frame[gy][gx]
                if rgb is None:
                    continue
                _draw_block(px, origin_gx + gx, gy, pitch, pad, rgb)

    if scenario == "jitter_fail":
        # Scramble a vertical band in frame 2 after rasterize — simulates bad coherence
        fx = 2 * (layout.frame_w + layout.gutter) + 4
        for gy in range(8, 14):
            _draw_block(px, fx + 3, gy, pitch, pad, (255, 128, 0))

    return im


def write_synthetic_fixture(
    out_path: pathlib.Path,
    layout: StripLayout,
    scenario: str,
) -> pathlib.Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = render_logical_strip(layout, scenario)
    im.save(out_path)
    return out_path


DEFAULT_LAYOUT = StripLayout()
