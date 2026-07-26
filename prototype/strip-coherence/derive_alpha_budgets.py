#!/usr/bin/env python3
"""Derive α=0.5 Budgets for Separated pairs and C5 Budgets for Unseparated pairs.

Evidence command for wayfinder #29. Prints machine-readable tables; does not
mutate runtime MOTION_CLASSES (that is a later implementation wave).
"""

from __future__ import annotations

import json
import math
import pathlib

import corpus
from pipeline import strip as S

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "prompts" / "manifest.json"
INBOX = HERE / "inbox"
GC_MANIFEST = ROOT / "gate-controls" / "manifest.json"
ACCEPTANCE = ROOT / "gate-controls" / "acceptance-profiles.json"

EXTRA_GOOD: dict[str, list[str]] = {"idle": ["miner-idle-strip.png"]}
NEGATIVE_IDS = {
    s["id"]
    for s in json.loads(MANIFEST.read_text())["samples"]
    if s.get("contract_expect") == "FAIL"
}

GATE_FIELDS = {
    "silhouette_budget": "sil",
    "palette_drift_pass": "drift",
    "loop_closure_pass": "loop",
    "min_pair_cohort_pass": "min_pair",
}

ALPHA = 0.5


def ceil_4(value: float) -> float:
    return math.ceil(value * 10_000) / 10_000


def ceil_001(value: float) -> float:
    return math.ceil(value * 100) / 100


def c5_budget(worst: float) -> float:
    return round(ceil_001(worst) + 0.02, 2)


def alpha_budget(g: float, c: float) -> float:
    return ceil_4(g + ALPHA * (c - g))


def _ingest_metrics(path: pathlib.Path, motion_class: str) -> dict[str, float] | None:
    layout = S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )
    try:
        result = S.ingest_strip_provider(path, layout, motion_class=motion_class)
    except (ValueError, OSError):
        return None
    coh = result.coherence
    if "reason" in coh:
        return None
    sil = max((row["frac"] for row in coh.get("silhouette_adjacent", [])), default=0.0)
    loop = (coh.get("loop_closure") or {}).get("frac", 0.0)
    drift = coh.get("worst_palette_drift", 0.0)
    pairwise = coh.get("silhouette_pairwise") or {}
    return {
        "sil": sil,
        "loop": loop,
        "drift": drift,
        "min_pair": pairwise.get("min_pair", 0.0),
    }


def worst_good() -> dict[str, dict[str, float]]:
    manifest = json.loads(MANIFEST.read_text())
    by_class: dict[str, list[dict[str, float]]] = {}
    for sample in manifest["samples"]:
        path = corpus.find_png(sample["id"])
        if path is None or sample["id"] in NEGATIVE_IDS:
            continue
        if sample.get("contract_expect") != "PASS":
            continue
        metrics = _ingest_metrics(path, sample["motion_class"])
        if metrics is None:
            continue
        by_class.setdefault(sample["motion_class"], []).append(metrics)
    for motion_class, names in EXTRA_GOOD.items():
        for name in names:
            path = INBOX / name
            if not path.exists():
                continue
            metrics = _ingest_metrics(path, motion_class)
            if metrics is not None:
                by_class.setdefault(motion_class, []).append(metrics)
    worst: dict[str, dict[str, float]] = {}
    for motion_class, rows in by_class.items():
        worst[motion_class] = {
            "sil": max(r["sil"] for r in rows),
            "loop": max(r["loop"] for r in rows),
            "drift": max(r["drift"] for r in rows),
            "min_pair": max(r["min_pair"] for r in rows),
        }
    return worst


def control_metrics() -> dict[tuple[str, str], float]:
    gc = json.loads(GC_MANIFEST.read_text())
    promos = {p["id"]: p for p in gc["promotions"]}
    out: dict[tuple[str, str], float] = {}
    for spec in gc["specifications"]:
        promo = promos[spec["active_promotion"]]
        run = json.loads((ROOT / promo["measurement_path"]).read_text())
        gate = spec["target_gate"]
        metric = run["gates"][gate]["metric"]
        if metric is None:
            continue
        key = (spec["motion_class"], gate)
        out[key] = ceil_4(metric)
    return out


def runtime_budget(motion_class: str, gate: str) -> float | None:
    budget = S.MOTION_CLASSES[motion_class]
    return {
        "silhouette_budget": budget.max_silhouette,
        "palette_drift_pass": budget.max_drift,
        "loop_closure_pass": budget.max_loop,
        "min_pair_cohort_pass": budget.max_min_pair,
    }[gate]


