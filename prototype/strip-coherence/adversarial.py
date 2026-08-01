#!/usr/bin/env python3
"""PROTOTYPE — does the split gate still REJECT? Mutate each class's good strip.

Each motion class runs the same mutation battery against its own corpus baseline.
MUST_FAIL lists mutations the current contract rejects. STRIP_GAPS / KNOWN_GAPS list
mutations that pass but are not gated — they print as GAP, never as ok.
"""

from __future__ import annotations

import pathlib

from pipeline import strip as S

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"

CLASS_BASELINES: dict[str, str] = {
    "idle": "01-miner-idle.png",
    "blob_idle": "02-slime-idle.png",
    "emissive": "03-torch-flicker.png",
    "airborne": "04-bat-flap.png",
    "walk": "05-miner-walk.png",
    "swing": "06-miner-swing.png",
}

GATES = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "min_pair_cohort_pass",
    "loop_closure_pass",
    "displacement_pass",
    "palette_drift_pass",
    "static_silhouette_pass",
)

MUTATIONS = (
    ("recolour frame 2", "recolour"),
    ("hop frame 2 (+3 rows)", "hop"),
    ("mirror frame 2", "wrong_pose"),
    ("slide frame 2 (+3 cols)", "slide"),
    ("hold frame 2 pose", "hold_pose"),
)

# Corpus baselines may differ from production reference bundles. Swing inbox strips
# exceed the static_silhouette_pass budget tuned on dwarf/swing/polished (issue #173).
BASELINE_OUTCOME: dict[str, str] = {
    "swing": "REVIEW",
}

MUST_FAIL: dict[str, set[str]] = {
    "idle": {"recolour", "hop", "wrong_pose", "slide"},
    "blob_idle": {"recolour", "hop", "slide"},
    "emissive": {"recolour", "hop", "slide", "wrong_pose"},
    "walk": {"recolour", "hop", "wrong_pose", "slide"},
    "swing": {"recolour", "hop", "wrong_pose", "slide", "hold_pose"},
    "airborne": {"recolour"},
}

# Class-specific mutation strength — deterministic, named in adversarial output.
CLASS_MUTATION_OVERRIDES: dict[str, dict[str, dict[str, object]]] = {
    "blob_idle": {
        "slide": {"dx": 4, "label": "slide frame 2 (+4 cols)"},
    },
    "emissive": {
        "wrong_pose": {"indices": (0, 2), "label": "mirror frames 0,2"},
    },
}

# Per-strip holes — displacement undecidable or otherwise ungated on this PNG.
STRIP_GAPS: dict[str, dict[str, str]] = {
    "04-bat-flap": {
        "hop": (
            "degenerate alignment minimum (margin 0.0000 at 3→0); "
            "displacement undecidable"
        ),
        "slide": (
            "degenerate alignment minimum (margin 0.0000 at 3→0); "
            "displacement undecidable"
        ),
    },
}

KNOWN_GAPS: dict[str, dict[str, str]] = {}


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


def _baseline_strip_id(motion_class: str) -> str:
    return CLASS_BASELINES[motion_class].removesuffix(".png")


def _gap_reason(motion_class: str, mutation_key: str | None) -> str | None:
    if mutation_key is None:
        return None
    strip_id = _baseline_strip_id(motion_class)
    if mutation_key in STRIP_GAPS.get(strip_id, {}):
        return STRIP_GAPS[strip_id][mutation_key]
    if mutation_key in KNOWN_GAPS.get(motion_class, {}):
        return KNOWN_GAPS[motion_class][mutation_key]
    return None


def _resolve_baseline(motion_class: str) -> pathlib.Path:
    name = CLASS_BASELINES[motion_class]
    path = INBOX / name
    if path.exists():
        return path
    if motion_class == "idle":
        legacy = INBOX / "miner-idle-strip.png"
        if legacy.exists():
            return legacy
    raise FileNotFoundError(f"missing baseline for {motion_class}: {path}")


