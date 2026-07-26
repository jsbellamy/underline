#!/usr/bin/env python3
"""PROTOTYPE — score one candidate Gate control and build its review packet.

Answers ticket #20: given a provider Strip, its Motion class, and the Gate it is
meant to isolate, can one small tool

  1. derive the class-applicable Gate set and classify the target Gate,
  2. prove every *other* applicable Gate passes (the Isolation verdict of #19),
  3. pick exactly one primary failure,
  4. emit a machine-readable retry action, and
  5. build the single composite an agent needs for Review-band judgment?

Throwaway. No provenance, no Manifest, no Promotion — measurement only, which is
the half of #19 a scorer owns. Run:

    PYTHONPATH=. python3 prototype/strip-coherence/gate_control.py \
        inbox/22-NEG-airborne-identity.png --motion-class airborne \
        --target-gate min_pair_cohort_pass --composite out/22.png
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

from PIL import Image, ImageDraw

from pipeline import strip as S

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"

# Gate order is the tie-break for primary-failure selection: cheapest/most
# upstream defect first, so one prompt change has a chance of addressing it.
GATE_ORDER = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "displacement_pass",
    "loop_closure_pass",
    "min_pair_cohort_pass",
    "palette_drift_pass",
)

# Gates whose failure is structural: the Strip is not a Strip, so nothing it
# measures can calibrate anything. Never a valid target.
STRUCTURAL_GATES = ("dimension_parity",)

METRIC_OF = {
    "silhouette_budget": ("silhouette_adjacent_max", "silhouette"),
    "loop_closure_pass": (None, "loop"),
    "min_pair_cohort_pass": (None, "min_pair"),
    "palette_drift_pass": ("worst_palette_drift", "palette_drift"),
}


class SpecificationError(ValueError):
    """The Gate-control specification is invalid. No Measurement run is written."""


def corpus_layout() -> S.StripLayout:
    return S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def applicable_gates(motion_class: str) -> dict[str, str]:
    """Class-applicable Gates -> why. Inapplicable Gates are omitted, per #19."""
    b = S.MOTION_CLASSES[motion_class]
    gates: dict[str, str] = {"dimension_parity": "structural", "palette_drift_pass": "always"}
    if b.grounded:
        gates["baseline_row_stable"] = "grounded: true"
    else:
        gates["displacement_pass"] = "grounded: false"
    if b.max_silhouette is not None:
        gates["silhouette_budget"] = f"max_silhouette={b.max_silhouette}"
    if b.loops and b.max_loop is not None:
        gates["loop_closure_pass"] = f"max_loop={b.max_loop}"
    if b.loops and b.max_min_pair is not None:
        gates["min_pair_cohort_pass"] = f"max_min_pair={b.max_min_pair}"
    return {g: gates[g] for g in GATE_ORDER if g in gates}


def metric_value(coh: dict[str, Any], gate: str) -> float | None:
    if gate == "loop_closure_pass":
        return (coh.get("loop_closure") or {}).get("frac")
    if gate == "min_pair_cohort_pass":
        return (coh.get("silhouette_pairwise") or {}).get("min_pair")
    key = METRIC_OF.get(gate, (None, None))[0]
    return coh.get(key) if key else None


def budget_value(coh: dict[str, Any], gate: str) -> float | None:
    key = METRIC_OF.get(gate, (None, None))[1]
    return (coh.get("budgets") or {}).get(key) if key else None


