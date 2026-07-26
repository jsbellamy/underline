"""PROTOTYPE PROBE — decompose the provider motion diff. Delete when answered.

Question: the real strip passes only at adjacent<=0.55. Are those changed cells
real motion, shading noise, or frame misalignment?
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import strip as S  # noqa: E402

INBOX = pathlib.Path(__file__).resolve().parent / "inbox" / "miner-idle-strip.png"


def classify(a, b, baseline):
    """Split changed cells above baseline into silhouette vs shading."""
    sil = shade = union = 0
    for y in range(min(len(a), len(b))):
        if y >= baseline:
            continue
        for x in range(min(len(a[y]), len(b[y]))):
            ca, cb = a[y][x], b[y][x]
            if ca is None and cb is None:
                continue
            union += 1
            if ca == cb:
                continue
            if (ca is None) != (cb is None):
                sil += 1
            else:
                shade += 1
    return sil, shade, union


def shift_scan(a, b, baseline, span=3):
    """Best whole-cell x-shift of b against a. If a shift beats 0, frames are misaligned."""
    best = []
    for dx in range(-span, span + 1):
        changed = union = 0
        for y in range(min(len(a), len(b))):
            if y >= baseline:
                continue
            for x in range(len(a[y])):
                xb = x + dx
                ca = a[y][x]
                cb = b[y][xb] if 0 <= xb < len(b[y]) else None
                if ca is None and cb is None:
                    continue
                union += 1
                if ca != cb:
                    changed += 1
        best.append((dx, round(changed / union, 4) if union else 0.0))
    return best


def main() -> int:
    layout = S.DEFAULT_LAYOUT
    probe_layout = S.StripLayout(
        frame_w=layout.frame_w, frame_h=layout.frame_h,
        frame_count=layout.frame_count, gutter=layout.gutter,
        pitch_px=layout.pitch_px, margin_cells=0,
    )
    cells, recovered = S.recover_strip_cells(INBOX, probe_layout)
    frames, meta = S.slice_frames_auto(cells, frame_count=layout.frame_count)
    print(f"grid={meta['grid']} segments={meta['segments']} widths={meta['segment_widths']} norm_w={meta['normalized_width']}")

    rgbs = S.collect_opaque_rgbs(frames)
    palette, pstats = S.build_shared_palette(
        rgbs, max_colors=S.DEFAULT_MAX_PALETTE, merge_dist=S.PROVIDER_MERGE_DIST_RGB
    )
    q = [[[None if c is None else S._nearest_rgb(c, palette) for c in row] for row in f]
         for f in frames]
    print(f"unique_rgb={pstats['input_unique']} clusters={pstats['clusters']} palette={pstats['palette_size']}")

    # Per-frame content bbox: does the character sit at the same x offset in each frame?
    print("\n-- per-frame content bbox (x0,x1,y0,y1) --")
    for i, f in enumerate(q):
        xs = [x for y in range(len(f)) for x in range(len(f[y])) if f[y][x] is not None]
        ys = [y for y in range(len(f)) for x in range(len(f[y])) if f[y][x] is not None]
        print(f"  f{i}: x={min(xs)}..{max(xs)}  y={min(ys)}..{max(ys)}  baseline={S.baseline_row(f)}")

    print("\n-- changed-cell decomposition (motion-only, above baseline) --")
    pairs = [(i, i + 1) for i in range(len(q) - 1)] + [(len(q) - 1, 0)]
    for i, j in pairs:
        baseline = S.baseline_row(q[i])
        sil, shade, union = classify(q[i], q[j], baseline)
        tot = sil + shade
        print(f"  {i}->{j}: frac={tot/union:.3f}  silhouette={sil} ({sil/max(tot,1):.0%})  "
              f"shading={shade} ({shade/max(tot,1):.0%})  union={union}")

    print("\n-- x-shift scan (dx: frac) — if dx!=0 wins, frames are misaligned --")
    for i, j in pairs:
        baseline = S.baseline_row(q[i])
        scan = shift_scan(q[i], q[j], baseline)
        best = min(scan, key=lambda t: t[1])
        print(f"  {i}->{j}: " + "  ".join(f"{dx:+d}:{v:.2f}" for dx, v in scan)
              + f"   BEST dx={best[0]:+d} @ {best[1]:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
