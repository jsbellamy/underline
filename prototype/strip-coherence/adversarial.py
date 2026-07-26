#!/usr/bin/env python3
"""PROTOTYPE — does the split gate still REJECT? Mutate the real strip's frames.

The strict budgets only mean something if a genuinely bad frame trips them.
Each mutation targets one gate; every row should read FAIL.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import strip as S  # noqa: E402

INBOX = pathlib.Path(__file__).resolve().parent / "inbox" / "miner-idle-strip.png"


def real_frames():
    layout = S.DEFAULT_LAYOUT
    probe = S.StripLayout(
        frame_w=layout.frame_w, frame_h=layout.frame_h,
        frame_count=layout.frame_count, gutter=layout.gutter,
        pitch_px=layout.pitch_px, margin_cells=0,
    )
    cells, _ = S.recover_strip_cells(INBOX, probe)
    frames, _ = S.slice_frames_auto(cells, frame_count=layout.frame_count)
    return frames


def recolour(frames, idx=2):
    """Repaint frame idx's body — a recolour, silhouette untouched."""
    out = [[row[:] for row in f] for f in frames]
    out[idx] = [
        [None if c is None else (min(255, c[0] + 110), c[1] // 3, c[2] // 3) for c in row]
        for row in out[idx]
    ]
    return out


def hop(frames, idx=2, dy=3):
    """Lift frame idx off the ground — feet must not move."""
    out = [[row[:] for row in f] for f in frames]
    w = len(out[idx][0])
    out[idx] = out[idx][dy:] + [[None] * w for _ in range(dy)]
    return out


def wrong_pose(frames, idx=2):
    """Mirror frame idx — same palette, same baseline, totally different silhouette."""
    out = [[row[:] for row in f] for f in frames]
    out[idx] = [list(reversed(row)) for row in out[idx]]
    return out


def slide(frames, idx=2, dx=3):
    """Translate frame idx sideways — character drifts across the strip."""
    out = [[row[:] for row in f] for f in frames]
    out[idx] = [[None] * dx + row[:-dx] for row in out[idx]]
    return out


def report(name, frames, want_pass):
    r = S.coherence_split(frames)
    sil = max((row["frac"] for row in r["silhouette_adjacent"]), default=0.0)
    tripped = [
        g for g in ("dimension_parity", "baseline_row_stable", "silhouette_budget",
                    "loop_closure_pass", "palette_drift_pass")
        if not r[g]
    ]
    ok = r["pass"] == want_pass
    print(f"{'ok ' if ok else 'MISMATCH'}  {name:<22} "
          f"{'PASS' if r['pass'] else 'FAIL'} (want {'PASS' if want_pass else 'FAIL'})  "
          f"sil_max={sil:.3f} drift_max={r['worst_palette_drift']:.3f}"
          + (f"  tripped={tripped}" if tripped else ""))
    return ok


def main() -> int:
    frames = real_frames()
    checks = [
        ("baseline (untouched)", frames, True),
        ("recolour frame 2", recolour(frames), False),
        ("hop frame 2 (+3 rows)", hop(frames), False),
        ("mirror frame 2", wrong_pose(frames), False),
        ("slide frame 2 (+3 cols)", slide(frames), False),
    ]
    return 0 if all(report(n, f, w) for n, f, w in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
