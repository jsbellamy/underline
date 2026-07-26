"""PROTOTYPE PROBE — is the corpus's silhouette failure motion or misalignment?

Six of nine corpus samples have uneven segment widths, so `normalize_frame_widths`
cropped them to the narrowest from the LEFT. NOTES.md says a silhouette failure on
those rows must be checked with a shift scan before it is believed. This does that for
every sample at once, and additionally scores an anchored alignment (content-centroid x,
baseline y) as the candidate replacement for left-cropping.

Reads: raw segments, pre-normalization. Delete once the alignment question is settled.
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
SPAN = 3


def segments_raw(path: pathlib.Path) -> tuple[list, dict]:
    """Slice into per-frame cell grids WITHOUT normalizing widths."""
    layout = S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )
    cells, _ = S.recover_strip_cells(path, layout)
    segs = S.opaque_segments(cells)
    frames = [[row[a : b + 1] for row in cells] for a, b in segs]
    return frames, {"widths": [b - a + 1 for a, b in segs]}


def sil_frac(a, b, dx: int, dy: int) -> float:
    """Silhouette diff of b shifted by (dx, dy) against a, above a's baseline."""
    baseline = S.baseline_row(a)
    if baseline is None:
        baseline = len(a)
    changed = union = 0
    for y in range(baseline):
        for x in range(len(a[y])):
            ca = a[y][x]
            yb, xb = y + dy, x + dx
            cb = None
            if 0 <= yb < len(b) and 0 <= xb < len(b[yb]):
                cb = b[yb][xb]
            if ca is None and cb is None:
                continue
            union += 1
            if (ca is None) != (cb is None):
                changed += 1
    return changed / union if union else 0.0


def bbox(frame) -> tuple[int, int, int, int] | None:
    xs = [x for y in range(len(frame)) for x in range(len(frame[y])) if frame[y][x] is not None]
    ys = [y for y in range(len(frame)) for x in range(len(frame[y])) if frame[y][x] is not None]
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def anchor_shift(a, b) -> tuple[int, int]:
    """Shift that lines b's content up with a's by bbox centre-x and bottom-y."""
    ba, bb = bbox(a), bbox(b)
    if ba is None or bb is None:
        return 0, 0
    ax0, ax1, _, ay1 = ba
    bx0, bx1, _, by1 = bb
    return ((bx0 + bx1) - (ax0 + ax1)) // 2, by1 - ay1


def main() -> int:
    samples = json.loads(MANIFEST.read_text())["samples"]
    print(f"{'sample':<22} {'pair':<6} {'left-crop':>9} {'best':>16} {'anchored':>9}")
    print("-" * 72)

    for s in samples:
        path = INBOX / f"{s['id']}.png"
        if not path.exists():
            continue
        try:
            frames, meta = segments_raw(path)
        except (ValueError, OSError) as error:
            print(f"{s['id']:<22} {'--':<6} recover failed: {str(error)[:40]}")
            continue
        if len(frames) != 4:
            print(f"{s['id']:<22} {'--':<6} {len(frames)} segments, skipped")
            continue

        pairs = [(0, 1), (1, 2), (2, 3), (3, 0)]
        rows = []
        for i, j in pairs:
            base = sil_frac(frames[i], frames[j], 0, 0)
            scan = [
                (dx, dy, sil_frac(frames[i], frames[j], dx, dy))
                for dx in range(-SPAN, SPAN + 1)
                for dy in range(-1, 2)
            ]
            bdx, bdy, bval = min(scan, key=lambda t: t[2])
            adx, ady = anchor_shift(frames[i], frames[j])
            aval = sil_frac(frames[i], frames[j], adx, ady)
            rows.append((f"{i}->{j}", base, bdx, bdy, bval, aval))

        label = s["id"]
        for name, base, bdx, bdy, bval, aval in rows:
            print(f"{label:<22} {name:<6} {base:>9.3f} "
                  f"{f'{bval:.3f} @{bdx:+d},{bdy:+d}':>16} {aval:>9.3f}")
            label = ""
        worst_base = max(r[1] for r in rows)
        worst_best = max(r[4] for r in rows)
        worst_anch = max(r[5] for r in rows)
        verdict = "MISALIGNMENT" if worst_best < 0.28 <= worst_base else "real motion"
        print(f"{'':<22} {'MAX':<6} {worst_base:>9.3f} {worst_best:>16.3f} "
              f"{worst_anch:>9.3f}   {verdict}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
