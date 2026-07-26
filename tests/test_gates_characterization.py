"""Characterization tests pinning current strip gate output.

These are characterization tests, not specifications. Later wave slices are
expected to change these numbers; any diff here must be explained in the
changing slice's PR body rather than silently re-baselined.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import strip as S

INBOX = pathlib.Path(__file__).resolve().parents[1] / "prototype" / "strip-coherence" / "inbox"
MANIFEST = (
    pathlib.Path(__file__).resolve().parents[1]
    / "prototype"
    / "strip-coherence"
    / "prompts"
    / "manifest.json"
)
TOLERANCE = 0.002

MOTION_CLASS = {
    s["id"]: s["motion_class"] for s in json.loads(MANIFEST.read_text())["samples"]
}

PINNED = {
    "01-miner-idle": {"pass": True, "worst_sil": 0.095, "loop": 0.147, "drift": 0.073},
    "02-slime-idle": {"pass": True, "worst_sil": 0.337, "loop": 0.330, "drift": 0.141},
    "03-torch-flicker": {"pass": True, "worst_sil": 0.160, "loop": 0.130, "drift": 0.145},
    "04-bat-flap": {"pass": True, "worst_sil": 0.644, "loop": 0.653, "drift": 0.145},
    "05-miner-walk": {"pass": True, "worst_sil": 0.398, "loop": 0.143, "drift": 0.117},
    "06-miner-swing": {"pass": True, "worst_sil": 0.565, "loop": 0.550, "drift": 0.179},
    "07-NEG-palette-drift": {"pass": False, "worst_sil": 0.057, "loop": 0.043, "drift": 0.279},
    "08-NEG-identity-drift": {"pass": False, "worst_sil": 0.602, "loop": 0.482, "drift": 0.218},
    "10-guard-idle": {"pass": True, "worst_sil": 0.024, "loop": 0.015, "drift": 0.077},
    "11-dwarf-idle": {"pass": True, "worst_sil": 0.108, "loop": 0.000, "drift": 0.115},
    "12-jelly-idle": {"pass": True, "worst_sil": 0.264, "loop": 0.202, "drift": 0.124},
    "14-lantern-flicker": {"pass": True, "worst_sil": 0.115, "loop": 0.099, "drift": 0.073},
    "17-wisp-float": {"pass": True, "worst_sil": 0.402, "loop": 0.461, "drift": 0.068},
    "19-scout-walk": {"pass": True, "worst_sil": 0.099, "loop": 0.084, "drift": 0.033},
    "20-axe-swing": {"pass": True, "worst_sil": 0.492, "loop": 0.522, "drift": 0.174},
    "21-hammer-swing": {"pass": True, "worst_sil": 0.359, "loop": 0.388, "drift": 0.124},
}

DERIVED_BUDGETS = {
    "idle": (0.17, 0.30, 0.14, 0.06),
    "blob_idle": (0.36, 0.36, 0.17, 0.05),
    "emissive": (0.18, 0.16, 0.17, 0.12),
    "walk": (0.42, 0.17, 0.14, 0.17),
    "swing": (0.59, None, 0.20, None),
    "airborne": (None, 0.68, 0.17, 0.29),
}

GATES = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "min_pair_cohort_pass",
    "loop_closure_pass",
    "palette_drift_pass",
)


def _corpus_layout() -> S.StripLayout:
    return S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _metrics(result: S.IngestResult) -> tuple[bool, float, float, float]:
    coh = result.coherence
    worst_sil = max((r["frac"] for r in coh.get("silhouette_adjacent", [])), default=0.0)
    loop = (coh.get("loop_closure") or {}).get("frac", 0.0)
    drift = coh.get("worst_palette_drift", 0.0)
    return result.pass_, worst_sil, loop, drift


def _close(got: float, want: float) -> bool:
    return abs(got - want) <= TOLERANCE


@pytest.mark.parametrize("sample_id", sorted(PINNED))
def test_ingest_strip_provider_characterization(sample_id: str) -> None:
    path = INBOX / f"{sample_id}.png"
    assert path.exists(), f"missing inbox fixture: {path}"

    result = S.ingest_strip_provider(
        path, _corpus_layout(), motion_class=MOTION_CLASS[sample_id]
    )
    want = PINNED[sample_id]
    got_pass, got_sil, got_loop, got_drift = _metrics(result)

    assert got_pass == want["pass"], sample_id
    assert _close(got_sil, want["worst_sil"]), f"{sample_id} sil {got_sil} != {want['worst_sil']}"
    assert _close(got_loop, want["loop"]), f"{sample_id} loop {got_loop} != {want['loop']}"
    assert _close(got_drift, want["drift"]), f"{sample_id} drift {got_drift} != {want['drift']}"


def test_unknown_motion_class_raises() -> None:
    frames = [[[(1, 1, 1)]]]
    with pytest.raises(ValueError, match="unknown motion_class"):
        S.coherence_split(frames, motion_class="not-a-class")


def test_motion_class_budgets_match_contract() -> None:
    for motion_class, (sil, loop, drift, min_pair) in DERIVED_BUDGETS.items():
        budget = S.MOTION_CLASSES[motion_class]
        assert budget.max_silhouette == sil
        assert budget.max_loop == loop
        assert budget.max_drift == drift
        assert budget.max_min_pair == min_pair


def test_none_silhouette_budget_excluded_from_pass() -> None:
    budget = S.MOTION_CLASSES["airborne"]
    assert budget.max_silhouette is None
    assert budget.max_min_pair == 0.29
    path = INBOX / "04-bat-flap.png"
    result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="airborne")
    coh = result.coherence
    assert coh.get("silhouette_budget") is None
    assert coh.get("min_pair_cohort_pass") is True
    assert result.pass_ is True


def test_airborne_identity_drift_fails_min_pair_cohort() -> None:
    path = INBOX / "08-NEG-identity-drift.png"
    result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="airborne")
    coh = result.coherence
    assert coh.get("silhouette_budget") is None
    assert coh.get("min_pair_cohort_pass") is False
    assert result.pass_ is False


def test_swing_excludes_min_pair_cohort_gate() -> None:
    budget = S.MOTION_CLASSES["swing"]
    assert budget.max_min_pair is None
    path = INBOX / "06-miner-swing.png"
    result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="swing")
    assert result.coherence.get("min_pair_cohort_pass") is None


def test_swing_does_not_trip_loop_closure_pass() -> None:
    path = INBOX / "06-miner-swing.png"
    result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="swing")
    coh = result.coherence
    assert coh.get("loop_closure_pass") is None
    assert "loop_closure_pass" not in [g for g in GATES if coh.get(g) is False]


def test_bat_flap_grounded_false_via_class() -> None:
    path = INBOX / "04-bat-flap.png"
    result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="airborne")
    coh = result.coherence
    assert coh.get("grounded") is False
    assert coh.get("baseline_row_stable") is None


def test_manifest_has_no_per_sample_grounded() -> None:
    manifest = json.loads(MANIFEST.read_text())
    for sample in manifest["samples"]:
        assert "grounded" not in sample, sample["id"]


def test_negative_controls_trip_expected_gates() -> None:
    cases = {
        "07-NEG-palette-drift": (["palette_drift_pass"], ["silhouette_budget"]),
        "08-NEG-identity-drift": (["silhouette_budget"], []),
        "09-NEG-no-gutter": (["recover"], GATES),
    }
    for sample_id, (must_trip, must_not_trip) in cases.items():
        path = INBOX / f"{sample_id}.png"
        if sample_id == "09-NEG-no-gutter":
            with pytest.raises(ValueError, match="clipped"):
                S.ingest_strip_provider(path, _corpus_layout(), motion_class="idle")
            continue
        result = S.ingest_strip_provider(path, _corpus_layout(), motion_class="idle")
        tripped = [g for g in GATES if result.coherence.get(g) is False]
        for gate in must_trip:
            assert gate in tripped, f"{sample_id} missing {gate}"
        for gate in must_not_trip:
            assert gate not in tripped, f"{sample_id} wrongly tripped {gate}"


def test_no_gutter_raises_on_recover() -> None:
    path = INBOX / "09-NEG-no-gutter.png"
    assert path.exists(), f"missing inbox fixture: {path}"

    with pytest.raises(ValueError, match="clipped"):
        S.recover_strip_cells(path, _corpus_layout())