def motion_class_for_strip(strip_id: str) -> str:
    """Resolve motion class for a corpus strip id (e.g. 04-bat-flap)."""
    for motion_class, filename in CLASS_BASELINES.items():
        if filename == f"{strip_id}.png":
            return motion_class
    raise KeyError(f"no class baseline for strip {strip_id!r}")


def frames_for_strip(strip_id: str):
    """Recover frames for a corpus strip by id."""
    path = INBOX / f"{strip_id}.png"
    if not path.exists():
        raise FileNotFoundError(f"missing strip: {path}")
    cells, _ = S.recover_strip_cells(path, _corpus_layout())
    frames, _ = S.slice_frames_pitch(cells, frame_count=S.DEFAULT_LAYOUT.frame_count)
    return frames


def real_frames(motion_class: str = "idle"):
    """Recover frames for a motion class's corpus baseline strip."""
    path = _resolve_baseline(motion_class)
    cells, _ = S.recover_strip_cells(path, _corpus_layout())
    frames, _ = S.slice_frames_pitch(cells, frame_count=S.DEFAULT_LAYOUT.frame_count)
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


def wrong_pose(frames, idx=2, *, indices: tuple[int, ...] | None = None):
    """Mirror frame idx — same palette, same baseline, totally different silhouette."""
    out = [[row[:] for row in f] for f in frames]
    mirror_indices = indices if indices is not None else (idx,)
    for mirror_idx in mirror_indices:
        out[mirror_idx] = [list(reversed(row)) for row in out[mirror_idx]]
    return out


def slide(frames, idx=2, dx=3):
    """Translate frame idx sideways — character drifts across the strip."""
    out = [[row[:] for row in f] for f in frames]
    out[idx] = [[None] * dx + row[:-dx] for row in out[idx]]
    return out


def hold_pose(frames, idx=2):
    """Duplicate frame idx-1 onto frame idx — adjacent alpha unchanged."""
    out = [[row[:] for row in f] for f in frames]
    out[idx] = [[cell for cell in row] for row in out[idx - 1]]
    return out


_MUTATORS = {
    "recolour": recolour,
    "hop": hop,
    "wrong_pose": wrong_pose,
    "slide": slide,
    "hold_pose": hold_pose,
}


def mutation_label(motion_class: str, mutation_key: str, default_label: str) -> str:
    override = CLASS_MUTATION_OVERRIDES.get(motion_class, {}).get(mutation_key, {})
    return str(override.get("label", default_label))


def mutate(motion_class: str, mutation_key: str, frames):
    """Apply a class-aware mutation with deterministic per-class strength."""
    override = CLASS_MUTATION_OVERRIDES.get(motion_class, {}).get(mutation_key)
    if override is None:
        return _MUTATORS[mutation_key](frames)
    if mutation_key == "slide":
        return slide(frames, dx=int(override["dx"]))
    if mutation_key == "wrong_pose":
        indices = override["indices"]
        assert isinstance(indices, tuple)
        return wrong_pose(frames, indices=indices)
    return _MUTATORS[mutation_key](frames)


def _tripped(result: dict) -> list[str]:
    gate_outcomes = result.get("gate_outcomes") or {}
    return [gate for gate, row in gate_outcomes.items() if row.get("outcome") == "FAIL"]


def _review_gates(result: dict) -> list[str]:
    gate_outcomes = result.get("gate_outcomes") or {}
    return [gate for gate, row in gate_outcomes.items() if row.get("outcome") == "REVIEW"]


def _outcome(result: dict) -> str:
    return result.get("outcome", "PASS" if result.get("pass") else "FAIL")