def measure(path: pathlib.Path, motion_class: str, target_gate: str) -> dict[str, Any]:
    """One Measurement run: applicable Gate outcomes plus an Isolation verdict."""
    applicable = applicable_gates(motion_class)
    run: dict[str, Any] = {
        "schema": "gate-control-measurement/0",
        "raw": str(path),
        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scorer_gate_config_sha256": gate_config_hash(),
        "motion_class": motion_class,
        "target_gate": target_gate,
        "applicable_gates": list(applicable),
    }

    # Decision (#20): an invalid target is a broken specification, not a failed
    # acquisition. Validate before scoring and write no Measurement run at all,
    # so the append-only ledger never carries a row that should not exist.
    if target_gate not in applicable:
        raise SpecificationError(
            f"target gate {target_gate!r} is inapplicable to motion class {motion_class!r}; "
            f"applicable: {', '.join(applicable)}"
        )
    if target_gate in STRUCTURAL_GATES:
        raise SpecificationError(
            f"target gate {target_gate!r} is structural and can never be a target Gate"
        )

    try:
        result = S.ingest_strip_provider(path, corpus_layout(), motion_class=motion_class)
    except (ValueError, OSError) as error:
        return _abort(run, "STRUCTURAL_RECOVERY_FAILED", str(error)[:120], recovered=False)

    coh = result.coherence
    if "silhouette_adjacent" not in coh:
        return _abort(run, "STRUCTURAL_RECOVERY_FAILED",
                      coh.get("reason") or "auto-slice failed", recovered=False)

    run["structural"] = {
        "recovered": True,
        "pitch_x_score": round(result.recovered["pitch_x"]["score"], 4),
        "pitch_y_score": round(result.recovered["pitch_y"]["score"], 4),
    }

    gates: dict[str, Any] = {}
    for gate, why in applicable.items():
        value = coh.get(gate)
        gates[gate] = {
            "applicable_because": why,
            "outcome": "undecidable" if value is None else ("pass" if value else "fail"),
            "metric": metric_value(coh, gate),
            "budget": budget_value(coh, gate),
            "reason": coh.get("displacement_reason") if gate == "displacement_pass" else None,
        }
    run["gates"] = gates

    others_failed = [g for g, r in gates.items() if g != target_gate and r["outcome"] == "fail"]
    target = gates[target_gate]["outcome"]
    # Decision (#20): only an undecidable *target* is INDETERMINATE. A non-target
    # undecidable is a recorded caveat — the control still evidences its own Gate,
    # it just does not evidence the undecidable dimension. Without this, airborne
    # can produce no Gate control at all, because displacement_pass is undecidable
    # on every airborne strip measured to date.
    caveats = [f"{g} is undecidable — this control does not evidence that dimension"
               for g, r in gates.items()
               if g != target_gate and r["outcome"] == "undecidable"]

    blockers: list[str] = []
    if target == "undecidable":
        isolation = "INDETERMINATE"
        blockers.append(f"target gate {target_gate} is undecidable")
    elif target == "fail" and not others_failed:
        isolation = "ISOLATED"
    else:
        isolation = "NOT_ISOLATED"
        if target == "pass":
            blockers.append(f"target gate {target_gate} passes")
        blockers += [f"collateral failure: {g}" for g in others_failed]

    run["isolation"] = isolation
    run["blockers"] = blockers
    run["caveats"] = caveats
    run["primary_failure"] = primary_failure(run)
    run["retry_action"] = retry_action(run)
    return run


def _abort(run: dict[str, Any], code: str, rationale: str,
           *, recovered: bool | None) -> dict[str, Any]:
    """Terminate measurement before any Gate outcome exists, still emitting one
    primary failure and one retry action — the acquisition loop needs both most
    when nothing scored."""
    out = {**run,
           "structural": {"recovered": recovered, "reason": rationale},
           "gates": {},
           "isolation": "INDETERMINATE",
           "blockers": [rationale],
           "primary_failure": {"code": code, "gate": run["target_gate"]
                               if code == "SPEC_INVALID_TARGET" else None,
                               "rationale": rationale}}
    out["retry_action"] = retry_action(out)
    return out


