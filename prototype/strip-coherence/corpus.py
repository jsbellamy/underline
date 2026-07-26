#!/usr/bin/env python3
"""PROTOTYPE — score every inbox strip against prompts/manifest.json.

Drop `<sample-id>.png` into inbox/ for any sample in the manifest, then run this.
Samples with no PNG yet are listed as pending, so the corpus can be filled in over
several sessions.

The point is not to get all-green. Rows where the verdict differs from the manifest's
prediction are the findings — especially 05/06, where a FAIL means the budgets are
per-motion-class rather than universal.
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

GATES = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "loop_closure_pass",
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


def evaluate(path: pathlib.Path) -> dict:
    layout = S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )
    try:
        result = S.ingest_strip_provider(path, layout)
    except (ValueError, OSError) as error:
        return {"pass": False, "tripped": ["recover"], "note": str(error)[:70]}

    coh = result.coherence
    if "reason" in coh:
        return {"pass": False, "tripped": ["slice"], "note": coh["reason"][:70]}

    tripped = [g for g in GATES if not coh.get(g, True)]
    sil = max((r["frac"] for r in coh.get("silhouette_adjacent", [])), default=0.0)
    loop = (coh.get("loop_closure") or {}).get("frac", 0.0)

    # Slicing keys on the subject's own empty columns, not the declared gutter, so
    # segments are content bboxes. Uneven widths mean normalize_frame_widths cropped
    # from the left against frames whose content starts at different offsets — that
    # misalignment reads as a silhouette failure. Flag it so it is not misread.
    widths = result.slice_meta.get("segment_widths", [])
    confound = len(set(widths)) > 1

    note = f"sil={sil:.3f} loop={loop:.3f} drift={coh.get('worst_palette_drift', 0):.3f}"
    if confound:
        note += f" {YELLOW}widths={widths}!{RESET}"
    return {
        "pass": result.pass_,
        "tripped": tripped,
        "note": note,
        "confound": confound,
        "widths": widths,
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    samples = manifest["samples"]

    print(f"{'sample':<22} {'class':<11} {'want':<5} {'got':<5}  {'agrees':<7} detail")
    print("-" * 100)

    pending, surprises, confounded, scored = [], [], [], 0
    for s in samples:
        path = find_png(s["id"])
        if path is None:
            pending.append(s["id"])
            print(f"{s['id']:<22} {s['class']:<11} {s['expect']:<5} {DIM}{'--':<5}  "
                  f"{'pending':<7} no PNG in inbox/{RESET}")
            continue

        r = evaluate(path)
        scored += 1
        if r.get("confound"):
            confounded.append(s["id"])
        got = "PASS" if r["pass"] else "FAIL"
        verdict_agrees = got == s["expect"]
        # An expectation may name alternatives, e.g. "recover|slice".
        gates_agree = all(
            set(want.split("|")) & set(r["tripped"])
            for want in s["expect_gates"]
        )
        agrees = verdict_agrees and gates_agree
        if not agrees:
            surprises.append((s, r, verdict_agrees, gates_agree))
        color = GREEN if agrees else YELLOW
        detail = r["note"]
        if r["tripped"]:
            detail += f"  tripped={r['tripped']}"
        print(f"{s['id']:<22} {s['class']:<11} {s['expect']:<5} {got:<5}  "
              f"{color}{'yes' if agrees else 'NO':<7}{RESET} {detail}")

    print("-" * 100)
    print(f"scored {scored}/{len(samples)}   pending {len(pending)}   "
          f"surprises {len(surprises)}")

    if surprises:
        print(f"\n{YELLOW}Findings — prediction did not hold:{RESET}")
        for s, r, v_ok, g_ok in surprises:
            print(f"  {s['id']}: expected {s['expect']} "
                  f"{s['expect_gates'] or '(all gates clean)'}, "
                  f"got {'PASS' if r['pass'] else 'FAIL'} {r['tripped'] or '(clean)'}")
            print(f"    {DIM}premise: {s['why']}{RESET}")
        print(f"\n  {DIM}Update the gate design or the premise — not the manifest.{RESET}")

    if confounded:
        print(f"\n{YELLOW}Uneven segment widths (alignment confound):{RESET} "
              f"{', '.join(confounded)}")
        print(f"  {DIM}Frames were cropped to the narrowest segment from the left. A "
              f"silhouette failure on these\n  rows may be misalignment, not motion — "
              f"check with probe.py's x-shift scan before believing it.{RESET}")

    if pending:
        print(f"\n{DIM}Pending: generate with prompts/<id>.prompt.txt, "
              f"save as inbox/<id>.png{RESET}")

    # Pending samples are not failures; only contradicted predictions are.
    return 1 if surprises else 0


if __name__ == "__main__":
    raise SystemExit(main())
