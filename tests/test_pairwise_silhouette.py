"""Pairwise silhouette diagnostics — cohort signal beside adjacent max-pair."""

from __future__ import annotations

import pathlib

import strip as S

INBOX = pathlib.Path(__file__).resolve().parents[1] / "prototype" / "strip-coherence" / "inbox"


def _corpus_layout() -> S.StripLayout:
    return S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def test_min_pair_separates_airborne_cohort_from_identity_drift() -> None:
    layout = _corpus_layout()
    bat = S.ingest_strip_provider(INBOX / "04-bat-flap.png", layout, motion_class="airborne")
    wisp = S.ingest_strip_provider(INBOX / "17-wisp-float.png", layout, motion_class="airborne")
    drift = S.ingest_strip_provider(
        INBOX / "08-NEG-identity-drift.png", layout, motion_class="airborne"
    )
    assert bat.coherence["min_pair_cohort_pass"] is True
    assert wisp.coherence["min_pair_cohort_pass"] is True
    assert drift.coherence["min_pair_cohort_pass"] is False


def test_max_pair_degenerates_on_bat_vs_identity_drift_under_airborne() -> None:
    layout = _corpus_layout()
    bat = S.ingest_strip_provider(
        INBOX / "04-bat-flap.png", layout, motion_class="airborne"
    )
    drift = S.ingest_strip_provider(
        INBOX / "08-NEG-identity-drift.png", layout, motion_class="airborne"
    )
    bat_max = bat.coherence["silhouette_pairwise"]["max_pair"]
    drift_max = drift.coherence["silhouette_pairwise"]["max_pair"]

    assert abs(bat_max - drift_max) < 0.05


def test_min_pair_blind_to_single_frame_tamper() -> None:
    frames = [
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
        [[(9, 9, 9), (9, 9, 9)], [(9, 9, 9), (9, 9, 9)]],
        [[(1, 1, 1), None], [None, (2, 2, 2)]],
    ]
    clean = S.coherence_split(frames, motion_class="idle")
    tampered = [frames[0], frames[1], adversarial_mirror(frames[2]), frames[3]]
    dirty = S.coherence_split(tampered, motion_class="idle")

    assert clean["silhouette_pairwise"]["min_pair"] == dirty["silhouette_pairwise"]["min_pair"]
    assert clean["min_pair_cohort_pass"] == dirty["min_pair_cohort_pass"]
    assert dirty["silhouette_budget"] is False


def adversarial_mirror(frame):
    return [list(reversed(row)) for row in frame]
