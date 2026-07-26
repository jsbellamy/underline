#!/usr/bin/env python3
"""PROTOTYPE — alignment minimum sharpness across the corpus.

Displacement-span (±4) and registration-span (±1) sharpness per transition.
A margin of 0.0 means the best shift is degenerate — silhouette_diff and
displacement both read an arbitrary winner.

Run before trusting any tight separation margin.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import corpus  # noqa: E402
import strip as S  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
MANIFEST = HERE / "prompts" / "manifest.json"


def _layout() -> S.StripLayout:
    base = S.DEFAULT_LAYOUT
    return S.StripLayout(
        frame_w=base.frame_w,
        frame_h=base.frame_h,
        frame_count=base.frame_count,
        gutter=base.gutter,
        pitch_px=base.pitch_px,
        margin_cells=0,
    )


def _score_sample(sample_id: str, motion_class: str, path: pathlib.Path) -> dict:
    cells, _ = S.recover_strip_cells(path, _layout())
    frames, _ = S.slice_frames_pitch(cells, frame_count=S.DEFAULT_LAYOUT.frame_count)
    q, anchor = S.quantize_motion_frames(frames, motion_class)
    budget = S.MOTION_CLASSES[motion_class]
    disp = S.alignment_sharpness_report(q, loops=budget.loops, anchor=anchor)
    reg = S.registration_sharpness_report(q, loops=budget.loops, anchor=anchor)
    return {
        "id": sample_id,
        "motion_class": motion_class,
        "displacement_min_margin": disp["min_margin"],
        "displacement_worst_pair": disp["worst_pair"],
        "registration_min_margin": reg["min_margin"],
        "registration_worst_pair": reg["worst_pair"],
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    rows: list[dict] = []
    for sample in manifest["samples"]:
        path = corpus.find_png(sample["id"])
        if path is None:
            continue
        try:
            rows.append(_score_sample(sample["id"], sample["motion_class"], path))
        except (ValueError, OSError) as error:
            print(f"{sample['id']:<24} {'--':<10} recover failed: {str(error)[:40]}")

    print(
        f"{'sample':<24} {'class':<10} {'disp_min':>9} {'disp_worst':>11} "
        f"{'reg_min':>8} {'reg_worst':>10}"
    )
    print("-" * 80)
    for row in rows:
        dw = row["displacement_worst_pair"]
        rw = row["registration_worst_pair"]
        dw_txt = f"{dw[0]}→{dw[1]}" if dw else "—"
        rw_txt = f"{rw[0]}→{rw[1]}" if rw else "—"
        print(
            f"{row['id']:<24} {row['motion_class']:<10} "
            f"{row['displacement_min_margin']:>9.4f} {dw_txt:>11} "
            f"{row['registration_min_margin']:>8.4f} {rw_txt:>10}"
        )

    flagged = [r for r in rows if r["registration_min_margin"] < 0.02]
    if flagged:
        print("\nLow registration sharpness (<0.02) — silhouette numbers less determinate:")
        for row in flagged:
            print(f"  {row['id']}: reg_min={row['registration_min_margin']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