def acceptance_status() -> dict[tuple[str, str], str]:
    """Build status map from acceptance-profiles.json plus contract inapplicables."""
    profiles = json.loads(ACCEPTANCE.read_text())["profiles"]
    status: dict[tuple[str, str], str] = {}
    for motion_class, profile in profiles.items():
        for gate, row in profile["gates"].items():
            if gate == "baseline_row_stable":
                continue
            status[(motion_class, gate)] = row["status"]
    for motion_class, budget in S.MOTION_CLASSES.items():
        if budget.max_silhouette is None:
            status.setdefault((motion_class, "silhouette_budget"), "INAPPLICABLE")
        if not budget.loops or budget.max_loop is None:
            status.setdefault((motion_class, "loop_closure_pass"), "INAPPLICABLE")
        if not budget.loops or budget.max_min_pair is None:
            status.setdefault((motion_class, "min_pair_cohort_pass"), "INAPPLICABLE")
    # Classes without full profiles yet — infer from acquisition resolutions.
    inferred = {
        ("blob_idle", "silhouette_budget"): "SEPARATED",
        ("blob_idle", "palette_drift_pass"): "SEPARATED",
        ("blob_idle", "loop_closure_pass"): "SEPARATED",
        ("blob_idle", "min_pair_cohort_pass"): "SEPARATED",
        ("airborne", "palette_drift_pass"): "SEPARATED",
        ("airborne", "loop_closure_pass"): "SEPARATED",
        ("airborne", "min_pair_cohort_pass"): "SEPARATED",
        ("airborne", "silhouette_budget"): "INAPPLICABLE",
        ("walk", "silhouette_budget"): "SEPARATED",
        ("walk", "palette_drift_pass"): "SEPARATED",
        ("walk", "loop_closure_pass"): "SEPARATED",
        ("walk", "min_pair_cohort_pass"): "UNSEPARATED",
        ("swing", "silhouette_budget"): "SEPARATED",
        ("swing", "palette_drift_pass"): "SEPARATED",
        ("swing", "loop_closure_pass"): "INAPPLICABLE",
        ("swing", "min_pair_cohort_pass"): "INAPPLICABLE",
    }
    for key, value in inferred.items():
        status.setdefault(key, value)
    return status


def main() -> int:
    wg = worst_good()
    controls = control_metrics()
    status = acceptance_status()
    rows: list[dict] = []

    for motion_class in sorted(S.MOTION_CLASSES):
        for gate, field in GATE_FIELDS.items():
            st = status.get((motion_class, gate))
            if st == "INAPPLICABLE":
                continue
            g_raw = wg[motion_class][field]
            g = ceil_4(g_raw)
            prior = runtime_budget(motion_class, gate)
            c = controls.get((motion_class, gate))
            if st == "SEPARATED":
                if c is None:
                    raise SystemExit(f"missing control for separated {motion_class}/{gate}")
                budget = alpha_budget(g, c)
                review_lo = budget
                review_hi = c
                hard_fail = c
                headroom = round(budget - g, 4)
                review_width = round(c - budget, 4)
                rule = "alpha"
            else:
                budget = c5_budget(g_raw)
                review_lo = budget
                review_hi = None
                hard_fail = None
                headroom = round(budget - g, 4)
                review_width = None
                rule = "c5"
            delta = None if prior is None else round(budget - prior, 4)
            rows.append(
                {
                    "motion_class": motion_class,
                    "gate": gate,
                    "status": st,
                    "G": g,
                    "C": c,
                    "budget": budget,
                    "prior_budget": prior,
                    "delta": delta,
                    "headroom": headroom,
                    "review_width": review_width,
                    "hard_fail": hard_fail,
                    "rule": rule,
                }
            )

    print("α=0.5 Budget derivation (evidence for wayfinder #29)")
    print("=" * 100)
    print(
        f"{'class':<10} {'gate':<22} {'status':<12} {'G':>7} {'C':>7} "
        f"{'Budget':>7} {'prior':>7} {'Δ':>7} {'head':>7} {'revW':>7} {'hard':>7}"
    )
    for r in rows:
        c = "" if r["C"] is None else f"{r['C']:.4f}"
        prior = "" if r["prior_budget"] is None else f"{r['prior_budget']:.2f}"
        delta = "" if r["delta"] is None else f"{r['delta']:+.4f}"
        rev = "" if r["review_width"] is None else f"{r['review_width']:.4f}"
        hard = "" if r["hard_fail"] is None else f"{r['hard_fail']:.4f}"
        print(
            f"{r['motion_class']:<10} {r['gate']:<22} {r['status']:<12} "
            f"{r['G']:.4f} {c:>7} {r['budget']:.4f} {prior:>7} {delta:>7} "
            f"{r['headroom']:.4f} {rev:>7} {hard:>7}"
        )

    # Fragile claims: thinnest review_width for separated; unseparated note
    separated = [r for r in rows if r["status"] == "SEPARATED"]
    separated.sort(key=lambda r: r["review_width"] or 999)
    print("\nThinnest Separated Review bands (ascending review_width)")
    print("-" * 72)
    for r in separated[:5]:
        print(
            f"  {r['motion_class']}/{r['gate']}: review ({r['budget']:.4f}, {r['C']:.4f}) "
            f"width {r['review_width']:.4f}, headroom {r['headroom']:.4f}"
        )

    print("\nJSON")
    print(json.dumps(rows, indent=2))

    out_path = ROOT / "gate-controls" / "budget-derivation.json"
    payload = {
        "schema": "budget-derivation/0",
        "alpha": ALPHA,
        "decided_in": "https://github.com/jsbellamy/underline/issues/29",
        "numeric_policy": "https://github.com/jsbellamy/underline/issues/38",
        "detail": "docs/acceptance-profiles/budgets.md",
        "pairs": rows,
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
