"""Strip animation ingest — pure logic for the underline prototype.

Recovers a wide logical grid from one provider render, slices into frames, and emits a
deterministic coherence report. Grid recovery uses vendored pipeline primitives; no I/O here.
"""

from __future__ import annotations

import pathlib
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from PIL import Image

from pipeline.gate_evidence import EvidenceError, load_acceptance_profiles, load_manifest
from pipeline.numeric_policy import canonical_metric, metric_passes
from pipeline.recovery import (
    MAGENTA,
    MIN_GRID_SCORE,
    detect_pitch,
    key,
    raw_clipping,
    raw_gates,
    sample_cells,
)

Cell = tuple[int, int, int] | None
MIN_LONG_AXIS = 20
DEFAULT_MAX_PALETTE = 16
MERGE_DIST_RGB = 36  # collapse anti-aliased neighbors before palette build
PROVIDER_MERGE_DIST_RGB = 64

REGISTRATION_SPAN = 1
# Wide scan for displacement evidence — NOT registration jitter absorption.
DISPLACEMENT_PROBE_SPAN = 4
DISPLACEMENT_MIN_MAGNITUDE = 2
# Residual |in+out| tolerance (Chebyshev) — exact pairing is too brittle at wide scan.
DISPLACEMENT_PAIR_TOLERANCE = 1
# Derived 2026-07-26 — floor(min applicable airborne margin 0.0164) − 0.001.
MIN_ALIGNMENT_SHARPNESS_AIRBORNE = 0.015

Facing = Literal["fixed", "free"]
Outcome = Literal["PASS", "REVIEW", "FAIL"]

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_PROFILES_PATH = _REPO_ROOT / "gate-controls" / "acceptance-profiles.json"
_DEFAULT_MANIFEST_PATH = _REPO_ROOT / "gate-controls" / "manifest.json"

_GATE_BUDGET_ATTR = {
    "silhouette_budget": "max_silhouette",
    "loop_closure_pass": "max_loop",
    "palette_drift_pass": "max_drift",
    "min_pair_cohort_pass": "max_min_pair",
}


@dataclass(frozen=True)
class GatePolicy:
    status: str
    budget: float | None
    hard_fail: float | None
    active_promotion: str | None = None


@dataclass(frozen=True)
class ClassBudget:
    max_silhouette: float | None
    max_loop: float | None
    max_drift: float
    max_min_pair: float | None
    grounded: bool
    loops: bool
    facing: Facing
    min_alignment_sharpness: float | None = None


_CLASS_META: dict[str, dict[str, Any]] = {
    "idle": {
        "grounded": True,
        "loops": True,
        "facing": "free",
        "min_alignment_sharpness": None,
    },
    "blob_idle": {
        "grounded": True,
        "loops": True,
        "facing": "free",
        "min_alignment_sharpness": None,
    },
    "walk": {
        "grounded": True,
        "loops": True,
        "facing": "fixed",
        "min_alignment_sharpness": None,
    },
    "swing": {
        "grounded": True,
        "loops": False,
        "facing": "fixed",
        "min_alignment_sharpness": None,
    },
    "airborne": {
        "grounded": False,
        "loops": True,
        "facing": "free",
        "min_alignment_sharpness": MIN_ALIGNMENT_SHARPNESS_AIRBORNE,
    },
    "emissive": {
        "grounded": True,
        "loops": True,
        "facing": "free",
        "min_alignment_sharpness": None,
    },
}


def evaluate_continuous_gate_outcome(policy: GatePolicy, metric: float) -> Outcome:
    """Tri-state outcome for a continuous Gate under its Acceptance profile."""
    canonical = canonical_metric(metric)
    budget = policy.budget
    if budget is None:
        raise ValueError("continuous gate policy requires a Budget")
    if policy.status == "SEPARATED":
        if canonical <= budget:
            return "PASS"
        if policy.hard_fail is not None and canonical >= policy.hard_fail:
            return "FAIL"
        return "REVIEW"
    if policy.status == "UNSEPARATED":
        return "PASS" if canonical <= budget else "REVIEW"
    raise ValueError(f"unsupported gate policy status {policy.status!r}")


def _gate_outcome_record(policy: GatePolicy, metric: float) -> dict[str, Any]:
    canonical = canonical_metric(metric)
    return {
        "acceptance_status": policy.status,
        "metric": canonical,
        "budget": policy.budget,
        "hard_fail": policy.hard_fail if policy.status == "SEPARATED" else None,
        "outcome": evaluate_continuous_gate_outcome(policy, metric),
    }