def gate_config_hash() -> str:
    payload = json.dumps(
        {name: vars(b) for name, b in sorted(S.MOTION_CLASSES.items())}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def primary_failure(run: dict[str, Any]) -> dict[str, Any] | None:
    """Exactly one. Deterministic: structure, then target-too-weak, then GATE_ORDER."""
    if run["isolation"] == "ISOLATED":
        return None
    if not run["structural"]["recovered"]:
        return {"code": "STRUCTURAL_RECOVERY_FAILED", "gate": None,
                "rationale": run["structural"].get("reason") or "strip did not recover"}

    gates = run["gates"]
    target = run["target_gate"]
    if gates[target]["outcome"] == "undecidable":
        return {"code": "GATE_UNDECIDABLE", "gate": target,
                "rationale": gates[target].get("reason") or f"{target} returned None"}

    if gates[target]["outcome"] == "pass":
        return {"code": "TARGET_DEFECT_TOO_WEAK", "gate": target,
                "rationale": f"{target} measured {gates[target]['metric']} "
                             f"within budget {gates[target]['budget']}"}

    collateral = [g for g in GATE_ORDER
                  if g != target and gates.get(g, {}).get("outcome") == "fail"]
    g = collateral[0]
    return {"code": "COLLATERAL_GATE_FAILED", "gate": g,
            "rationale": f"{g} measured {gates[g]['metric']} over budget {gates[g]['budget']}"}


RETRY_INTENT = {
    "STRUCTURAL_RECOVERY_FAILED": "restate the grid/gutter constraint in the prompt",
    "GATE_UNDECIDABLE": "change the motion so alignment is well-posed",
    "TARGET_DEFECT_TOO_WEAK": "amplify the targeted defect",
    "COLLATERAL_GATE_FAILED": "hold the collateral dimension fixed",
}


def retry_action(run: dict[str, Any]) -> dict[str, Any] | None:
    pf = run.get("primary_failure")
    if pf is None:
        return None
    gates = run["gates"]
    action: dict[str, Any] = {
        "reason_code": pf["code"],
        "gate": pf["gate"],
        "intent": RETRY_INTENT[pf["code"]],
        "one_prompt_delta": True,
    }
    if not gates:
        return action
    if pf["code"] == "TARGET_DEFECT_TOO_WEAK":
        action["direction"] = "increase"
        action["metric_now"] = gates[pf["gate"]]["metric"]
        action["must_exceed"] = gates[pf["gate"]]["budget"]
    elif pf["code"] == "COLLATERAL_GATE_FAILED":
        action["direction"] = "decrease"
        action["metric_now"] = gates[pf["gate"]]["metric"]
        action["must_fall_below"] = gates[pf["gate"]]["budget"]
    return action


# --- review composite ---------------------------------------------------

SCALE = 6
PAD = 8
BAND = 11


def _frames(path: pathlib.Path) -> list[list[list[Any]]] | None:
    return S.load_provider_frames(path, corpus_layout())


def _quantized(frames):
    rgbs = S.collect_opaque_rgbs(frames)
    palette, _ = S.build_shared_palette(
        rgbs, max_colors=S.DEFAULT_MAX_PALETTE, merge_dist=S.PROVIDER_MERGE_DIST_RGB)
    if not palette:
        return frames
    return [[[None if rgb is None else S._nearest_rgb(rgb, palette) for rgb in row]
             for row in frame] for frame in frames]


def _panel_silhouette(draw, frames, run, dy, fw, fh, cell_w) -> None:
    """Occupancy change per adjacent pair — the silhouette/loop/min-pair defect."""
    half = max(1, SCALE // 2)
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        x0 = PAD + i * (cell_w + PAD) + cell_w // 2
        for y in range(min(fh, len(a), len(b))):
            for x in range(min(fw, len(a[y]), len(b[y]))):
                oa, ob = a[y][x] is not None, b[y][x] is not None
                if oa != ob:
                    draw.rectangle([x0 + x * half, dy + y * half,
                                    x0 + (x + 1) * half - 1, dy + (y + 1) * half - 1],
                                   fill=(220, 60, 60))
                elif oa:
                    draw.point((x0 + x * half, dy + y * half), fill=(60, 60, 70))
        draw.text((x0, dy + fh * half + 2), f"{i}->{i+1}", fill=(150, 150, 160))


def _panel_palette(draw, frames, run, dy, fw, fh, cell_w) -> None:
    """Per-frame palette histogram — the drift defect a silhouette diff cannot show."""
    bar_h = fh * max(1, SCALE // 2)
    # Histogram the quantized frames — the gate measures drift on the shared
    # palette, so raw provider colours would show hundreds of near-zero slivers.
    hists = [S.palette_histogram(f) for f in _quantized(frames)]
    colours = sorted({c for h in hists for c in h},
                     key=lambda c: -sum(h.get(c, 0.0) for h in hists))
    for i, hist in enumerate(hists):
        x0 = PAD + i * (cell_w + PAD)
        y = dy
        for colour in colours:
            share = hist.get(colour, 0.0)
            h = int(round(share * bar_h))
            if h:
                draw.rectangle([x0, y, x0 + cell_w - 1, y + h - 1], fill=tuple(colour))
                y += h
        draw.text((x0, dy + bar_h + 2), f"f{i} palette", fill=(150, 150, 160))


def _panel_displacement(draw, frames, run, dy, fw, fh, cell_w) -> None:
    """Best-alignment shift per transition — the vector the displacement gate reads."""
    shifts = S.adjacent_transition_shifts(_quantized(frames))
    for i, entry in enumerate(shifts):
        x0 = PAD + i * (cell_w + PAD)
        dx, dy_ = entry["dx"], entry["dy"]
        draw.text((x0, dy), f"{entry['from']}->{entry['to']}", fill=(150, 150, 160))
        draw.text((x0, dy + BAND), f"shift ({dx:+d},{dy_:+d})", fill=(220, 160, 60))
        cx, cy = x0 + cell_w // 2, dy + BAND * 4
        draw.line([cx, cy, cx + dx * SCALE, cy + dy_ * SCALE], fill=(220, 160, 60), width=2)
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(190, 190, 200))


PANEL_FOR = {
    "silhouette_budget": _panel_silhouette,
    "loop_closure_pass": _panel_silhouette,
    "min_pair_cohort_pass": _panel_silhouette,
    "palette_drift_pass": _panel_palette,
    "displacement_pass": _panel_displacement,
    "baseline_row_stable": _panel_silhouette,
}


def _band_lines(run: dict[str, Any]) -> list[str]:
    lines = [f"{run['isolation']}   target={run['target_gate']}   "
             f"class={run['motion_class']}"]
    for gate, r in run["gates"].items():
        mark = {"pass": "  ok ", "fail": " FAIL", "undecidable": " ?? "}[r["outcome"]]
        star = "*" if gate == run["target_gate"] else " "
        detail = (f"{r['metric']:.4f} vs budget {r['budget']}"
                  if r["metric"] is not None and r["budget"] is not None
                  else (r["reason"] or ""))
        lines.append(f"{star}{mark}  {gate:<22} {detail}")
    pf = run.get("primary_failure")
    lines.append(f"primary_failure: {pf['code'] if pf else 'none'}"
                 + (f" ({pf['gate']})" if pf and pf.get("gate") else ""))
    lines += [f"caveat: {c}" for c in run.get("caveats", [])]
    lines.append(f"raw_sha256: {run['raw_sha256']}")
    return lines


def build_composite(path: pathlib.Path, run: dict[str, Any], out: pathlib.Path) -> pathlib.Path:
    """One image, bound to the raw hash: frames, adjacent diffs, verdict band."""
    frames = _frames(path)
    if frames is None:
        raise ValueError("cannot composite a strip that did not slice")
    fw, fh = S.DEFAULT_LAYOUT.frame_w, S.DEFAULT_LAYOUT.frame_h
    n = len(frames)
    cell_w, cell_h = fw * SCALE, fh * SCALE
    band_lines = _band_lines(run)
    width = max(PAD * 2 + n * cell_w + (n - 1) * PAD,
                PAD * 2 + max(len(line) for line in band_lines) * 6)
    height = PAD * 4 + cell_h + fh * max(1, SCALE // 2) + BAND * (len(band_lines) + 2)

    im = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(im)

    for i, frame in enumerate(frames):
        x0 = PAD + i * (cell_w + PAD)
        for y in range(min(fh, len(frame))):
            for x in range(min(fw, len(frame[y]))):
                rgb = frame[y][x]
                if rgb is not None:
                    draw.rectangle(
                        [x0 + x * SCALE, PAD + y * SCALE,
                         x0 + (x + 1) * SCALE - 1, PAD + (y + 1) * SCALE - 1],
                        fill=tuple(rgb),
                    )
        draw.text((x0, PAD + cell_h + 2), f"f{i}", fill=(150, 150, 160))

    # Decision (#20): the evidence panel is chosen by target Gate, so the reviewer
    # sees the defect the Gate actually measures. A silhouette diff under a palette
    # target renders near-blank and misleads.
    dy = PAD * 2 + cell_h + BAND
    panel = PANEL_FOR.get(run["target_gate"], _panel_silhouette)
    panel(draw, frames, run, dy, fw, fh, cell_w)

    ty = height - BAND * (len(band_lines) + 1)
    verdict_colour = {"ISOLATED": (90, 200, 110), "NOT_ISOLATED": (230, 170, 60),
                      "INDETERMINATE": (200, 80, 80)}[run["isolation"]]
    for i, line in enumerate(band_lines):
        draw.text((PAD, ty + i * BAND), line,
                  fill=verdict_colour if i == 0 else (190, 190, 200))

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    run["composite"] = {"path": str(out),
                        "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("png", type=pathlib.Path)
    p.add_argument("--motion-class", required=True)
    p.add_argument("--target-gate", required=True, choices=GATE_ORDER)
    p.add_argument("--composite", type=pathlib.Path)
    args = p.parse_args(argv)

    path = args.png if args.png.exists() else INBOX / args.png.name
    run = measure(path, args.motion_class, args.target_gate)
    if args.composite and run["structural"].get("recovered"):
        build_composite(path, run, args.composite)
    print(json.dumps(run, indent=2))
    return 0 if run["isolation"] == "ISOLATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
