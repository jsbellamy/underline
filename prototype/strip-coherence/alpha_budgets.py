#!/usr/bin/env python3
"""PROTOTYPE — derive α-Budgets for every applicable Motion-class/Gate pair.

Separated pairs use Budget = ceil₄(G + α·(C − G)) with α = 0.5 (#28).
Unseparated pairs keep the current ceil₀.₀₁(worst-good)+0.02 Budget and have no
hard-fail boundary. Inapplicable Gates are omitted.

Reproduces the tables in docs/alpha-budget-tables.md. Does not mutate runtime
MOTION_CLASSES — landing production Budgets is a later implementation wave.
"""

from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass

# Local prototype imports (same pattern as derive_budgets.py).
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import derive_budgets as db  # noqa: E402
from numeric_policy import canonical_metric  # noqa: E402
from pipeline import strip as S  # noqa: E402

ALPHA = 0.5
GC_MANIFEST = ROOT / "gate-controls" / "manifest.json"
ACCEPTANCE_PROFILES = ROOT / "gate-controls" / "acceptance-profiles.json"

GATE_METRIC_KEY = {
    "silhouette_budget": "sil",
    "loop_closure_pass": "loop",
    "palette_drift_pass": "drift",
    "min_pair_cohort_pass": "min_pair",
}

RUNTIME_BUDGET_ATTR = {
    "silhouette_budget": "max_silhouette",
    "loop_closure_pass": "max_loop",
    "palette_drift_pass": "max_drift",
    "min_pair_cohort_pass": "max_min_pair",
}


@dataclass(frozen=True)
class SeparatedBudget:
    g: float
    c: float
    budget: float
    good_headroom: float
    review_width: float


def derive_separated_budget(
    worst_good: float, control: float, *, alpha: float = ALPHA
) -> SeparatedBudget:
    """Apply the #28 Gap allocation factor to already-measured endpoints."""
    g = canonical_metric(worst_good)
    c = canonical_metric(control)
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")
    if c <= g:
        raise ValueError(f"control {c} must be strictly above worst-good {g}")
    budget = canonical_metric(g + alpha * (c - g))
    if not g <= budget < c:
        raise ValueError(f"derived Budget {budget} not in [{g}, {c})")
    return SeparatedBudget(
        g=g,
        c=c,
        budget=budget,
        good_headroom=round(budget - g, 4),
        review_width=round(c - budget, 4),
    )


def _load_acceptance_status() -> dict[tuple[str, str], str]:
    """Build (motion_class, gate) → SEPARATED|UNSEPARATED|INAPPLICABLE."""
    profiles = json.loads(ACCEPTANCE_PROFILES.read_text())["profiles"]
    status: dict[tuple[str, str], str] = {}
    for motion_class, profile in profiles.items():
        for gate, row in profile["gates"].items():
            if gate == "baseline_row_stable":
                continue
            status[(motion_class, gate)] = row["status"]
    # Classes not yet in acceptance-profiles.json — decided on the map tickets.
    decided = {
        ("blob_idle", "silhouette_budget"): "SEPARATED",
        ("blob_idle", "palette_drift_pass"): "SEPARATED",
        ("blob_idle", "loop_closure_pass"): "SEPARATED",
        ("blob_idle", "min_pair_cohort_pass"): "SEPARATED",
        ("walk", "silhouette_budget"): "SEPARATED",
        ("walk", "palette_drift_pass"): "SEPARATED",
        ("walk", "loop_closure_pass"): "SEPARATED",
        ("walk", "min_pair_cohort_pass"): "UNSEPARATED",
        ("airborne", "silhouette_budget"): "INAPPLICABLE",
        ("airborne", "palette_drift_pass"): "SEPARATED",
        ("airborne", "loop_closure_pass"): "SEPARATED",
        ("airborne", "min_pair_cohort_pass"): "SEPARATED",
        ("swing", "silhouette_budget"): "SEPARATED",
        ("swing", "palette_drift_pass"): "SEPARATED",
        ("swing", "loop_closure_pass"): "INAPPLICABLE",
        ("swing", "min_pair_cohort_pass"): "INAPPLICABLE",
    }
    for key, value in decided.items():
        status.setdefault(key, value)
    return status


def _worst_good_by_class() -> dict[str, dict[str, tuple[str, float]]]:
    """motion_class → gate_metric_key → (binding_sample_id, raw_metric)."""
    manifest = json.loads(db.MANIFEST.read_text())
    by_class: dict[str, list[tuple[str, dict[str, float]]]] = {}
    for sample in manifest["samples"]:
        if sample.get("contract_expect") != "PASS" or sample["id"] in db.NEGATIVE_IDS:
            continue
        path = corpus.find_png(sample["id"])
        if path is None:
            continue
        metrics = db._ingest_metrics(path, sample["motion_class"])
        if metrics is None:
            continue
        by_class.setdefault(sample["motion_class"], []).append((sample["id"], metrics))
    for motion_class, names in db.EXTRA_GOOD.items():
        for name in names:
            path = db.INBOX / name
            if not path.exists():
                continue
            metrics = db._ingest_metrics(path, motion_class)
            if metrics is None:
                continue
            by_class.setdefault(motion_class, []).append(
                (name.removesuffix(".png"), metrics)
            )

    out: dict[str, dict[str, tuple[str, float]]] = {}
    for motion_class, rows in by_class.items():
        binding: dict[str, tuple[str, float]] = {}
        for key in ("sil", "loop", "drift", "min_pair"):
            sample_id, metrics = max(rows, key=lambda row: row[1][key])
            binding[key] = (sample_id, metrics[key])
        out[motion_class] = binding
    return out


