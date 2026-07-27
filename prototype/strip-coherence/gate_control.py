#!/usr/bin/env python3
"""COMPATIBILITY — score one candidate Gate control via pipeline.gate_control.

Forwards measurement, isolation, primary-failure, and retry logic to the
production scorer. Review-composite rendering remains here until Wave C lands
the production packet builder.

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

from pipeline import gate_control as prod
from pipeline import strip as S

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"

GATE_ORDER = prod.GATE_ORDER
SpecificationError = prod.SpecificationError
applicable_gates = prod.applicable_gates
gate_config_hash = prod.gate_config_hash
measure = prod.measure
primary_failure = prod.primary_failure
retry_action = prod.retry_action
corpus_layout = prod.corpus_layout

# --- review composite (prototype-only until packet builder promotion) --------

SCALE = 6
PAD = 8
BAND = 11


def _frames(path: pathlib.Path) -> list[list[list[Any]]] | None:
    return S.load_provider_frames(path, corpus_layout())


def _quantized(frames):
    rgbs = S.collect_opaque_rgbs(frames)
    palette, _ = S.build_shared_palette(
        rgbs, max_colors=S.DEFAULT_MAX_PALETTE, merge_dist=S.PROVIDER_MERGE_DIST_RGB
    )
    if not palette:
        return frames
    return [
        [[None if rgb is None else S._nearest_rgb(rgb, palette) for rgb in row] for row in frame]
        for frame in frames
    ]


def _panel_silhouette(draw, frames, run, dy, fw, fh, cell_w) -> None:
    half = max(1, SCALE // 2)
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        x0 = PAD + i * (cell_w + PAD) + cell_w // 2
        for y in range(min(fh, len(a), len(b))):
            for x in range(min(fw, len(a[y]), len(b[y]))):
                oa, ob = a[y][x] is not None, b[y][x] is not None
                if oa != ob:
                    draw.rectangle(
                        [
                            x0 + x * half,
                            dy + y * half,
                            x0 + (x + 1) * half - 1,
                            dy + (y + 1) * half - 1,
                        ],
                        fill=(220, 60, 60),
                    )
                elif oa:
                    draw.point((x0 + x * half, dy + y * half), fill=(60, 60, 70))
        draw.text((x0, dy + fh * half + 2), f"{i}->{i+1}", fill=(150, 150, 160))


def _panel_palette(draw, frames, run, dy, fw, fh, cell_w) -> None:
    bar_h = fh * max(1, SCALE // 2)
    hists = [S.palette_histogram(f) for f in _quantized(frames)]
    colours = sorted(
        {c for h in hists for c in h},
        key=lambda c: -sum(h.get(c, 0.0) for h in hists),
    )
    for i, hist in enumerate(hists):
        x0 = PAD + i * (cell_w + PAD)
        y = dy
        for colour in colours:
            share = hist.get(colour, 0.0)
            height = int(round(share * bar_h))
            if height:
                draw.rectangle(
                    [x0, y, x0 + cell_w - 1, y + height - 1],
                    fill=tuple(colour),
                )
                y += height
        draw.text((x0, dy + bar_h + 2), f"f{i} palette", fill=(150, 150, 160))


def _panel_displacement(draw, frames, run, dy, fw, fh, cell_w) -> None:
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
    lines = [
        f"{run['isolation']}   target={run['target_gate']}   class={run['motion_class']}"
    ]
    for gate, row in run["gates"].items():
        mark = {"pass": "  ok ", "fail": " FAIL", "undecidable": " ?? "}[row["outcome"]]
        star = "*" if gate == run["target_gate"] else " "
        detail = (
            f"{row['metric']:.4f} vs budget {row['budget']}"
            if row["metric"] is not None and row["budget"] is not None
            else (row["reason"] or "")
        )
        lines.append(f"{star}{mark}  {gate:<22} {detail}")
    pf = run.get("primary_failure")
    lines.append(
        f"primary_failure: {pf['code'] if pf else 'none'}"
        + (f" ({pf['gate']})" if pf and pf.get("gate") else "")
    )
    lines += [f"caveat: {c}" for c in run.get("caveats", [])]
    lines.append(f"raw_sha256: {run['raw_sha256']}")
    return lines


def build_composite(path: pathlib.Path, run: dict[str, Any], out: pathlib.Path) -> pathlib.Path:
    frames = _frames(path)
    if frames is None:
        raise ValueError("cannot composite a strip that did not slice")
    fw, fh = S.DEFAULT_LAYOUT.frame_w, S.DEFAULT_LAYOUT.frame_h
    n = len(frames)
    cell_w, cell_h = fw * SCALE, fh * SCALE
    band_lines = _band_lines(run)
    width = max(
        PAD * 2 + n * cell_w + (n - 1) * PAD,
        PAD * 2 + max(len(line) for line in band_lines) * 6,
    )
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
                        [
                            x0 + x * SCALE,
                            PAD + y * SCALE,
                            x0 + (x + 1) * SCALE - 1,
                            PAD + (y + 1) * SCALE - 1,
                        ],
                        fill=tuple(rgb),
                    )
        draw.text((x0, PAD + cell_h + 2), f"f{i}", fill=(150, 150, 160))

    dy = PAD * 2 + cell_h + BAND
    panel = PANEL_FOR.get(run["target_gate"], _panel_silhouette)
    panel(draw, frames, run, dy, fw, fh, cell_w)

    ty = height - BAND * (len(band_lines) + 1)
    verdict_colour = {
        "ISOLATED": (90, 200, 110),
        "NOT_ISOLATED": (230, 170, 60),
        "INDETERMINATE": (200, 80, 80),
    }[run["isolation"]]
    for i, line in enumerate(band_lines):
        draw.text(
            (PAD, ty + i * BAND),
            line,
            fill=verdict_colour if i == 0 else (190, 190, 200),
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    run["composite"] = {
        "path": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
    }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png", type=pathlib.Path)
    parser.add_argument("--motion-class", required=True)
    parser.add_argument("--target-gate", required=True, choices=GATE_ORDER)
    parser.add_argument("--composite", type=pathlib.Path)
    parser.add_argument("--recorded-at")
    parser.add_argument("--scorer-commit")
    args = parser.parse_args(argv)

    path = args.png if args.png.exists() else INBOX / args.png.name
    try:
        run = measure(
            path,
            args.motion_class,
            args.target_gate,
            recorded_at=args.recorded_at or prod.utc_now(),
            scorer_commit=args.scorer_commit or prod.git_commit(),
        )
    except SpecificationError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2
    if args.composite and run["structural"].get("recovered"):
        build_composite(path, run, args.composite)
    print(json.dumps(run, indent=2))
    return 0 if run["isolation"] == "ISOLATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
