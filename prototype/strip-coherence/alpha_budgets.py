#!/usr/bin/env python3
"""PROTOTYPE — derive α-Budgets for every applicable Motion-class/Gate pair.

Separated pairs use Budget = ceil₄(G + α·(C − G)) with α = 0.5 (#28).
Unseparated pairs keep the current ceil₀.₀₁(worst-good)+0.02 Budget and have no
hard-fail boundary. Inapplicable Gates are omitted.

Reproduces the tables in docs/alpha-budget-tables.md and verifies the production
`MOTION_CLASSES` / `ACCEPTANCE_GATES` projection matches derived evidence.
"""

from __future__ import annotations

import json
import os
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
GC_ROOT = pathlib.Path(
    os.environ.get("UNDERLINE_GATE_CONTROLS_ROOT", ROOT / "gate-controls")
)
GC_MANIFEST = GC_ROOT / "manifest.json"
ACCEPTANCE_PROFILES = GC_ROOT / "acceptance-profiles.json"

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


def _load_acceptance_profiles() -> dict[tuple[str, str], dict]:
    """(motion_class, gate) → profile row (status, budget, hard_fail, …)."""
    profiles = json.loads(ACCEPTANCE_PROFILES.read_text())["profiles"]
    rows: dict[tuple[str, str], dict] = {}
    for motion_class, profile in profiles.items():
        for gate, row in profile["gates"].items():
            if gate == "baseline_row_stable":
                continue
            rows[(motion_class, gate)] = row
    return rows


def _load_acceptance_status() -> dict[tuple[str, str], str]:
    """Build (motion_class, gate) → SEPARATED|UNSEPARATED|INAPPLICABLE."""
    return {
        pair: row["status"] for pair, row in _load_acceptance_profiles().items()
    }


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


def _required_separated_promotion_ids() -> frozenset[str]:
    """Provider-controlled Separated pairs that require an ACTIVE Promotion."""
    required: set[str] = set()
    for row in _load_acceptance_profiles().values():
        if row.get("status") == "SEPARATED" and "active_promotion" in row:
            required.add(row["active_promotion"])
    return frozenset(required)


def _assert_all_separated_promotions_active() -> None:
    """Fail closed when any required Separated Promotion is not ACTIVE."""
    required = _required_separated_promotion_ids()
    manifest = json.loads(GC_MANIFEST.read_text())
    statuses = {p["id"]: p["status"] for p in manifest["promotions"]}
    inactive = sorted(
        pid for pid in required if statuses.get(pid) != "ACTIVE"
    )
    if inactive:
        raise SystemExit(
            "α-Budget derivation blocked: required Separated Promotions "
            f"not ACTIVE: {', '.join(inactive)}"
        )


def _promoted_controls() -> dict[tuple[str, str], dict]:
    """(motion_class, gate) → {metric, attempt, caveats, measurement_path}."""
    profiles = _load_acceptance_profiles()
    manifest = json.loads(GC_MANIFEST.read_text())
    promotions = {p["id"]: p for p in manifest["promotions"]}
    specifications = {
        (spec["motion_class"], spec["target_gate"]): spec
        for spec in manifest["specifications"]
    }
    out: dict[tuple[str, str], dict] = {}
    for (motion_class, gate), row in profiles.items():
        if row.get("status") != "SEPARATED":
            continue
        promo_id = row.get("active_promotion")
        if promo_id is None:
            continue
        pair = f"{motion_class}/{gate}"
        promo = promotions.get(promo_id)
        if promo is None:
            raise SystemExit(
                f"α-Budget derivation blocked: missing Promotion {promo_id!r} "
                f"for {pair}"
            )
        if promo["status"] != "ACTIVE":
            raise SystemExit(
                f"α-Budget derivation blocked: Promotion {promo_id!r} not ACTIVE "
                f"(status={promo['status']!r}) for {pair}"
            )
        spec = specifications.get((motion_class, gate))
        if spec is None:
            raise SystemExit(
                f"α-Budget derivation blocked: missing specification for {pair}"
            )
        if spec["active_promotion"] != promo_id:
            raise SystemExit(
                f"α-Budget derivation blocked: mismatched Promotion for {pair}: "
                f"profile references {promo_id!r} but manifest spec has "
                f"{spec['active_promotion']!r}"
            )
        measurement_path = ROOT / promo["measurement_path"]
        if not measurement_path.is_file():
            raise SystemExit(
                f"α-Budget derivation blocked: missing Measurement evidence at "
                f"{promo['measurement_path']!r} for {pair}"
            )
        run = json.loads(measurement_path.read_text())
        gate_row = run.get("gates", {}).get(gate)
        if gate_row is None or "metric" not in gate_row:
            raise SystemExit(
                f"α-Budget derivation blocked: invalid Measurement evidence for "
                f"{pair} at {promo['measurement_path']!r}"
            )
        out[(motion_class, gate)] = {
            "metric": gate_row["metric"],
            "attempt": promo["attempt_id"],
            "caveats": list(run.get("caveats") or []),
            "measurement_path": promo["measurement_path"],
            "promotion": promo["id"],
        }
    return out


