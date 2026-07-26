#!/usr/bin/env python3
"""PROTOTYPE — falsify the antisymmetric displacement tamper rule on good strips.

Pre-registered rule (see docs/strip-acquisition-contract.md):
  An interior frame is tampered when its in-shift and out-shift are equal and
  opposite with Chebyshev magnitude >= DISPLACEMENT_MIN_MAGNITUDE (default 2).

Shifts come from best_alignment_shift at DISPLACEMENT_PROBE_SPAN (±4) — a wide
evidence scan. REGISTRATION_SPAN (±1) is only for silhouette jitter absorption;
do not conflate the two.

Run over every manifest-good strip before promoting this to a gate.
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

EXTRA_GOOD = ("miner-idle-strip",)


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


def probe_sample(sample_id: str, motion_class: str, path: pathlib.Path) -> dict:
    q, anchor = _load_quantized(path, motion_class)
    transitions = S.adjacent_transition_shifts(q, anchor=anchor)
    flags = S.antisymmetric_displacement_flags(q, anchor=anchor)
    return {
        "id": sample_id,
        "motion_class": motion_class,
        "transitions": transitions,
        "flags": flags,
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    good = [
        s
        for s in manifest["samples"]
        if s.get("contract_expect") == "PASS"
    ]
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
        f"(span=±{S.DISPLACEMENT_PROBE_SPAN}, min_mag≥{S.DISPLACEMENT_MIN_MAGNITUDE})"
    )
    print("-" * 72)
    for row in rows:
        trans = " ".join(
            _fmt_shift(t["dx"], t["dy"]) for t in row["transitions"]
        )
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
    print(f"good strips scored: {len(rows)}")
    print(f"false positives: {len(false_positives)}")
    if false_positives:
        print("Rule is NOT gate-ready — good strips trip antisymmetric displacement.")
        for row in false_positives:
            print(f"  {row['id']}: {row['flags']}")
    else:
        print("No good strip tripped — rule survives falsification on this corpus.")

    print("\n--- adversarial spot-check (airborne baseline mutations) ---")
    import adversarial  # noqa: E402

    base = adversarial.real_frames("airborne")
    q, anchor = S.quantize_motion_frames(base, "airborne")
    cases = [
        ("clean", q),
        ("hop", S.quantize_motion_frames(adversarial.hop(base), "airborne")[0]),
        ("slide", S.quantize_motion_frames(adversarial.slide(base), "airborne")[0]),
        (
            "mirror",
            S.quantize_motion_frames(adversarial.wrong_pose(base), "airborne")[0],
        ),
    ]
    for name, frames in cases:
        trans = S.adjacent_transition_shifts(frames, anchor=anchor)
        flags = S.antisymmetric_displacement_flags(frames, anchor=anchor)
        trans_txt = " ".join(_fmt_shift(t["dx"], t["dy"]) for t in trans)
        detect = "DETECT" if flags else "—"
        print(f"  airborne {name:<6} {trans_txt}  {detect} {flags or ''}")

    swing_base = adversarial.real_frames("swing")
    sq, s_anchor = S.quantize_motion_frames(swing_base, "swing")
    swing_trans = S.adjacent_transition_shifts(sq, anchor=s_anchor)
    swing_flags = S.antisymmetric_displacement_flags(sq, anchor=s_anchor)
    trans_txt = " ".join(_fmt_shift(t["dx"], t["dy"]) for t in swing_trans)
    print(
        f"  swing  clean   {trans_txt}  "
        f"{'DETECT' if swing_flags else '—'} {swing_flags or ''}"
    )

    return 1 if false_positives else 0


if __name__ == "__main__":
    raise SystemExit(main())