def _promoted_controls() -> dict[tuple[str, str], dict]:
    """(motion_class, gate) → {metric, attempt, caveats, measurement_path}."""
    manifest = json.loads(GC_MANIFEST.read_text())
    promotions = {p["id"]: p for p in manifest["promotions"]}
    out: dict[tuple[str, str], dict] = {}
    for spec in manifest["specifications"]:
        promo = promotions[spec["active_promotion"]]
        run = json.loads((ROOT / promo["measurement_path"]).read_text())
        gate = spec["target_gate"]
        out[(spec["motion_class"], gate)] = {
            "metric": run["gates"][gate]["metric"],
            "attempt": promo["attempt_id"],
            "caveats": list(run.get("caveats") or []),
            "measurement_path": promo["measurement_path"],
            "promotion": promo["id"],
        }
    return out


def _runtime_budget(motion_class: str, gate: str) -> float | None:
    budget = S.MOTION_CLASSES[motion_class]
    return getattr(budget, RUNTIME_BUDGET_ATTR[gate])


def main() -> int:
    status = _load_acceptance_status()
    worst = _worst_good_by_class()
    controls = _promoted_controls()

    print(f"α-Budget derivation (α = {ALPHA})")
    print("Budget = ceil₄(G + α·(C − G)) for Separated pairs")
    print("=" * 96)
    print(
        f"{'pair':<36} {'status':<12} {'G':>7} {'C':>7} {'Budget':>7} "
        f"{'old':>6} {'Δ':>8} {'head':>7} {'review':>7}"
    )
    print("-" * 96)

    separated_rows: list[dict] = []
    unseparated_rows: list[dict] = []
    inapplicable: list[str] = []

    for motion_class in ("idle", "blob_idle", "emissive", "walk", "airborne", "swing"):
        for gate, metric_key in GATE_METRIC_KEY.items():
            pair = f"{motion_class}/{gate}"
            pair_status = status.get((motion_class, gate))
            if pair_status is None:
                raise SystemExit(f"missing Acceptance status for {pair}")
            if pair_status == "INAPPLICABLE":
                inapplicable.append(pair)
                print(f"{pair:<36} {'INAPPLICABLE':<12}")
                continue

            sample_id, raw_g = worst[motion_class][metric_key]
            old = _runtime_budget(motion_class, gate)
            assert old is not None

            if pair_status == "UNSEPARATED":
                g = canonical_metric(raw_g)
                head = round(old - g, 4)
                print(
                    f"{pair:<36} {'UNSEPARATED':<12} {g:7.4f} {'—':>7} {old:7.4f} "
                    f"{old:6.2f} {0.0:+8.4f} {head:7.4f} {'open':>7}  ({sample_id})"
                )
                unseparated_rows.append(
                    {
                        "pair": pair,
                        "g": g,
                        "budget": old,
                        "old": old,
                        "delta": 0.0,
                        "good_headroom": head,
                        "binding_good": sample_id,
                    }
                )
                continue

            control = controls[(motion_class, gate)]
            derived = derive_separated_budget(raw_g, control["metric"], alpha=ALPHA)
            delta = round(derived.budget - old, 4)
            caveat = " [caveat]" if control["caveats"] else ""
            print(
                f"{pair:<36} {'SEPARATED':<12} {derived.g:7.4f} {derived.c:7.4f} "
                f"{derived.budget:7.4f} {old:6.2f} {delta:+8.4f} "
                f"{derived.good_headroom:7.4f} {derived.review_width:7.4f}  "
                f"({sample_id} → {control['attempt']}){caveat}"
            )
            separated_rows.append(
                {
                    "pair": pair,
                    "g": derived.g,
                    "c": derived.c,
                    "budget": derived.budget,
                    "old": old,
                    "delta": delta,
                    "good_headroom": derived.good_headroom,
                    "review_width": derived.review_width,
                    "binding_good": sample_id,
                    "control_attempt": control["attempt"],
                    "caveats": control["caveats"],
                }
            )

    print()
    print("FRAGILE CLAIMS (Separated — thinnest good headroom / Review width)")
    print("-" * 96)
    fragile = sorted(separated_rows, key=lambda row: row["good_headroom"])[:5]
    for row in fragile:
        print(
            f"  {row['pair']:<36} head={row['good_headroom']:.4f}  "
            f"review={row['review_width']:.4f}  "
            f"G={row['g']:.4f}  B={row['budget']:.4f}  C={row['c']:.4f}"
        )

    print()
    print(
        f"Separated={len(separated_rows)}  Unseparated={len(unseparated_rows)}  "
        f"Inapplicable={len(inapplicable)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