def _aggregate_outcome(
    *,
    structural_fail: bool,
    gate_outcomes: dict[str, dict[str, Any]],
) -> Outcome:
    if structural_fail:
        return "FAIL"
    outcomes = [row["outcome"] for row in gate_outcomes.values()]
    if any(outcome == "FAIL" for outcome in outcomes):
        return "FAIL"
    if any(outcome == "REVIEW" for outcome in outcomes):
        return "REVIEW"
    return "PASS"


def _validate_separated_promotions(
    gate_policies: dict[str, dict[str, GatePolicy]],
    *,
    manifest_path: pathlib.Path,
) -> None:
    manifest = load_manifest(manifest_path)
    promotions = {promo.id: promo for promo in manifest.promotions}
    specifications = {
        (spec.motion_class, spec.target_gate): spec for spec in manifest.specifications
    }
    for motion_class, gates in gate_policies.items():
        for gate_name, policy in gates.items():
            if policy.status != "SEPARATED" or policy.active_promotion is None:
                continue
            promo = promotions.get(policy.active_promotion)
            if promo is None:
                raise ValueError(
                    f"missing Promotion {policy.active_promotion!r} for "
                    f"{motion_class}/{gate_name}"
                )
            if promo.status != "ACTIVE":
                raise ValueError(
                    f"Promotion {policy.active_promotion!r} not ACTIVE "
                    f"(status={promo.status!r}) for {motion_class}/{gate_name}"
                )
            spec = specifications.get((motion_class, gate_name))
            if spec is None:
                raise ValueError(
                    f"missing specification for {motion_class}/{gate_name}"
                )
            if spec.active_promotion != policy.active_promotion:
                raise ValueError(
                    f"alternate Promotion for {motion_class}/{gate_name}: profile "
                    f"references {policy.active_promotion!r} but manifest spec "
                    f"has {spec.active_promotion!r}"
                )


def build_runtime_acceptance_policy(
    *,
    profiles_path: pathlib.Path | None = None,
    manifest_path: pathlib.Path | None = None,
) -> tuple[dict[str, ClassBudget], dict[str, dict[str, GatePolicy]]]:
    """Load Acceptance profiles and project runtime Budgets and Gate policies."""
    profiles_path = profiles_path or _DEFAULT_PROFILES_PATH
    manifest_path = manifest_path or _DEFAULT_MANIFEST_PATH
    try:
        profiles = load_acceptance_profiles(profiles_path)
    except EvidenceError as exc:
        raise ValueError(str(exc)) from exc

    gate_policies: dict[str, dict[str, GatePolicy]] = {}
    motion_classes: dict[str, ClassBudget] = {}
    for motion_class, meta in _CLASS_META.items():
        profile_gates = profiles.profiles.get(motion_class)
        if profile_gates is None:
            raise ValueError(f"missing Acceptance profile for motion class {motion_class!r}")
        class_policies: dict[str, GatePolicy] = {}
        budget_kwargs: dict[str, float | None] = {
            "max_silhouette": None,
            "max_loop": None,
            "max_drift": None,
            "max_min_pair": None,
        }
        for gate_name, gate in profile_gates.items():
            class_policies[gate_name] = GatePolicy(
                status=gate.status,
                budget=gate.budget,
                hard_fail=gate.hard_fail,
                active_promotion=gate.active_promotion,
            )
            attr = _GATE_BUDGET_ATTR.get(gate_name)
            if attr is not None:
                budget_kwargs[attr] = gate.budget if gate.status != "INAPPLICABLE" else None
        if budget_kwargs["max_drift"] is None:
            raise ValueError(f"{motion_class}: palette_drift_pass must be applicable")
        gate_policies[motion_class] = class_policies
        motion_classes[motion_class] = ClassBudget(
            max_silhouette=budget_kwargs["max_silhouette"],
            max_loop=budget_kwargs["max_loop"],
            max_drift=budget_kwargs["max_drift"],
            max_min_pair=budget_kwargs["max_min_pair"],
            grounded=meta["grounded"],
            loops=meta["loops"],
            facing=meta["facing"],
            min_alignment_sharpness=meta["min_alignment_sharpness"],
        )

    _validate_separated_promotions(gate_policies, manifest_path=manifest_path)
    return motion_classes, gate_policies


MOTION_CLASSES, ACCEPTANCE_GATES = build_runtime_acceptance_policy()


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
    outcome: Outcome

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
            "outcome": self.outcome,
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


def _occupancy_diff_at_shift_2d(
    a: list[list[Cell]],
    b: list[list[Cell]],
    dx: int,
    dy: int,
    *,
    anchor: int | None = None,
) -> tuple[int, int]:
    """Occupancy flips above anchor with b shifted by (dx, dy) relative to a."""
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
            yb, xb = y + dy, x + dx
            if 0 <= yb < len(b) and 0 <= xb < len(b[yb]):
                b_cell = b[yb][xb]
            else:
                b_cell = None
            if a_cell is None and b_cell is None:
                continue
            union_opaque += 1
            if (a_cell is None) != (b_cell is None):
                changed += 1
    return changed, union_opaque


