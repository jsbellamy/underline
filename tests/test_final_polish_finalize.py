"""Behavioral proof for pipeline.final_polish finalization (issues #95 and #101).

`finalize_bundle`: the immutable final report, Release Frame production, the
fail path that writes a report without a release, and the fail-closed rules that
block a release. Identity Lock's own release block lives in
tests/test_final_polish_identity.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.final_polish import (
    InvalidBundleError,
    REPORT_SCHEMA,
)
from pipeline.gate_evidence import sha256_file
from pipeline.strip import (
    IngestResult,
    ingest_strip_provider,
)
from tests.support import polish_bundle as pb

from tests.support.final_polish_fixtures import (
    FRAME_COUNT,
    LANTERN_STRIP,
    PASS_STRIP,
    _check_bundle,
    _corpus_layout,
    _finalize_bundle,
    _set_opaque_rgb,
)


def _init_bundle_polish(
    strip: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    """Idle/emissive/lantern bundle construction via the polish_bundle seam (issue #249).

    This module has no walk or swing call sites, so it no longer needs the
    interim `tests.support.final_polish_fixtures._init_bundle` at all.
    """
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=polish_profile)
    pb.init_bundle(attempt, bundle)


def _init_passing_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)
    return bundle


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class"),
    [
        ("dwarf-miner", PASS_STRIP, "idle"),
        ("lantern", LANTERN_STRIP, "emissive"),
    ],
)
def test_production_check_and_final_report_bind_embedded_profile(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    result = _check_bundle(bundle)
    profile_hash = sha256_file(bundle / "profile.json")
    assert result.profile_id == profile_id
    assert result.profile_sha256 == profile_hash

    report = json.loads(_finalize_bundle(bundle).read_text())
    assert report["polish_profile"] == {
        "id": profile_id,
        "sha256": profile_hash,
    }


def test_check_and_final_report_bind_embedded_profile(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    result = _check_bundle(bundle)
    profile_hash = sha256_file(bundle / "profile.json")
    assert result.profile_id == "miner"
    assert result.profile_sha256 == profile_hash

    report = json.loads(_finalize_bundle(bundle).read_text())
    assert report["polish_profile"] == {
        "id": "miner",
        "sha256": profile_hash,
    }


def test_provider_currently_review_is_reportable_without_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with patch("pipeline.final_polish.ingest_strip_provider", return_value=review):
        result = _check_bundle(bundle)
        assert result.provider_outcome == "REVIEW"
        assert result.outcome == "REVIEW"

        _finalize_bundle(bundle)
    assert not (bundle / "release").exists()
    assert len(list((bundle / "reports").glob("*.json"))) == 1


def test_finalize_records_immutable_report_and_pass_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    report_path = _finalize_bundle(bundle)

    assert report_path.is_file()
    report = json.loads(report_path.read_text())
    assert report["schema"] == REPORT_SCHEMA
    assert report["outcome"] == "PASS"
    assert report["fingerprint"] == result.fingerprint
    assert len(report["release_frames"]) == FRAME_COUNT

    for index in range(FRAME_COUNT):
        release = bundle / "release" / f"frame-{index}.png"
        polished = bundle / "polished" / f"frame-{index}.png"
        assert release.is_file()
        assert sha256_file(release) == sha256_file(polished)


def test_finalize_fail_outcome_writes_report_without_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    _set_opaque_rgb(polished, 3, 5, (250, 1, 2))
    result = _check_bundle(bundle)
    report_path = _finalize_bundle(bundle)

    report = json.loads(report_path.read_text())
    assert report["outcome"] == "FAIL"
    assert not (bundle / "release").exists()


def test_repeat_finalize_is_idempotent(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    first = _finalize_bundle(bundle)
    second = _finalize_bundle(bundle)
    assert first == second
    assert json.loads(first.read_text()) == json.loads(second.read_text())


def test_conflicting_report_fails_closed(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    report_path = _finalize_bundle(bundle)
    tampered = json.loads(report_path.read_text())
    tampered["outcome"] = "FAIL"
    report_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(InvalidBundleError) as exc:
        _finalize_bundle(bundle)
    assert exc.value.reason_code == "report_conflict"


def test_conflicting_release_fails_closed(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    _finalize_bundle(bundle)
    release = bundle / "release" / "frame-0.png"
    release.write_bytes(release.read_bytes() + b"x")

    with pytest.raises(InvalidBundleError) as exc:
        _finalize_bundle(bundle)
    assert exc.value.reason_code == "release_conflict"


def test_tampered_v2_provenance_blocks_check_and_finalize(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = bundle / "provider" / "source.source.json"
    record = json.loads(provenance.read_text())
    record["attempt_id"] = "tampered"
    provenance.write_text(json.dumps(record) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "provenance_hash_mismatch"

    with pytest.raises(InvalidBundleError):
        _finalize_bundle(bundle)