def report(
    motion_class: str,
    name: str,
    frames,
    *,
    mutation_key: str | None = None,
    verbose: bool = True,
) -> str:
    """Return 'ok', 'MISMATCH', or 'GAP'."""
    result = S.coherence_split(frames, motion_class=motion_class)
    sil = max((row["frac"] for row in result["silhouette_adjacent"]), default=0.0)
    pairwise = result.get("silhouette_pairwise") or {}
    tripped = _tripped(result)
    review_gates = _review_gates(result)
    outcome = _outcome(result)
    if mutation_key is None:
        mutation_key = next((k for label, k in MUTATIONS if label == name), None)
    gap_reason = _gap_reason(motion_class, mutation_key)

    if name == "baseline (untouched)":
        want = BASELINE_OUTCOME.get(motion_class, "PASS")
        status = "ok" if outcome == want else "MISMATCH"
    elif mutation_key in MUST_FAIL.get(motion_class, set()):
        status = "ok" if outcome != "PASS" else "MISMATCH"
        want = "not PASS"
    elif gap_reason:
        status = "GAP"
        want = "not PASS (ungated)"
    elif (
        mutation_key in ("hop", "slide")
        and motion_class == "airborne"
        and result.get("displacement_pass") is False
    ):
        status = "ok" if outcome != "PASS" else "MISMATCH"
        want = "not PASS"
    elif (
        mutation_key in ("hop", "slide")
        and motion_class == "airborne"
        and result.get("displacement_pass") is None
    ):
        status = "GAP"
        want = "not PASS (inapplicable)"
    else:
        status = "ok" if outcome == "PASS" else "MISMATCH"
        want = "PASS"

    if verbose:
        disp = result.get("displacement_pass")
        disp_note = ""
        if result.get("displacement_inapplicable"):
            disp_note = "  disp=—"
        elif disp is not None:
            disp_note = f"  disp={'pass' if disp else 'FAIL'}"
        review_note = f"  review={review_gates}" if review_gates else ""
        print(
            f"{status:<8}  {motion_class:<10} {name:<22} "
            f"{outcome} (want {want})  "
            f"sil_max={sil:.3f} min_pair={pairwise.get('min_pair', 0):.3f} "
            f"drift_max={result['worst_palette_drift']:.3f}{disp_note}{review_note}"
            + (f"  failed={tripped}" if tripped else "")
        )
        if status == "GAP" and gap_reason:
            print(f"          {gap_reason}")
        elif status == "GAP" and result.get("displacement_reason"):
            print(f"          {result['displacement_reason']}")
    return status


def run_class(motion_class: str, *, verbose: bool = True) -> tuple[bool, int, int]:
    frames = real_frames(motion_class)
    gaps = 0
    inapplicable = 0
    baseline_coh = S.coherence_split(frames, motion_class=motion_class)
    if baseline_coh.get("displacement_inapplicable") and verbose:
        print(
            f"N/A       {motion_class:<10} displacement inapplicable — "
            f"{baseline_coh['displacement_reason']}"
        )
        inapplicable = 1
    ok = report(motion_class, "baseline (untouched)", frames, verbose=verbose) == "ok"
    for label, key in MUTATIONS:
        display_label = mutation_label(motion_class, key, label)
        status = report(
            motion_class,
            display_label,
            mutate(motion_class, key, frames),
            mutation_key=key,
            verbose=verbose,
        )
        if status == "MISMATCH":
            ok = False
        elif status == "GAP":
            gaps += 1
    return ok, gaps, inapplicable


def main() -> int:
    ok = True
    total_gaps = 0
    total_inapplicable = 0
    for motion_class in CLASS_BASELINES:
        print(f"\n=== {motion_class} ({CLASS_BASELINES[motion_class]}) ===")
        class_ok, gaps, inapplicable = run_class(motion_class)
        ok = class_ok and ok
        total_gaps += gaps
        total_inapplicable += inapplicable
    if total_gaps:
        print(f"\n{total_gaps} GAPS (documented, not green)")
    if total_inapplicable:
        print(
            f"{total_inapplicable} class baseline(s) displacement inapplicable "
            f"(adversarial scope — one mutation baseline per class, not full corpus)"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