def best_alignment_shift(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = DISPLACEMENT_PROBE_SPAN,
    anchor: int | None = None,
) -> tuple[int, int]:
    """(dx, dy) shifting b relative to a that minimises occupancy diff above anchor.

    Uses a wide scan for displacement evidence. Do not substitute REGISTRATION_SPAN —
    registration minimises shift to absorb jitter; this reads shift as evidence.
    """
    best_dx = 0
    best_dy = 0
    best_frac = float("inf")
    for dy in range(-span, span + 1):
        for dx in range(-span, span + 1):
            changed, union = _occupancy_diff_at_shift_2d(
                a, b, dx, dy, anchor=anchor
            )
            frac = changed / union if union else 0.0
            if frac < best_frac:
                best_frac = frac
                best_dx = dx
                best_dy = dy
    return best_dx, best_dy


def alignment_shift_scores(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = DISPLACEMENT_PROBE_SPAN,
    anchor: int | None = None,
) -> list[tuple[int, int, float]]:
    """All (dx, dy, frac) candidates sorted best-first."""
    scores: list[tuple[int, int, float]] = []
    for dy in range(-span, span + 1):
        for dx in range(-span, span + 1):
            changed, union = _occupancy_diff_at_shift_2d(
                a, b, dx, dy, anchor=anchor
            )
            frac = changed / union if union else 0.0
            scores.append((dx, dy, frac))
    scores.sort(key=lambda row: row[2])
    return scores


def transition_sharpness_margin(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = DISPLACEMENT_PROBE_SPAN,
    anchor: int | None = None,
) -> dict[str, Any]:
    """Best-vs-next-best distinct shift gap — 0.0 means a degenerate minimum."""
    scores = alignment_shift_scores(a, b, span=span, anchor=anchor)
    best_dx, best_dy, best_frac = scores[0]
    second_frac: float | None = None
    for dx, dy, frac in scores[1:]:
        if (dx, dy) != (best_dx, best_dy):
            second_frac = frac
            break
    margin = round(second_frac - best_frac, 4) if second_frac is not None else 0.0
    return {
        "best_shift": (best_dx, best_dy),
        "best_frac": round(best_frac, 4),
        "margin": margin,
    }


def registration_shift_scores(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = REGISTRATION_SPAN,
    anchor: int | None = None,
) -> list[tuple[int, float]]:
    """1D registration scan — same machinery silhouette_diff uses."""
    scores: list[tuple[int, float]] = []
    for dx in range(-span, span + 1):
        changed, union = _silhouette_diff_at_shift(a, b, dx, anchor=anchor)
        frac = changed / union if union else 0.0
        scores.append((dx, frac))
    scores.sort(key=lambda row: row[1])
    return scores


def registration_sharpness_margin(
    a: list[list[Cell]],
    b: list[list[Cell]],
    *,
    span: int = REGISTRATION_SPAN,
    anchor: int | None = None,
) -> dict[str, Any]:
    """Registration-span sharpness — diagnostic for silhouette_diff well-posedness."""
    scores = registration_shift_scores(a, b, span=span, anchor=anchor)
    best_dx, best_frac = scores[0]
    second_frac: float | None = None
    for dx, frac in scores[1:]:
        if dx != best_dx:
            second_frac = frac
            break
    margin = round(second_frac - best_frac, 4) if second_frac is not None else 0.0
    return {
        "best_shift": (best_dx, 0),
        "best_frac": round(best_frac, 4),
        "margin": margin,
    }


def alignment_sharpness_report(
    frames: list[list[list[Cell]]],
    *,
    loops: bool,
    anchor: int | None = None,
    span: int = DISPLACEMENT_PROBE_SPAN,
) -> dict[str, Any]:
    """Per-transition displacement-span sharpness; min_margin drives applicability."""
    n = len(frames)
    if n < 2:
        return {"transitions": [], "min_margin": 0.0, "worst_pair": None}
    if loops:
        pairs = [(i, (i + 1) % n) for i in range(n)]
    else:
        pairs = [(i, i + 1) for i in range(n - 1)]
    transitions: list[dict[str, Any]] = []
    margins: list[float] = []
    for i, j in pairs:
        row = transition_sharpness_margin(
            frames[i], frames[j], span=span, anchor=anchor
        )
        row["pair"] = [i, j]
        transitions.append(row)
        margins.append(row["margin"])
    worst_idx = min(range(len(margins)), key=lambda k: margins[k])
    return {
        "transitions": transitions,
        "min_margin": round(min(margins), 4) if margins else 0.0,
        "worst_pair": transitions[worst_idx]["pair"] if transitions else None,
    }


