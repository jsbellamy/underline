"""Characterization tests pinning current strip gate output.

These are characterization tests, not specifications. Later wave slices are
expected to change these numbers; any diff here must be explained in the
changing slice's PR body rather than silently re-baselined.
"""

from __future__ import annotations

import pathlib

import pytest
import strip as S

INBOX = pathlib.Path(__file__).resolve().parents[1] / "prototype" / "strip-coherence" / "inbox"
TOLERANCE = 0.002

CORPUS_LAYOUT = S.StripLayout(
    frame_w=S.DEFAULT_LAYOUT.frame_w,
    frame_h=S.DEFAULT_LAYOUT.frame_h,
    frame_count=S.DEFAULT_LAYOUT.frame_count,
    gutter=S.DEFAULT_LAYOUT.gutter,
    pitch_px=24,
    margin_cells=0,
)

PINNED = {
    "01-miner-idle": {"pass": True, "worst_sil": 0.095, "loop": 0.151, "drift": 0.073},
    "02-slime-idle": {"pass": False, "worst_sil": 0.300, "loop": 0.300, "drift": 0.146},
    "03-torch-flicker": {"pass": True, "worst_sil": 0.160, "loop": 0.130, "drift": 0.145},
    "04-bat-flap": {"pass": False, "worst_sil": 0.651, "loop": 0.603, "drift": 0.151},
    "05-miner-walk": {"pass": False, "worst_sil": 0.391, "loop": 0.132, "drift": 0.114},
    "06-miner-swing": {"pass": False, "worst_sil": 0.382, "loop": 0.515, "drift": 0.188},
    "07-NEG-palette-drift": {"pass": False, "worst_sil": 0.133, "loop": 0.142, "drift": 0.290},
    "08-NEG-identity-drift": {"pass": False, "worst_sil": 0.571, "loop": 0.503, "drift": 0.228},
}


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

    result = S.ingest_strip_provider(path, CORPUS_LAYOUT)
    want = PINNED[sample_id]
    got_pass, got_sil, got_loop, got_drift = _metrics(result)

    assert got_pass == want["pass"], sample_id
    assert _close(got_sil, want["worst_sil"]), f"{sample_id} sil {got_sil} != {want['worst_sil']}"
    assert _close(got_loop, want["loop"]), f"{sample_id} loop {got_loop} != {want['loop']}"
    assert _close(got_drift, want["drift"]), f"{sample_id} drift {got_drift} != {want['drift']}"


def test_no_gutter_raises_on_recover() -> None:
    path = INBOX / "09-NEG-no-gutter.png"
    assert path.exists(), f"missing inbox fixture: {path}"

    with pytest.raises(ValueError, match="clipped"):
        S.recover_strip_cells(path, CORPUS_LAYOUT)
