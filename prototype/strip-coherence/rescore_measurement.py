#!/usr/bin/env python3
"""Apply the #38 numeric policy to an existing Measurement run.

Creates a new append-only Measurement run with four-place ceiling quantization
and inclusive Budget comparison (epsilon=0). Does not overwrite prior evidence.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GC_ROOT = ROOT / "gate-controls"
sys.path.insert(0, str(ROOT))

from pipeline.numeric_policy import NUMERIC_POLICY, canonical_metric  # noqa: E402


def gate_outcome(metric: float | None, budget: float | None) -> str | None:
    if metric is None or budget is None:
        return None
    return "pass" if canonical_metric(metric) <= budget else "fail"


def rescore(run: dict) -> dict:
    out = copy.deepcopy(run)
    out["schema"] = "gate-control-measurement/1"
    out["numeric_policy"] = NUMERIC_POLICY
    out["rescore_of"] = run.get("rescore_of") or {
        "schema": run.get("schema"),
        "scorer_gate_config_sha256": run.get("scorer_gate_config_sha256"),
    }
    out["rescored_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    target = out["target_gate"]
    others_failed: list[str] = []
    for gate, row in out["gates"].items():
        metric = row.get("metric")
        budget = row.get("budget")
        if metric is None:
            continue
        row["metric_raw"] = metric
        row["metric"] = canonical_metric(metric)
        outcome = gate_outcome(metric, budget)
        if outcome is not None:
            row["outcome"] = outcome
        if gate != target and row["outcome"] == "fail":
            others_failed.append(gate)

    target_row = out["gates"][target]
    target_outcome = target_row["outcome"]
    caveats = list(out.get("caveats", []))
    blockers: list[str] = []
    if target_outcome == "undecidable":
        isolation = "INDETERMINATE"
        blockers.append(f"target gate {target} is undecidable")
    elif target_outcome == "fail" and not others_failed:
        isolation = "ISOLATED"
    else:
        isolation = "NOT_ISOLATED"
        if target_outcome == "pass":
            blockers.append(f"target gate {target} passes")
        blockers += [f"collateral failure: {g}" for g in others_failed]

    out["isolation"] = isolation
    out["blockers"] = blockers
    out["caveats"] = caveats
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("measurement", type=pathlib.Path, help="existing measurement JSON")
    p.add_argument("--out", type=pathlib.Path, help="output path (default: sibling timestamp)")
    args = p.parse_args(argv)

    measurement = args.measurement
    if not measurement.is_absolute():
        measurement = ROOT / measurement
    run = json.loads(measurement.read_text())
    rescored = rescore(run)

    if args.out:
        out_path = args.out if args.out.is_absolute() else ROOT / args.out
    else:
        attempt_dir = measurement.parent
        stamp = rescored["rescored_at"].replace(":", "-")
        out_path = attempt_dir / f"{stamp}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rescored, indent=2) + "\n")
    print(json.dumps({"path": str(out_path.relative_to(ROOT)), "isolation": rescored["isolation"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