def registration_sharpness_report(
    frames: list[list[list[Cell]]],
    *,
    loops: bool,
    anchor: int | None = None,
) -> dict[str, Any]:
    """Registration-span sharpness across transitions — corpus diagnostic."""
    n = len(frames)
    if n < 2:
        return {"transitions": [], "min_margin": 0.0, "worst_pair": None}
    if loops:
        pairs = [(i, (i + 1) % n) for i in range(n)]
    else:
        pairs = [(i, i + 1) for i in range(n - 1)]
    transitions: list[dict[str, Any]] = []
    margins: list[float] = []
    for i, j in pairs:
        row = registration_sharpness_margin(frames[i], frames[j], anchor=anchor)
        row["pair"] = [i, j]
        transitions.append(row)
        margins.append(row["margin"])
    worst_idx = min(range(len(margins)), key=lambda k: margins[k])
    return {
        "transitions": transitions,
        "min_margin": round(min(margins), 4) if margins else 0.0,
        "worst_pair": transitions[worst_idx]["pair"] if transitions else None,
    }


def displacement_gate_result(
    frames: list[list[list[Cell]]],
    budget: ClassBudget,
    *,
    anchor: int | None,
) -> dict[str, Any]:
    """displacement_pass: True/False when measurable, None when inapplicable."""
    if budget.min_alignment_sharpness is None:
        return {
            "displacement_pass": None,
            "displacement_inapplicable": False,
            "displacement_reason": None,
            "alignment_sharpness": None,
            "displacement_flags": [],
        }
    sharpness = alignment_sharpness_report(frames, loops=budget.loops, anchor=anchor)
    min_margin = sharpness["min_margin"]
    threshold = budget.min_alignment_sharpness
    if min_margin < threshold:
        worst = sharpness["worst_pair"]
        pair_label = f"{worst[0]}→{worst[1]}" if worst else "?"
        return {
            "displacement_pass": None,
            "displacement_inapplicable": True,
            "displacement_reason": (
                f"degenerate alignment minimum (margin {min_margin:.4f} at "
                f"{pair_label}); displacement undecidable"
            ),
            "alignment_sharpness": sharpness,
            "displacement_flags": [],
        }
    flags = antisymmetric_displacement_flags(
        frames, loops=budget.loops, anchor=anchor
    )
    return {
        "displacement_pass": len(flags) == 0,
        "displacement_inapplicable": False,
        "displacement_reason": None,
        "alignment_sharpness": sharpness,
        "displacement_flags": flags,
    }


def shift_magnitude(dx: int, dy: int) -> int:
    """Chebyshev magnitude — max(|dx|, |dy|)."""
    return max(abs(dx), abs(dy))


def shifts_antisymmetric(
    in_dx: int,
    in_dy: int,
    out_dx: int,
    out_dy: int,
    *,
    tolerance: int = DISPLACEMENT_PAIR_TOLERANCE,
) -> bool:
    """True when in+out residuals are within tolerance cells (approximate negation)."""
    return shift_magnitude(in_dx + out_dx, in_dy + out_dy) <= tolerance


def displacement_frame_indices(frame_count: int, *, loops: bool) -> range:
    """Frame indices to scan — all frames when looping, interior only otherwise."""
    if frame_count < 3:
        return range(0)
    return range(frame_count) if loops else range(1, frame_count - 1)


