"""Fail-closed Gate-evidence loaders (issue #49 C1, C7)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from pipeline import gate_evidence as ge

ROOT = Path(__file__).resolve().parents[1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _png_bytes(tag: bytes = b"raw") -> bytes:
    # Minimal deterministic PNG-like blob (hash-bound; not decoded as image).
    return b"\x89PNG\r\n\x1a\n" + tag + b"\x00" * 32


def _fixture(tmp_path: Path) -> dict[str, object]:
    """Minimal valid evidence graph under tmp_path/gate-controls."""
    gc = tmp_path / "gate-controls"
    raw = _png_bytes(b"candidate")
    raw_sha = _sha(raw)
    attempt_id = "idle--silhouette_budget--001"
    spec_id = "idle/silhouette_budget"
    promo_id = "promo--idle--silhouette_budget"
    measurement_rel = f"gate-controls/reports/{attempt_id}/m1.json"
    provenance_rel = f"gate-controls/provenance/{attempt_id}.json"
    raw_rel = f"gate-controls/raw/{attempt_id}.png"

    measurement = {
        "schema": "gate-control-measurement/0",
        "raw": str(tmp_path / raw_rel),
        "raw_sha256": raw_sha,
        "scorer_gate_config_sha256": "abc",
        "motion_class": "idle",
        "target_gate": "silhouette_budget",
        "applicable_gates": ["silhouette_budget", "palette_drift_pass"],
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "fail",
                "metric": 0.3,
                "budget": 0.17,
                "reason": None,
            },
            "palette_drift_pass": {
                "outcome": "pass",
                "metric": 0.05,
                "budget": 0.14,
                "reason": None,
            },
        },
        "isolation": "ISOLATED",
        "blockers": [],
        "caveats": [],
        "primary_failure": None,
    }
    provenance = {
        "schema": "gate-control-provenance/0",
        "specification_id": spec_id,
        "attempt_id": attempt_id,
        "generator": "cursor-image-gen",
        "prompt_text": "prompt",
        "prompt_sha256": _sha(b"prompt"),
        "reference_image_sha256": [],
        "generated_at": "2026-07-26T16:00:00+00:00",
        "acquiring_agent": "test",
        "repository_commit": "deadbeef",
        "raw_path": raw_rel,
        "raw_sha256": raw_sha,
        "media_type": "image/png",
        "dimensions": [16, 24],
    }
    attempt = {
        "schema": "gate-control-acquisition/0",
        "attempt_id": attempt_id,
        "specification_id": spec_id,
        "ordinal": 1,
        "predecessor_attempt_id": None,
        "recorded_at": "2026-07-26T16:00:00+00:00",
        "prompt_path": None,
        "prompt_sha256": provenance["prompt_sha256"],
        "prompt_delta": None,
        "acquiring_agent": "test",
        "artifact_state": "retained",
        "isolation": "ISOLATED",
        "primary_failure": None,
        "promotion_blockers": [],
        "measurement_path": measurement_rel,
        "provenance_path": provenance_rel,
        "composite_path": None,
        "raw_sha256": raw_sha,
    }
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [
            {
                "id": spec_id,
                "motion_class": "idle",
                "target_gate": "silhouette_budget",
                "active_promotion": promo_id,
            }
        ],
        "promotions": [
            {
                "id": promo_id,
                "specification_id": spec_id,
                "attempt_id": attempt_id,
                "measurement_path": measurement_rel,
                "status": "PENDING_VERIFICATION",
                "recorded_at": "2026-07-26T16:00:00+00:00",
                "note": "fixture",
            }
        ],
    }
    profiles = {
        "schema": "acceptance-profile-index/0",
        "profiles": {
            "idle": {
                "motion_class": "idle",
                "gates": {
                    "silhouette_budget": {
                        "status": "SEPARATED",
                        "budget": 0.2239,
                        "hard_fail": 0.3,
                        "active_promotion": promo_id,
                        "control_attempt": attempt_id,
                    }
                },
            }
        },
    }
    review = {
        "schema": "gate-review-audit/0",
        "review_id": "review--01",
        "attempt_id": attempt_id,
        "gate": "silhouette_budget",
        "verdict": "APPROVE",
        "packet_sha256": "0" * 64,
    }
    verification = {
        "schema": "gate-control-verification/0",
        "promotion_id": promo_id,
        "attempt_id": attempt_id,
        "status": "PENDING_VERIFICATION",
        "manifest_sha256": "1" * 64,
    }

    _write(tmp_path / raw_rel, raw)
    _write(tmp_path / measurement_rel, measurement)
    _write(tmp_path / provenance_rel, provenance)
    _write(gc / "manifest.json", manifest)
    _write(gc / "attempts.jsonl", "")
    (gc / "attempts.jsonl").write_text(json.dumps(attempt, sort_keys=True) + "\n")
    _write(gc / "acceptance-profiles.json", profiles)
    _write(gc / "reviews" / attempt_id / "review--01.json", review)
    _write(gc / "verification" / f"{promo_id}.json", verification)
    return {
        "root": tmp_path,
        "gc": gc,
        "attempt_id": attempt_id,
        "promo_id": promo_id,
        "spec_id": spec_id,
        "raw_sha": raw_sha,
        "measurement_rel": measurement_rel,
        "provenance_rel": provenance_rel,
        "raw_rel": raw_rel,
        "attempt": attempt,
        "manifest": manifest,
        "measurement": measurement,
        "provenance": provenance,
        "profiles": profiles,
        "review": review,
        "verification": verification,
    }


def test_valid_fixture_loads_fail_closed_graph(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    graph = ge.validate_evidence_graph(fx["root"])
    assert graph.manifest.schema == "gate-control-manifest/0"
    assert fx["promo_id"] in graph.promotions
    assert fx["attempt_id"] in graph.attempts
    assert graph.attempts[fx["attempt_id"]].artifact_state == "retained"


def test_unknown_manifest_schema_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "manifest.json"
    doc = json.loads(path.read_text())
    doc["schema"] = "gate-control-manifest/99"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="unknown schema"):
        ge.validate_evidence_graph(fx["root"])


def test_unknown_measurement_schema_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["root"] / fx["measurement_rel"]
    doc = json.loads(path.read_text())
    doc["schema"] = "gate-control-measurement/99"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="unknown schema"):
        ge.validate_evidence_graph(fx["root"])


def test_duplicate_attempt_id_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "attempts.jsonl"
    line = path.read_text().strip()
    path.write_text(line + "\n" + line + "\n")
    with pytest.raises(ge.EvidenceError, match="duplicate attempt_id"):
        ge.validate_evidence_graph(fx["root"])


def test_duplicate_promotion_id_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "manifest.json"
    doc = json.loads(path.read_text())
    doc["promotions"].append(dict(doc["promotions"][0]))
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="duplicate promotion id"):
        ge.validate_evidence_graph(fx["root"])


def test_broken_measurement_reference_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    (fx["root"] / fx["measurement_rel"]).unlink()
    with pytest.raises(ge.EvidenceError, match="missing required file"):
        ge.validate_evidence_graph(fx["root"])


def test_promotion_attempt_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "manifest.json"
    doc = json.loads(path.read_text())
    doc["promotions"][0]["attempt_id"] = "idle--silhouette_budget--999"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="identity"):
        ge.validate_evidence_graph(fx["root"])


def test_promotion_specification_mismatch_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "manifest.json"
    doc = json.loads(path.read_text())
    doc["promotions"][0]["specification_id"] = "idle/palette_drift_pass"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="identity"):
        ge.validate_evidence_graph(fx["root"])


def test_measurement_target_gate_mismatch_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["root"] / fx["measurement_rel"]
    doc = json.loads(path.read_text())
    doc["target_gate"] = "palette_drift_pass"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="identity"):
        ge.validate_evidence_graph(fx["root"])


def test_raw_sha_mismatch_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["root"] / fx["raw_rel"]
    path.write_bytes(_png_bytes(b"tampered"))
    with pytest.raises(ge.EvidenceError, match="SHA-256 mismatch"):
        ge.validate_evidence_graph(fx["root"])


def test_provenance_raw_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["root"] / fx["provenance_rel"]
    doc = json.loads(path.read_text())
    doc["raw_sha256"] = "f" * 64
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="SHA-256 mismatch"):
        ge.validate_evidence_graph(fx["root"])


def test_discarded_promotion_candidate_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "attempts.jsonl"
    attempt = json.loads(path.read_text())
    attempt["artifact_state"] = "discarded"
    path.write_text(json.dumps(attempt, sort_keys=True) + "\n")
    with pytest.raises(ge.EvidenceError, match="discarded"):
        ge.validate_evidence_graph(fx["root"])


def test_missing_raw_for_retained_attempt_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    (fx["root"] / fx["raw_rel"]).unlink()
    with pytest.raises(ge.EvidenceError, match="missing required file"):
        ge.validate_evidence_graph(fx["root"])


def test_unknown_review_schema_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "reviews" / fx["attempt_id"] / "review--01.json"
    doc = json.loads(path.read_text())
    doc["schema"] = "gate-review-audit/99"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="unknown schema"):
        ge.validate_evidence_graph(fx["root"])


def test_unknown_verification_schema_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "verification" / f"{fx['promo_id']}.json"
    doc = json.loads(path.read_text())
    doc["schema"] = "gate-control-verification/99"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="unknown schema"):
        ge.validate_evidence_graph(fx["root"])


def test_unknown_acceptance_profile_schema_is_rejected(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["gc"] / "acceptance-profiles.json"
    doc = json.loads(path.read_text())
    doc["schema"] = "acceptance-profile-index/99"
    _write(path, doc)
    with pytest.raises(ge.EvidenceError, match="unknown schema"):
        ge.validate_evidence_graph(fx["root"])


def test_loaders_do_not_mutate_repository_evidence(tmp_path: Path) -> None:
    """C7: temporary-root work leaves the checked-in gate-controls tree unchanged."""
    repo_gc = ROOT / "gate-controls"
    before = ge.fingerprint_tree(repo_gc)
    fx = _fixture(tmp_path)
    ge.validate_evidence_graph(fx["root"])
    after = ge.fingerprint_tree(repo_gc)
    assert before == after


def test_measurement_v1_schema_is_accepted(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    path = fx["root"] / fx["measurement_rel"]
    doc = json.loads(path.read_text())
    doc["schema"] = "gate-control-measurement/1"
    doc["numeric_policy"] = {"schema": "gate-numeric-policy/0"}
    _write(path, doc)
    graph = ge.validate_evidence_graph(fx["root"])
    assert graph.measurements[fx["attempt_id"]].schema == "gate-control-measurement/1"