def _runtime_budget(motion_class: str, gate: str) -> float | None:
    budget = S.MOTION_CLASSES[motion_class]
    return getattr(budget, RUNTIME_BUDGET_ATTR[gate])


def _runtime_gate_policy(motion_class: str, gate: str) -> S.GatePolicy:
    return S.ACCEPTANCE_GATES[motion_class][gate]


def _assert_runtime_equivalence(
    *,
    profiles: dict[tuple[str, str], dict],
    separated_rows: list[dict],
) -> None:
    """Exit nonzero when derived α-Budgets diverge from production projection."""
    mismatches: list[str] = []
    derived_by_pair = {row["pair"]: row for row in separated_rows}

    for motion_class in ("idle", "blob_idle", "emissive", "walk", "airborne", "swing"):
        for gate in GATE_METRIC_KEY:
            pair_key = (motion_class, gate)
            pair = f"{motion_class}/{gate}"
            profile_row = profiles.get(pair_key)
            if profile_row is None:
                mismatches.append(f"missing Acceptance profile row for {pair}")
                continue

            policy = _runtime_gate_policy(motion_class, gate)
            profile_status = profile_row["status"]
            if policy.status != profile_status:
                mismatches.append(
                    f"{pair}: status profile={profile_status!r} "
                    f"runtime={policy.status!r}"
                )

            runtime_budget = _runtime_budget(motion_class, gate)
            profile_budget = profile_row.get("budget")
            if profile_status == "INAPPLICABLE":
                if runtime_budget is not None:
                    mismatches.append(
                        f"{pair}: runtime budget {runtime_budget!r} but INAPPLICABLE"
                    )
            elif profile_budget != runtime_budget:
                mismatches.append(
                    f"{pair}: budget profile={profile_budget} "
                    f"runtime={runtime_budget}"
                )

            profile_hard_fail = profile_row.get("hard_fail")
            runtime_hard_fail = policy.hard_fail
            if profile_status == "SEPARATED":
                if profile_hard_fail != runtime_hard_fail:
                    mismatches.append(
                        f"{pair}: hard_fail profile={profile_hard_fail} "
                        f"runtime={runtime_hard_fail}"
                    )
                derived = derived_by_pair.get(pair)
                if derived is None:
                    mismatches.append(f"{pair}: missing derived Separated row")
                elif derived["budget"] != runtime_budget:
                    mismatches.append(
                        f"{pair}: derived budget={derived['budget']} "
                        f"runtime={runtime_budget}"
                    )
                elif derived["c"] != profile_hard_fail:
                    mismatches.append(
                        f"{pair}: derived C={derived['c']} "
                        f"profile hard_fail={profile_hard_fail}"
                    )
            elif profile_status == "UNSEPARATED" and profile_hard_fail is not None:
                mismatches.append(
                    f"{pair}: UNSEPARATED profile must not declare hard_fail"
                )

    if mismatches:
        lines = ["α-Budget derivation blocked: runtime projection mismatch:"]
        lines.extend(f"  - {line}" for line in mismatches)
        raise SystemExit("\n".join(lines))


def main() -> int:
    _assert_all_separated_promotions_active()
    profiles = _load_acceptance_profiles()
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
            if old is None and pair_status != "INAPPLICABLE":
                raise SystemExit(
                    f"α-Budget derivation blocked: runtime omits Budget for {pair} "
                    f"but profile status is {pair_status}"
                )
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

    _assert_runtime_equivalence(profiles=profiles, separated_rows=separated_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