def quantize_motion_frames(
    frames: list[list[list[Cell]]],
    motion_class: str,
    *,
    max_colors: int = DEFAULT_MAX_PALETTE,
    merge_dist: int = PROVIDER_MERGE_DIST_RGB,
    anchor_row: int | None = None,
) -> tuple[list[list[list[Cell]]], int | None]:
    """Shared palette quantize + silhouette anchor, matching coherence_split."""
    if motion_class not in MOTION_CLASSES:
        raise ValueError(f"unknown motion_class: {motion_class!r}")
    budget = MOTION_CLASSES[motion_class]
    rgbs = collect_opaque_rgbs(frames)
    palette, _stats = build_shared_palette(
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
    if budget.grounded:
        baselines = [baseline_row(f) for f in q]
        anchor = anchor_row if anchor_row is not None else baselines[0]
        sil_anchor: int | None = anchor
    else:
        sil_anchor = len(q[0]) if q else 0
    return q, sil_anchor


def adjacent_transition_shifts(
    frames: list[list[list[Cell]]],
    *,
    span: int = DISPLACEMENT_PROBE_SPAN,
    anchor: int | None = None,
) -> list[dict[str, Any]]:
    """Best-alignment shift for each forward adjacent pair i→i+1 (b shifted vs a)."""
    rows: list[dict[str, Any]] = []
    for i in range(len(frames) - 1):
        dx, dy = best_alignment_shift(
            frames[i], frames[i + 1], span=span, anchor=anchor
        )
        rows.append(
            {
                "from": i,
                "to": i + 1,
                "dx": dx,
                "dy": dy,
                "magnitude": shift_magnitude(dx, dy),
            }
        )
    return rows


def antisymmetric_displacement_flags(
    frames: list[list[list[Cell]]],
    *,
    loops: bool = False,
    min_magnitude: int = DISPLACEMENT_MIN_MAGNITUDE,
    pair_tolerance: int = DISPLACEMENT_PAIR_TOLERANCE,
    span: int = DISPLACEMENT_PROBE_SPAN,
    anchor: int | None = None,
) -> list[dict[str, Any]]:
    """Frames where in/out shifts are approximately opposite with |in| ≥ min_magnitude."""
    flags: list[dict[str, Any]] = []
    n = len(frames)
    for k in displacement_frame_indices(n, loops=loops):
        prev_k = (k - 1) % n if loops else k - 1
        next_k = (k + 1) % n if loops else k + 1
        in_dx, in_dy = best_alignment_shift(
            frames[prev_k], frames[k], span=span, anchor=anchor
        )
        out_dx, out_dy = best_alignment_shift(
            frames[k], frames[next_k], span=span, anchor=anchor
        )
        mag = shift_magnitude(in_dx, in_dy)
        if mag < min_magnitude:
            continue
        if shifts_antisymmetric(
            in_dx, in_dy, out_dx, out_dy, tolerance=pair_tolerance
        ):
            flags.append(
                {
                    "frame": k,
                    "in_shift": (in_dx, in_dy),
                    "out_shift": (out_dx, out_dy),
                    "magnitude": mag,
                }
            )
    return flags


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
    max_min_pair = budget.max_min_pair

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

    baseline_row_inapplicable = not grounded
    baseline_row_reason = (
        "motion class is ungrounded (grounded: false)" if not grounded else None
    )

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
            loop_closure_pass = metric_passes(frac, max_loop_diff)
            loop["pass"] = loop_closure_pass

    drift = palette_drift(q)
    worst_drift = max((d["tv"] for d in drift), default=0.0)
    pairwise = silhouette_pairwise(q, anchor=sil_anchor)
    adjacent_max = max((row["frac"] for row in adjacent), default=0.0)

    silhouette_budget: bool | None = None
    if max_silhouette_diff is not None:
        silhouette_budget = all(
            metric_passes(row["frac"], max_silhouette_diff) for row in adjacent
        )

    min_pair_cohort_pass: bool | None = None
    if budget.loops and max_min_pair is not None:
        min_pair_cohort_pass = metric_passes(pairwise["min_pair"], max_min_pair)

    disp = displacement_gate_result(q, budget, anchor=sil_anchor)

    gate_policies = ACCEPTANCE_GATES[motion_class]
    gate_outcomes: dict[str, dict[str, Any]] = {}
    caveats: list[str] = []

    sil_policy = gate_policies.get("silhouette_budget")
    if sil_policy is not None and sil_policy.status != "INAPPLICABLE":
        gate_outcomes["silhouette_budget"] = _gate_outcome_record(
            sil_policy, adjacent_max
        )

    loop_policy = gate_policies.get("loop_closure_pass")
    if (
        loop is not None
        and loop_policy is not None
        and loop_policy.status != "INAPPLICABLE"
    ):
        gate_outcomes["loop_closure_pass"] = _gate_outcome_record(
            loop_policy, loop["frac"]
        )

    drift_policy = gate_policies.get("palette_drift_pass")
    if drift_policy is not None and drift_policy.status != "INAPPLICABLE":
        gate_outcomes["palette_drift_pass"] = _gate_outcome_record(
            drift_policy, worst_drift
        )

    min_pair_policy = gate_policies.get("min_pair_cohort_pass")
    if (
        min_pair_policy is not None
        and min_pair_policy.status != "INAPPLICABLE"
    ):
        gate_outcomes["min_pair_cohort_pass"] = _gate_outcome_record(
            min_pair_policy, pairwise["min_pair"]
        )

    disp_policy = gate_policies.get("displacement_pass")
    if disp_policy is not None and disp_policy.status != "INAPPLICABLE":
        if disp["displacement_pass"] is None:
            reason = disp.get("displacement_reason")
            if reason:
                caveats.append(reason)
        elif disp["displacement_pass"] is True:
            gate_outcomes["displacement_pass"] = {
                "acceptance_status": disp_policy.status,
                "metric": True,
                "budget": disp_policy.budget,
                "hard_fail": None,
                "outcome": "PASS",
            }
        else:
            gate_outcomes["displacement_pass"] = {
                "acceptance_status": disp_policy.status,
                "metric": False,
                "budget": disp_policy.budget,
                "hard_fail": None,
                "outcome": "REVIEW",
            }

    structural_fail = not (len(dims) == 1) or (
        grounded and baseline_stable is False
    )
    outcome = _aggregate_outcome(
        structural_fail=structural_fail,
        gate_outcomes=gate_outcomes,
    )

    gates = {
        "quantize": {**stats, "mode": "quantize-shared", "merge_dist": merge_dist},
        "motion_class": motion_class,
        "dimension_parity": len(dims) == 1,
        "dimensions": sorted(dims),
        "grounded": grounded,
        "anchor_row": anchor,
        "baseline_row_stable": baseline_stable,
        "baseline_row_inapplicable": baseline_row_inapplicable,
        "baseline_row_reason": baseline_row_reason,
        "baseline_rows": baselines,
        "silhouette_adjacent": adjacent,
        "silhouette_adjacent_max": adjacent_max,
        "silhouette_pairwise": pairwise,
        "silhouette_budget": silhouette_budget,
        "min_pair_cohort_pass": min_pair_cohort_pass,
        "loop_closure": loop,
        "loop_closure_pass": loop_closure_pass,
        "palette_drift": drift,
        "worst_palette_drift": worst_drift,
        "palette_drift_pass": metric_passes(worst_drift, max_palette_drift),
        "alignment_sharpness": disp["alignment_sharpness"],
        "displacement_flags": disp["displacement_flags"],
        "displacement_pass": disp["displacement_pass"],
        "displacement_inapplicable": disp["displacement_inapplicable"],
        "displacement_reason": disp["displacement_reason"],
        "budgets": {
            "silhouette": max_silhouette_diff,
            "loop": max_loop_diff,
            "palette_drift": max_palette_drift,
            "min_pair": max_min_pair,
            "min_alignment_sharpness": budget.min_alignment_sharpness,
        },
        "gate_outcomes": gate_outcomes,
        "caveats": caveats,
        "outcome": outcome,
    }
    gates["pass"] = outcome == "PASS"
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
    gate_errs = raw_gates(raw_path)
    gate_errs = [e for e in gate_errs if "missing provenance" not in e]
    if gate_errs:
        raise ValueError("; ".join(gate_errs))

    clip = raw_clipping(raw_path)
    if clip:
        raise ValueError("; ".join(clip))

    src, fg, bbox = key(raw_path)
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
    pitch_y_fit = detect_pitch(src, fg, "y", band_lo, band_hi)
    pitch_x_fit = detect_pitch(src, fg, "x", band_lo, band_hi)
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

    cells = sample_cells(src, fg, bbox, pitch_x, pitch_y)
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
            "outcome": "FAIL",
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
    outcome: Outcome = coherence.get("outcome", "FAIL")
    pass_ = pitch_ok and outcome == "PASS"

    return IngestResult(
        layout=layout,
        source=str(raw_path),
        recovered=recovered,
        slice_meta=slice_meta,
        coherence=coherence,
        pass_=pass_,
        outcome=outcome if pitch_ok else "FAIL",
    )


def provider_probe_layout(layout: StripLayout) -> StripLayout:
    """Layout for provider recovery with margin stripped (matches inbox corpus tools)."""
    return StripLayout(
        frame_w=layout.frame_w,
        frame_h=layout.frame_h,
        frame_count=layout.frame_count,
        gutter=layout.gutter,
        pitch_px=layout.pitch_px,
        margin_cells=0,
    )


def load_provider_frames(
    raw_path: pathlib.Path,
    layout: StripLayout,
) -> list[list[list[Cell]]] | None:
    """Recover and pitch-slice a provider strip without running coherence gates."""
    probe = provider_probe_layout(layout)
    cells, _ = recover_strip_cells(raw_path, probe)
    frames, _ = slice_frames_pitch(cells, frame_count=layout.frame_count)
    return frames


def coherence_gate_status(
    coherence: dict[str, Any],
    gate_key: str,
    *,
    inapplicable_key: str | None = None,
    reason_key: str | None = None,
    budget_key: str | None = None,
) -> dict[str, Any]:
    gate_outcomes = coherence.get("gate_outcomes", {})
    if gate_key in gate_outcomes:
        row = gate_outcomes[gate_key]
        return {
            "status": row["outcome"].lower(),
            "value": row.get("metric"),
            "budget": row.get("budget"),
            "hard_fail": row.get("hard_fail"),
            "acceptance_status": row.get("acceptance_status"),
            "outcome": row["outcome"],
        }
    value = coherence.get(gate_key)
    budgets = coherence.get("budgets", {})
    if inapplicable_key and coherence.get(inapplicable_key):
        return {
            "status": "inapplicable",
            "value": value,
            "reason": coherence.get(reason_key),
        }
    if value is None and budget_key and budgets.get(budget_key) is None:
        return {
            "status": "inapplicable",
            "value": None,
            "reason": f"{budget_key} budget is None for this motion class",
        }
    if value is None:
        return {"status": "inapplicable", "value": None, "reason": None}
    return {"status": "pass" if value else "fail", "value": value}


def format_coherence_gate_status(label: str, status: dict[str, Any]) -> str:
    state = status["status"]
    if state == "inapplicable":
        reason = status.get("reason")
        detail = f"inapplicable — {reason}" if reason else "inapplicable"
        return f"  {label}: {detail}"
    if state in {"pass", "review", "fail"}:
        return f"  {label}: {state.upper()}"
    verdict = "pass" if state == "pass" else "FAIL"
    return f"  {label}: {verdict}"


def format_coherence_split_report(coherence: dict[str, Any]) -> list[str]:
    """Human-readable gate lines for a coherence_split dict."""
    lines: list[str] = []
    if "reason" in coherence and "silhouette_adjacent" not in coherence:
        lines.append(f"  reason: {coherence['reason']}")
        return lines

    lines.append(
        format_coherence_gate_status(
            "max_silhouette",
            coherence_gate_status(coherence, "silhouette_budget", budget_key="silhouette"),
        )
    )
    lines.append(
        format_coherence_gate_status(
            "displacement_pass",
            coherence_gate_status(
                coherence,
                "displacement_pass",
                inapplicable_key="displacement_inapplicable",
                reason_key="displacement_reason",
            ),
        )
    )
    lines.append(
        format_coherence_gate_status(
            "baseline_row_stable",
            coherence_gate_status(
                coherence,
                "baseline_row_stable",
                inapplicable_key="baseline_row_inapplicable",
                reason_key="baseline_row_reason",
            ),
        )
    )
    for key in (
        "dimension_parity",
        "min_pair_cohort_pass",
        "loop_closure_pass",
        "palette_drift_pass",
    ):
        if key not in coherence:
            continue
        gate_value = coherence[key]
        gate_outcomes = coherence.get("gate_outcomes", {})
        if key in gate_outcomes:
            lines.append(f"  {key}: {gate_outcomes[key]['outcome']}")
            continue
        if gate_value is None:
            lines.append(f"  {key}: inapplicable")
        else:
            lines.append(f"  {key}: {'pass' if gate_value else 'FAIL'}")
    for row in coherence.get("silhouette_adjacent", []):
        lines.append(
            f"  silhouette {row['pair']}: "
            f"changed={row['changed_cells']}/{row['union_opaque']} "
            f"({row['frac']:.1%})"
        )
    for row in coherence.get("palette_drift", []):
        lines.append(f"  palette drift {row['pair']}: {row['tv']:.1%}")
    loop = coherence.get("loop_closure")
    if loop:
        loop_pass = loop.get("pass")
        pass_label = loop_pass if loop_pass is not None else "n/a"
        lines.append(
            f"  loop {loop['pair']}: "
            f"changed={loop['changed_cells']}/{loop['union_opaque']} "
            f"({loop['frac']:.1%}) pass={pass_label}"
        )
    return lines


def coherence_split_json_gates(coherence: dict[str, Any]) -> dict[str, Any]:
    gate_outcomes = coherence.get("gate_outcomes", {})
    return {
        "max_silhouette": coherence_gate_status(
            coherence, "silhouette_budget", budget_key="silhouette"
        ),
        "displacement_pass": coherence_gate_status(
            coherence,
            "displacement_pass",
            inapplicable_key="displacement_inapplicable",
            reason_key="displacement_reason",
        ),
        "baseline_row_stable": coherence_gate_status(
            coherence,
            "baseline_row_stable",
            inapplicable_key="baseline_row_inapplicable",
            reason_key="baseline_row_reason",
        ),
        "gate_outcomes": gate_outcomes,
        "outcome": coherence.get("outcome"),
        "caveats": coherence.get("caveats", []),
    }


def format_provider_ingest_report(result: IngestResult) -> str:
    """Human report for provider strips (pitch slice; no nominal raster match)."""
    lines: list[str] = []
    lines.append(f"Source  {result.source}")
    lines.append(
        f"Layout  {result.layout.frame_count}×{result.layout.frame_w}×"
        f"{result.layout.frame_h}  gutter={result.layout.gutter}  "
        f"strip_w={result.layout.strip_width()}"
    )
    rec = result.recovered
    grid = rec["grid"]
    lines.append(
        f"Recovered  grid {grid[0]}×{grid[1]}  "
        f"pitch x={rec['pitch_x']['score']:.3f} y={rec['pitch_y']['score']:.3f}"
    )
    sl = result.slice_meta
    grid_w, grid_h = sl["grid"]
    lines.append(
        f"Slice  mode=pitch  grid {grid_w}×{grid_h}  "
        f"pitch={sl.get('pitch')}  frames={result.layout.frame_count}"
    )
    lines.append("Coherence")
    lines.extend(format_coherence_split_report(result.coherence))
    lines.append("")
    lines.append(f"Overall  {result.outcome}")
    return "\n".join(lines)


def format_synthetic_ingest_report(result: IngestResult) -> str:
    """Human report for synthetic fixtures (exact raster dimensions)."""
    lines: list[str] = []
    lines.append(f"Source  {result.source}")
    lines.append(
        f"Layout  {result.layout.frame_count}×{result.layout.frame_w}×"
        f"{result.layout.frame_h}  gutter={result.layout.gutter}  "
        f"strip_w={result.layout.strip_width()}"
    )
    rec = result.recovered
    lines.append(
        f"Recovered  grid {rec['grid']}  expected {rec['expected_grid']}  "
        f"pitch x={rec['pitch_x']['score']:.3f} y={rec['pitch_y']['score']:.3f}"
    )
    sl = result.slice_meta
    lines.append(
        f"Slice  raster_match={sl.get('raster_match')}  "
        f"shape_match={sl.get('shape_match')}  "
        f"grid={sl.get('grid')} expected_raster={sl.get('expected_raster')}"
    )
    lines.append("Coherence")
    lines.extend(format_coherence_split_report(result.coherence))
    lines.append("")
    lines.append(f"Overall  {result.outcome}")
    return "\n".join(lines)


def format_ingest_report(result: IngestResult) -> str:
    if result.slice_meta.get("mode") == "pitch":
        return format_provider_ingest_report(result)
    return format_synthetic_ingest_report(result)


def ingest_strip_provider(
    raw_path: pathlib.Path,
    layout: StripLayout,
    *,
    motion_class: str = "idle",
) -> IngestResult:
    """Recover full raster and slice at uniform pitch (provider slop tolerant)."""
    probe = provider_probe_layout(layout)
    cells, recovered = recover_strip_cells(raw_path, probe)
    frames, slice_meta = slice_frames_pitch(cells, frame_count=layout.frame_count)
    if frames is None:
        coherence = {
            "pass": False,
            "outcome": "FAIL",
            "reason": slice_meta.get("reason", "auto-slice failed"),
            "slice": slice_meta,
        }
    else:
        coherence = coherence_split(frames, motion_class=motion_class)

    pitch_ok = (
        recovered["pitch_x"]["score"] >= MIN_GRID_SCORE
        or recovered["pitch_y"]["score"] >= MIN_GRID_SCORE
    )
    outcome: Outcome = coherence.get("outcome", "FAIL")
    pass_ = pitch_ok and outcome == "PASS"

    return IngestResult(
        layout=layout,
        source=str(raw_path),
        recovered=recovered,
        slice_meta=slice_meta,
        coherence=coherence,
        pass_=pass_,
        outcome=outcome if pitch_ok else "FAIL",
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
    im = Image.new("RGBA", (img_w, img_h), (*MAGENTA, 255))
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


def export_frames(
    frames: list[list[list[Cell]]],
    out_dir: pathlib.Path,
    stem: str,
    *,
    frame_w: int = 16,
    frame_h: int = 24,
) -> list[pathlib.Path]:
    """Write one RGBA PNG per logical frame; transparent cells use magenta alpha 0."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[pathlib.Path] = []
    for index, frame in enumerate(frames):
        logical = [row[:frame_w] for row in frame[:frame_h]]
        height = len(logical)
        width = len(logical[0]) if logical else 0
        image = Image.new("RGBA", (width, height), (*MAGENTA, 0))
        pixels = image.load()
        for y in range(height):
            for x in range(width):
                rgb = logical[y][x]
                if rgb is not None:
                    pixels[x, y] = (*rgb, 255)
        path = out_dir / f"{stem}-f{index}.png"
        image.save(path)
        paths.append(path)
    return paths


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
