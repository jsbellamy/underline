#!/usr/bin/env python3
"""PROTOTYPE — derive per-class budgets from scored corpus samples.

Reads manifest.json, ingests every declared-good strip (contract_expect PASS) with a
PNG in inbox/, and prints worst-good measurements plus ceil+0.02 derived budgets.
Good-strip membership is a manifest judgment about the art — not whether the strip
passes under the budgets being calibrated. Negative controls are scored for
separation checks. Pending samples are listed but skipped.
"""

from __future__ import annotations

import json
import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import corpus  # noqa: E402
import strip as S  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = HERE / "prompts" / "manifest.json"
INBOX = HERE / "inbox"

# Good strips outside manifest.json but in the idle derivation cohort (contract C5).
EXTRA_GOOD: dict[str, list[str]] = {
    "idle": ["miner-idle-strip.png"],
}

NEGATIVE_IDS = {
    s["id"]
    for s in json.loads(MANIFEST.read_text())["samples"]
    if s.get("contract_expect") == "FAIL"
}


def _ceil_001(value: float) -> float:
    return math.ceil(value * 100) / 100


def _derive(worst: float) -> float:
    return round(_ceil_001(worst) + 0.02, 2)


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
        "pass": result.pass_,
        "sil": sil,
        "loop": loop,
        "drift": drift,
        "min_pair": pairwise.get("min_pair", 0.0),
        "max_pair": pairwise.get("max_pair", 0.0),
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    samples = manifest["samples"]
    by_class: dict[str, list[tuple[str, dict[str, float]]]] = {}
    negatives: dict[str, dict[str, float]] = {}
    pending: list[str] = []

    for sample in samples:
        path = corpus.find_png(sample["id"])
        if path is None:
            pending.append(sample["id"])
            continue
        metrics = _ingest_metrics(path, sample["motion_class"])
        if metrics is None:
            continue
        if sample["id"] in NEGATIVE_IDS:
            negatives[sample["id"]] = metrics
            continue
        if sample.get("contract_expect") != "PASS":
            continue
        by_class.setdefault(sample["motion_class"], []).append((sample["id"], metrics))

    for motion_class, names in EXTRA_GOOD.items():
        for name in names:
            path = INBOX / name
            if not path.exists():
                continue
            metrics = _ingest_metrics(path, motion_class)
            if metrics is None:
                continue
            label = name.removesuffix(".png")
            by_class.setdefault(motion_class, []).append((label, metrics))

    print("Per-class worst-good measurements (manifest-good, gate-agnostic)")
    print("-" * 72)
    for motion_class in sorted(by_class):
        rows = by_class[motion_class]
        worst = {
            "sil": max(m["sil"] for _, m in rows),
            "loop": max(m["loop"] for _, m in rows),
            "drift": max(m["drift"] for _, m in rows),
            "worst_good_min_pair": max(m["min_pair"] for _, m in rows),
            "cohort_min_pair_floor": min(m["min_pair"] for _, m in rows),
            "max_pair": max(m["max_pair"] for _, m in rows),
        }
        budget = S.MOTION_CLASSES[motion_class]
        print(f"\n{motion_class}  (n={len(rows)})")
        for sample_id, m in rows:
            flag = "" if m["pass"] else "  <- fails current budget"
            print(
                f"  {sample_id:<24} sil={m['sil']:.3f} loop={m['loop']:.3f} "
                f"drift={m['drift']:.3f} min_pair={m['min_pair']:.3f}{flag}"
            )
        sil_derived = None if budget.max_silhouette is None else _derive(worst["sil"])
        loop_derived = None if budget.max_loop is None else _derive(worst["loop"])
        drift_derived = _derive(worst["drift"])
        min_pair_derived = (
            None if budget.max_min_pair is None else _derive(worst["worst_good_min_pair"])
        )
        print(
            f"  worst sil={worst['sil']:.3f} -> {sil_derived}   "
            f"loop={worst['loop']:.3f} -> {loop_derived}   "
            f"drift={worst['drift']:.3f} -> {drift_derived}"
        )
        print(
            f"  worst-good min_pair={worst['worst_good_min_pair']:.3f} -> {min_pair_derived}   "
            f"cohort floor={worst['cohort_min_pair_floor']:.3f}  max_pair={worst['max_pair']:.3f}"
        )

    if negatives:
        print("\nNegative controls (separation reference)")
        print("-" * 72)
        for sample_id, m in sorted(negatives.items()):
            print(
                f"  {sample_id:<24} sil={m['sil']:.3f} loop={m['loop']:.3f} "
                f"drift={m['drift']:.3f} min_pair={m['min_pair']:.3f}"
            )

    if pending:
        print(f"\nPending ({len(pending)}): {', '.join(pending)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
