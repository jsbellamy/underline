#!/usr/bin/env python3
"""PROTOTYPE — falsify the antisymmetric displacement tamper rule on good strips.

Pre-registered rule (see docs/strip-acquisition-contract.md):
  A frame is tampered when its in-shift and out-shift are approximately opposite
  (residual |in+out| ≤ DISPLACEMENT_PAIR_TOLERANCE) with Chebyshev |in| ≥
  DISPLACEMENT_MIN_MAGNITUDE.

loops=True classes scan all frames including wrap-around; loops=False scans interior
frames only. Intended for airborne only when promoted — grounded classes already have
hop/slide coverage via silhouette and baseline gates.

Run over every manifest-good strip before promoting this to a gate.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import adversarial  # noqa: E402
import corpus  # noqa: E402
import strip as S  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"
MANIFEST = HERE / "prompts" / "manifest.json"

EXTRA_GOOD = ("miner-idle-strip",)
AIRBORNE_BASELINES = ("04-bat-flap", "16-moth-flap", "17-wisp-float")


def _corpus_layout() -> S.StripLayout:
    layout = S.DEFAULT_LAYOUT
    return S.StripLayout(
        frame_w=layout.frame_w,
        frame_h=layout.frame_h,
        frame_count=layout.frame_count,
        gutter=layout.gutter,
        pitch_px=layout.pitch_px,
        margin_cells=0,
    )


def _load_quantized(path: pathlib.Path, motion_class: str):
    cells, _ = S.recover_strip_cells(path, _corpus_layout())
    frames, _ = S.slice_frames_pitch(cells, frame_count=S.DEFAULT_LAYOUT.frame_count)
    return S.quantize_motion_frames(frames, motion_class)


def _fmt_shift(dx: int, dy: int) -> str:
    return f"({dx:+d},{dy:+d})"


def _displacement_loops(motion_class: str) -> bool:
    """loops-aware scan only for airborne — the intended gate class."""
    budget = S.MOTION_CLASSES[motion_class]
    return budget.loops and motion_class == "airborne"


def _displacement_flags(q, motion_class: str, anchor):
    return S.antisymmetric_displacement_flags(
        q, loops=_displacement_loops(motion_class), anchor=anchor
    )


def _load_airborne_frames(sample_id: str):
    path = INBOX / f"{sample_id}.png"
    cells, _ = S.recover_strip_cells(path, _corpus_layout())
    return S.slice_frames_pitch(cells, frame_count=S.DEFAULT_LAYOUT.frame_count)[0]


def _detects_tamper(
    frames,
    motion_class: str,
    *,
    idx: int,
    mutation: str,
    magnitude: int,
) -> bool:
    if mutation == "hop":
        mutated = adversarial.hop(frames, idx=idx, dy=magnitude)
    else:
        mutated = adversarial.slide(frames, idx=idx, dx=magnitude)
    q, anchor = S.quantize_motion_frames(mutated, motion_class)
    flags = _displacement_flags(q, motion_class, anchor)
    return any(f["frame"] == idx for f in flags)


def probe_sample(sample_id: str, motion_class: str, path: pathlib.Path) -> dict:
    q, anchor = _load_quantized(path, motion_class)
    transitions = S.adjacent_transition_shifts(q, anchor=anchor)
    flags = (
        _displacement_flags(q, motion_class, anchor)
        if motion_class == "airborne"
        else []
    )
    return {
        "id": sample_id,
        "motion_class": motion_class,
        "transitions": transitions,
        "flags": flags,
    }


def _print_coverage_grids() -> None:
    print("\n--- airborne coverage grid (loops=True, not gate-ready) ---")
    print("A. tampered-frame index (hop/slide magnitude=3)")
    print(f"{'':22}  " + "  ".join(f"f{i} hop slide" for i in range(4)))
    for sample_id in AIRBORNE_BASELINES:
        frames = _load_airborne_frames(sample_id)
        cells = []
        for idx in range(4):
            hop = "D" if _detects_tamper(
                frames, "airborne", idx=idx, mutation="hop", magnitude=3
            ) else "MISS"
            slide = "D" if _detects_tamper(
                frames, "airborne", idx=idx, mutation="slide", magnitude=3
            ) else "MISS"
            cells.append(f"{hop:>3} {slide:>5}")
        print(f"{sample_id:<22}  " + "  ".join(cells))

    print("\nB. frame 2, varying magnitude")
    mag_header = " " * 22 + "  " + "  ".join(
        f"hop{m}" for m in (2, 3, 4)
    ) + "   " + "  ".join(f"slide{m}" for m in (2, 3, 4))
    print(mag_header)
    for sample_id in AIRBORNE_BASELINES:
        frames = _load_airborne_frames(sample_id)
        hop_cells = [
            "D" if _detects_tamper(frames, "airborne", idx=2, mutation="hop", magnitude=m)
            else "MISS"
            for m in (2, 3, 4)
        ]
        slide_cells = [
            "D"
            if _detects_tamper(
                frames, "airborne", idx=2, mutation="slide", magnitude=m
            )
            else "MISS"
            for m in (2, 3, 4)
        ]
        row = f"{sample_id:<22}  " + "  ".join(f"{c:>4}" for c in hop_cells)
        row += "   " + "  ".join(f"{c:>6}" for c in slide_cells)
        print(row)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    good = [s for s in manifest["samples"] if s.get("contract_expect") == "PASS"]
    rows: list[dict] = []
    false_positives: list[dict] = []

    for sample in good:
        path = corpus.find_png(sample["id"])
        if path is None:
            continue
        row = probe_sample(sample["id"], sample["motion_class"], path)
        rows.append(row)
        if row["flags"]:
            false_positives.append(row)

    for label in EXTRA_GOOD:
        path = HERE / "inbox" / f"{label}.png"
        if not path.exists():
            continue
        row = probe_sample(label, "idle", path)
        rows.append(row)
        if row["flags"]:
            false_positives.append(row)

    print(
        "Antisymmetric displacement falsification "
        f"(span=±{S.DISPLACEMENT_PROBE_SPAN}, min_mag≥{S.DISPLACEMENT_MIN_MAGNITUDE}, "
        f"pair_tol≤{S.DISPLACEMENT_PAIR_TOLERANCE}, loops-aware)"
    )
    print("-" * 72)
    for row in rows:
        trans = " ".join(_fmt_shift(t["dx"], t["dy"]) for t in row["transitions"])
        flag_txt = ""
        if row["flags"]:
            parts = [
                f"frame {f['frame']} in={_fmt_shift(*f['in_shift'])} "
                f"out={_fmt_shift(*f['out_shift'])}"
                for f in row["flags"]
            ]
            flag_txt = "  **FLAG** " + "; ".join(parts)
        print(f"{row['id']:<24} {row['motion_class']:<10} {trans}{flag_txt}")

    print("-" * 72)
    print(f"airborne good strips scored: {sum(1 for r in rows if r['motion_class'] == 'airborne')}")
    airborne_fps = [r for r in false_positives if r["motion_class"] == "airborne"]
    print(f"airborne false positives: {len(airborne_fps)}")
    if airborne_fps:
        print("Rule is NOT gate-ready — airborne good strips trip displacement.")
        for row in airborne_fps:
            print(f"  {row['id']}: {row['flags']}")
    else:
        print("Airborne good strips clean — 0 FP bar met (grounded classes excluded).")

    _print_coverage_grids()

    print("\n--- adversarial spot-check (04-bat-flap mutations) ---")
    base = adversarial.real_frames("airborne")
    q, anchor = S.quantize_motion_frames(base, "airborne")
    cases = [
        ("clean", q),
        ("hop f2", S.quantize_motion_frames(adversarial.hop(base), "airborne")[0]),
        ("slide f2", S.quantize_motion_frames(adversarial.slide(base), "airborne")[0]),
        (
            "mirror f2",
            S.quantize_motion_frames(adversarial.wrong_pose(base), "airborne")[0],
        ),
    ]
    for name, frames in cases:
        trans = S.adjacent_transition_shifts(frames, anchor=anchor)
        flags = _displacement_flags(frames, "airborne", anchor)
        trans_txt = " ".join(_fmt_shift(t["dx"], t["dy"]) for t in trans)
        detect = "DETECT" if flags else "—"
        print(f"  airborne {name:<8} {trans_txt}  {detect} {flags or ''}")

    return 1 if airborne_fps else 0


if __name__ == "__main__":
    raise SystemExit(main())
