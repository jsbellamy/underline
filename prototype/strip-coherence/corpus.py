#!/usr/bin/env python3
"""PROTOTYPE — score every inbox strip against prompts/manifest.json.

Drop `<sample-id>.png` into inbox/ for any sample in the manifest, then run this.
Samples with no PNG yet are listed as pending, so the corpus can be filled in over
several sessions.

Exit code is a contract regression check: rows where the verdict differs from
`contract_expect` are failures. Pre-generation predictions live in
`prompts/prediction-ledger.json` and are reported for reference only — a ledger
mismatch that the contract already explains (e.g. 05/06 under per-class budgets)
is not a failure.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import strip as S  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"
MANIFEST = HERE / "prompts" / "manifest.json"
PREDICTION_LEDGER = HERE / "prompts" / "prediction-ledger.json"

GATES = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "min_pair_cohort_pass",
    "loop_closure_pass",
    "displacement_pass",
    "palette_drift_pass",
)

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def find_png(sample_id: str) -> pathlib.Path | None:
    exact = INBOX / f"{sample_id}.png"
    if exact.exists():
        return exact
    # tolerate the original hand-named file
    if sample_id == "01-miner-idle":
        legacy = INBOX / "miner-idle-strip.png"
        if legacy.exists():
            return legacy
    matches = sorted(INBOX.glob(f"{sample_id}*.png"))
    return matches[0] if matches else None


def _budget_label(motion_class: str) -> str:
    budget = S.MOTION_CLASSES[motion_class]
    sil = "—" if budget.max_silhouette is None else f"{budget.max_silhouette:.2f}"
    loop = "—" if budget.max_loop is None else f"{budget.max_loop:.2f}"
    min_pair = "—" if budget.max_min_pair is None else f"{budget.max_min_pair:.2f}"
    return f"sil≤{sil} min_pair≤{min_pair} loop≤{loop} drift≤{budget.max_drift:.2f}"


def _gates_agree(expect_gates: list[str], tripped: list[str]) -> bool:
    return all(set(want.split("|")) & set(tripped) for want in expect_gates)


def evaluate(path: pathlib.Path, *, motion_class: str) -> dict:
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
    except (ValueError, OSError) as error:
        return {"pass": False, "tripped": ["recover"], "note": str(error)[:70]}

    coh = result.coherence
    if "reason" in coh:
        return {"pass": False, "tripped": ["slice"], "note": coh["reason"][:70]}

    tripped = [g for g in GATES if coh.get(g) is False]
    sil = max((r["frac"] for r in coh.get("silhouette_adjacent", [])), default=0.0)
    loop = (coh.get("loop_closure") or {}).get("frac", 0.0)
    pairwise = coh.get("silhouette_pairwise") or {}

    note = (
        f"sil={sil:.3f} loop={loop:.3f} drift={coh.get('worst_palette_drift', 0):.3f} "
        f"min_pair={pairwise.get('min_pair', 0):.3f} "
        f"max_pair={pairwise.get('max_pair', 0):.3f}"
    )
    if coh.get("displacement_inapplicable"):
        note += "  disp=— (inapplicable)"
    elif coh.get("displacement_pass") is not None:
        note += f"  disp={'pass' if coh['displacement_pass'] else 'FAIL'}"
    return {
        "pass": result.pass_,
        "tripped": tripped,
        "note": note,
        "displacement_inapplicable": coh.get("displacement_inapplicable", False),
        "displacement_reason": coh.get("displacement_reason"),
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    ledger = {
        row["id"]: row for row in json.loads(PREDICTION_LEDGER.read_text())["samples"]
    }
    samples = manifest["samples"]

    print(f"{'sample':<22} {'class':<11} {'want':<5} {'got':<5}  {'agrees':<7} detail")
    print("-" * 100)

    pending, regressions, ledger_mismatches, scored = [], [], [], 0
    displacement_inapplicable: list[str] = []
    for s in samples:
        motion_class = s["motion_class"]
        budget_note = _budget_label(motion_class)
        path = find_png(s["id"])
        if path is None:
            pending.append(s["id"])
            print(f"{s['id']:<22} {motion_class:<11} {s['contract_expect']:<5} {DIM}{'--':<5}  "
                  f"{'pending':<7} no PNG in inbox/  {DIM}{budget_note}{RESET}")
            continue

        r = evaluate(path, motion_class=motion_class)
        scored += 1
        if r.get("displacement_inapplicable"):
            displacement_inapplicable.append(s["id"])
            detail_extra = f"  {YELLOW}disp inapplicable: {r['displacement_reason']}{RESET}"
        else:
            detail_extra = ""
        got = "PASS" if r["pass"] else "FAIL"
        contract_agrees = got == s["contract_expect"] and _gates_agree(
            s["contract_expect_gates"], r["tripped"]
        )
        if not contract_agrees:
            regressions.append((s, r))

        frozen = ledger.get(s["id"])
        if frozen is not None:
            ledger_agrees = got == frozen["expect"] and _gates_agree(
                frozen["expect_gates"], r["tripped"]
            )
            if not ledger_agrees:
                ledger_mismatches.append((s, r, frozen))

        color = GREEN if contract_agrees else RED
        detail = r["note"]
        if r["tripped"]:
            detail += f"  tripped={r['tripped']}"
        print(f"{s['id']:<22} {motion_class:<11} {s['contract_expect']:<5} {got:<5}  "
              f"{color}{'yes' if contract_agrees else 'NO':<7}{RESET} {detail}{detail_extra}  "
              f"{DIM}{budget_note}{RESET}")

    print("-" * 100)
    print(f"scored {scored}/{len(samples)}   pending {len(pending)}   "
          f"regressions {len(regressions)}")
    if displacement_inapplicable:
        print(
            f"{YELLOW}{len(displacement_inapplicable)} strip(s) displacement inapplicable "
            f"(degenerate alignment): {', '.join(displacement_inapplicable)}{RESET}"
        )

    if regressions:
        print(f"\n{RED}Contract regressions — verdict differs from manifest:{RESET}")
        for s, r in regressions:
            print(f"  {s['id']}: expected {s['contract_expect']} "
                  f"{s['contract_expect_gates'] or '(all gates clean)'}, "
                  f"got {'PASS' if r['pass'] else 'FAIL'} {r['tripped'] or '(clean)'}")
            print(f"    {DIM}premise: {s['why']}{RESET}")

    if ledger_mismatches:
        print(f"\n{YELLOW}Frozen ledger — pre-generation predictions (informational):{RESET}")
        for s, r, frozen in ledger_mismatches:
            print(f"  {s['id']}: predicted {frozen['expect']} "
                  f"{frozen['expect_gates'] or '(all gates clean)'}, "
                  f"got {'PASS' if r['pass'] else 'FAIL'} {r['tripped'] or '(clean)'}")
            print(f"    {DIM}premise: {s['why']}{RESET}")
        print(f"\n  {DIM}Ledger is frozen in prediction-ledger.json — update contract_expect "
              f"in manifest.json when the gate design changes.{RESET}")

    if pending:
        print(f"\n{DIM}Pending: generate with prompts/<id>.prompt.txt, "
              f"save as inbox/<id>.png{RESET}")

    # Pending samples are not failures; only contract regressions are.
    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
