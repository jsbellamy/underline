"""PROTOTYPE SWEEP — can quantizer tuning get the real strip under 0.28? Delete when answered."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import strip as S  # noqa: E402

INBOX = pathlib.Path(__file__).resolve().parent / "inbox" / "miner-idle-strip.png"


def load_frames():
    layout = S.DEFAULT_LAYOUT
    probe = S.StripLayout(
        frame_w=layout.frame_w, frame_h=layout.frame_h,
        frame_count=layout.frame_count, gutter=layout.gutter,
        pitch_px=layout.pitch_px, margin_cells=0,
    )
    cells, _ = S.recover_strip_cells(INBOX, probe)
    frames, _ = S.slice_frames_auto(cells, frame_count=layout.frame_count)
    return frames


def quantize(frames, max_colors, merge_dist):
    rgbs = S.collect_opaque_rgbs(frames)
    palette, stats = S.build_shared_palette(
        rgbs, max_colors=max_colors, merge_dist=merge_dist
    )
    q = [[[None if c is None else S._nearest_rgb(c, palette) for c in row] for row in f]
         for f in frames]
    return q, stats


def fracs(q, mode):
    """mode: 'full' (silhouette+shading) or 'sil' (occupancy only)."""
    pairs = [(i, i + 1) for i in range(len(q) - 1)] + [(len(q) - 1, 0)]
    out = []
    for i, j in pairs:
        baseline = S.baseline_row(q[i])
        changed = union = 0
        for y in range(min(len(q[i]), len(q[j]))):
            if y >= baseline:
                continue
            for x in range(min(len(q[i][y]), len(q[j][y]))):
                ca, cb = q[i][y][x], q[j][y][x]
                if ca is None and cb is None:
                    continue
                union += 1
                if mode == "sil":
                    if (ca is None) != (cb is None):
                        changed += 1
                elif ca != cb:
                    changed += 1
        out.append(round(changed / union, 3) if union else 0.0)
    return out


def hist_drift(frames):
    """Total-variation distance between per-frame color histograms (0=identical mix)."""
    from collections import Counter

    hists = []
    for f in frames:
        c = Counter(rgb for row in f for rgb in row if rgb is not None)
        n = sum(c.values()) or 1
        hists.append({k: v / n for k, v in c.items()})
    keys = set().union(*[set(h) for h in hists])
    pairs = [(i, i + 1) for i in range(len(frames) - 1)] + [(len(frames) - 1, 0)]
    return [
        round(0.5 * sum(abs(hists[i].get(k, 0) - hists[j].get(k, 0)) for k in keys), 3)
        for i, j in pairs
    ]


def main() -> int:
    frames = load_frames()

    print("=== A. quantizer sweep, full cell diff (silhouette + shading) ===")
    print(f"{'colors':>7} {'merge':>6} {'clusters':>9}  adj 0-1  1-2  2-3   loop 3-0   max_adj")
    for max_colors in (4, 6, 8, 10, 12, 16):
        for merge_dist in (64, 96, 128, 160):
            q, st = quantize(frames, max_colors, merge_dist)
            f = fracs(q, "full")
            mark = "  <= PASS@0.28" if max(f[:-1]) <= 0.28 and f[-1] <= 0.28 else ""
            print(f"{max_colors:>7} {merge_dist:>6} {st['clusters']:>9}   "
                  f"{f[0]:.3f} {f[1]:.3f} {f[2]:.3f}    {f[3]:.3f}     {max(f[:-1]):.3f}{mark}")

    print("\n=== B. silhouette-only diff (occupancy flips, quantizer-independent) ===")
    q, _ = quantize(frames, 16, 64)
    f = fracs(q, "sil")
    print(f"  adjacent = {f[0]:.3f} {f[1]:.3f} {f[2]:.3f}   loop = {f[3]:.3f}   max_adj={max(f[:-1]):.3f}")
    print(f"  PASS@0.28: {max(f[:-1]) <= 0.28 and f[-1] <= 0.28}")

    print("\n=== C. silhouette-only on synthetic pass fixture (sanity: gate still discriminates?) ===")
    fx = pathlib.Path(__file__).resolve().parent / "fixtures"
    for name in ("synthetic-pass", "synthetic-baseline_fail", "synthetic-palette_fail"):
        p = fx / f"{name}.png"
        if not p.exists():
            print(f"  {name}: missing")
            continue
        cells, _ = S.recover_strip_cells(p, S.DEFAULT_LAYOUT)
        fr, _ = S.slice_frames(cells, S.DEFAULT_LAYOUT)
        if fr is None:
            print(f"  {name}: slice failed")
            continue
        sf = fracs(fr, "sil")
        ff = fracs(fr, "full")
        print(f"  {name}: sil={sf}  full={ff}  hist={hist_drift(fr)}")

    print("\n=== D. palette histogram drift (TV distance between frames) ===")
    print("  hypothesis: re-shading keeps the distribution; a recolor moves it")
    for merge_dist, max_colors in ((128, 8), (96, 10), (64, 16)):
        q, st = quantize(frames, max_colors, merge_dist)
        print(f"  real strip (colors={max_colors} merge={merge_dist}, "
              f"clusters={st['clusters']}): {hist_drift(q)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
