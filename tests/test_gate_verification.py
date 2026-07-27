"""Promotion verification records for Wave A activation (issues #59–#61)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import gate_evidence as ge
from pipeline import gate_review as gr
from pipeline import gate_verification as gv

ROOT = Path(__file__).resolve().parents[1]


def _issue_59_records_present() -> bool:
    verification_root = ROOT / "gate-controls" / "verification"
    return any(
        (verification_root / f"{promotion_id}.json").is_file()
        for promotion_id in gv.ISSUE_59_PROMOTION_IDS
    )


def _issue_60_records_present() -> bool:
    verification_root = ROOT / "gate-controls" / "verification"
    return any(
        (verification_root / f"{promotion_id}.json").is_file()
        for promotion_id in gv.ISSUE_60_PROMOTION_IDS
    )


def _issue_61_records_present() -> bool:
    verification_root = ROOT / "gate-controls" / "verification"
    return any(
        (verification_root / f"{promotion_id}.json").is_file()
        for promotion_id in gv.ISSUE_61_PROMOTION_IDS
    )


def test_pre_transition_manifest_hash_resets_named_promotion_status(tmp_path: Path) -> None:
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [],
        "promotions": [
            {"id": "promo--idle--palette_drift_pass", "status": "ACTIVE"},
            {"id": "promo--idle--silhouette_budget", "status": "ACTIVE"},
            {"id": "promo--walk--loop_closure_pass", "status": "PENDING_VERIFICATION"},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    digest = gv.manifest_sha256_at_binding(
        path,
        promotion_ids=frozenset(
            {
                "promo--idle--palette_drift_pass",
                "promo--idle--silhouette_budget",
            }
        ),
    )
    expected_doc = dict(manifest)
    for promo in expected_doc["promotions"]:
        if promo["id"] in {
            "promo--idle--palette_drift_pass",
            "promo--idle--silhouette_budget",
        }:
            promo["status"] = "PENDING_VERIFICATION"
    expected = ge.sha256_bytes(
        (json.dumps(expected_doc, indent=2) + "\n").encode()
    )
    assert digest == expected


def test_validate_verification_record_rejects_active_without_manifest_match(
    tmp_path: Path,
) -> None:
    gc = tmp_path / "gate-controls"
    gc.mkdir()
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [
            {
                "id": "idle/palette_drift_pass",
                "motion_class": "idle",
                "target_gate": "palette_drift_pass",
                "active_promotion": "promo--idle--palette_drift_pass",
            }
        ],
        "promotions": [
            {
                "id": "promo--idle--palette_drift_pass",
                "specification_id": "idle/palette_drift_pass",
                "attempt_id": "idle--palette_drift_pass--001",
                "measurement_path": "gate-controls/reports/m.json",
                "status": "PENDING_VERIFICATION",
                "recorded_at": "2026-07-27T00:00:00+00:00",
            }
        ],
    }
    manifest_path = gc / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    measurement_path = gc / "reports" / "m.json"
    measurement_path.parent.mkdir(parents=True)
    measurement_path.write_text("{}\n")
    provenance_path = gc / "provenance" / "p.json"
    provenance_path.parent.mkdir(parents=True)
    provenance_path.write_text("{}\n")
    packet_path = gc / "reviews" / "x" / "packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_doc = {"packet_sha256": "d" * 64}
    packet_path.write_text(json.dumps(packet_doc) + "\n")
    review_paths = []
    for name in ("review--01.json", "review--02.json"):
        review_path = gc / "reviews" / "x" / name
        review_path.write_text(json.dumps({"verdict": "APPROVE"}) + "\n")
        review_paths.append(review_path)
    bound = gv.manifest_sha256_at_binding(
        manifest_path,
        promotion_ids=frozenset({"promo--idle--palette_drift_pass"}),
    )
    record = {
        "schema": "gate-control-verification/0",
        "promotion_id": "promo--idle--palette_drift_pass",
        "specification_id": "idle/palette_drift_pass",
        "attempt_id": "idle--palette_drift_pass--001",
        "measurement_path": "gate-controls/reports/m.json",
        "measurement_sha256": ge.sha256_file(measurement_path),
        "provenance_path": "gate-controls/provenance/p.json",
        "provenance_sha256": ge.sha256_file(provenance_path),
        "raw_sha256": "c" * 64,
        "packet_path": "reviews/x/packet.json",
        "packet_sha256": "d" * 64,
        "reviews": [
            {
                "review_id": "review--01",
                "path": "reviews/x/review--01.json",
                "sha256": ge.sha256_file(review_paths[0]),
                "verdict": "APPROVE",
            },
            {
                "review_id": "review--02",
                "path": "reviews/x/review--02.json",
                "sha256": ge.sha256_file(review_paths[1]),
                "verdict": "APPROVE",
            },
        ],
        "manifest_sha256": bound,
        "repository_commit": "deadbeef",
        "commands": [{"command": "npm test", "exit_code": 0, "evidence_row": "1 passed"}],
        "recorded_at": "2026-07-27T00:00:00+00:00",
        "status": "ACTIVE",
        "failure_reason": None,
    }
    path = gc / "verification" / "promo--idle--palette_drift_pass.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    with pytest.raises(gv.VerificationError, match="manifest status"):
        gv.validate_verification_record(tmp_path, path)


def test_active_promotion_verification_records_validate_against_repository() -> None:
    if not _issue_59_records_present():
        pytest.skip("verification records not written yet")
    verification_root = ROOT / "gate-controls" / "verification"
    paths = sorted(verification_root.glob("promo--*.json"))
    assert paths, "expected issue #59 verification records"
    for path in paths:
        promotion_id = path.stem
        if promotion_id not in gv.VERIFICATION_PROMOTION_IDS:
            continue
        gv.validate_verification_record(ROOT, path)


def test_active_promotion_manifest_matches_verification_record() -> None:
    if not (
        _issue_59_records_present()
        or _issue_60_records_present()
        or _issue_61_records_present()
    ):
        pytest.skip("verification records not written yet")
    manifest = ge.load_manifest(ROOT / "gate-controls" / "manifest.json")
    verification_root = ROOT / "gate-controls" / "verification"
    for promotion_id in gv.VERIFICATION_PROMOTION_IDS:
        record_path = verification_root / f"{promotion_id}.json"
        if not record_path.is_file():
            continue
        promotion = next(p for p in manifest.promotions if p.id == promotion_id)
        record = json.loads(record_path.read_text())
        if record["status"] == "ACTIVE":
            assert promotion.status == "ACTIVE"
            assert all(r["verdict"] == "APPROVE" for r in record["reviews"])
            assert all(c["exit_code"] == 0 for c in record["commands"])
            assert record["failure_reason"] is None
        else:
            assert promotion.status == "INVALIDATED"
            assert record["failure_reason"]


def test_apply_manifest_statuses_transitions_named_promotions_only(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "gate-control-manifest/0",
                "specifications": [],
                "promotions": [
                    {
                        "id": "promo--idle--palette_drift_pass",
                        "status": "PENDING_VERIFICATION",
                    },
                    {
                        "id": "promo--walk--loop_closure_pass",
                        "status": "PENDING_VERIFICATION",
                    },
                ],
            },
            indent=2,
        )
        + "\n"
    )
    gv.apply_manifest_statuses(
        manifest_path,
        statuses={"promo--idle--palette_drift_pass": "ACTIVE"},
    )
    doc = json.loads(manifest_path.read_text())
    statuses = {promo["id"]: promo["status"] for promo in doc["promotions"]}
    assert statuses == {
        "promo--idle--palette_drift_pass": "ACTIVE",
        "promo--walk--loop_closure_pass": "PENDING_VERIFICATION",
    }


def test_repository_review_dirs_validate_after_second_review_input() -> None:
    for promotion_id in gv.VERIFICATION_PROMOTION_IDS:
        attempt_id = gv.review_dir_for_promotion(promotion_id)
        review_dir = ROOT / "gate-controls" / "reviews" / attempt_id
        if not (review_dir / "packet.json").is_file():
            pytest.skip(f"missing review packet for {promotion_id}")
        gv.ensure_blinded_second_review_input(review_dir)
        report = gr.validate_review_dir(review_dir, root=ROOT)
        assert report["ok"] is True


def test_issue_60_pre_transition_manifest_hash_resets_named_promotion_status(
    tmp_path: Path,
) -> None:
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [],
        "promotions": [
            {"id": "promo--emissive--loop_closure_pass", "status": "ACTIVE"},
            {"id": "promo--airborne--palette_drift_pass", "status": "ACTIVE"},
            {"id": "promo--walk--loop_closure_pass", "status": "PENDING_VERIFICATION"},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    digest = gv.manifest_sha256_at_binding(
        path,
        promotion_ids=gv.ISSUE_60_PROMOTION_IDS,
    )
    expected_doc = dict(manifest)
    for promo in expected_doc["promotions"]:
        if promo["id"] in gv.ISSUE_60_PROMOTION_IDS:
            promo["status"] = "PENDING_VERIFICATION"
    expected = ge.sha256_bytes(
        (json.dumps(expected_doc, indent=2) + "\n").encode()
    )
    assert digest == expected


def test_issue_60_verification_records_validate_against_repository() -> None:
    if not _issue_60_records_present():
        pytest.skip("issue #60 verification records not written yet")
    verification_root = ROOT / "gate-controls" / "verification"
    for promotion_id in gv.ISSUE_60_PROMOTION_IDS:
        path = verification_root / f"{promotion_id}.json"
        assert path.is_file(), f"missing verification for {promotion_id}"
        gv.validate_verification_record(ROOT, path)


def test_issue_60_manifest_matches_verification_records() -> None:
    if not _issue_60_records_present():
        pytest.skip("issue #60 verification records not written yet")
    manifest = ge.load_manifest(ROOT / "gate-controls" / "manifest.json")
    verification_root = ROOT / "gate-controls" / "verification"
    for promotion_id in gv.ISSUE_60_PROMOTION_IDS:
        promotion = next(p for p in manifest.promotions if p.id == promotion_id)
        record_path = verification_root / f"{promotion_id}.json"
        record = json.loads(record_path.read_text())
        if record["status"] == "ACTIVE":
            assert promotion.status == "ACTIVE"
        else:
            assert promotion.status == "INVALIDATED"


def test_issue_61_pre_transition_manifest_hash_resets_named_promotion_status(
    tmp_path: Path,
) -> None:
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [],
        "promotions": [
            {"id": "promo--walk--loop_closure_pass", "status": "ACTIVE"},
            {"id": "promo--swing--silhouette_budget", "status": "ACTIVE"},
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    digest = gv.manifest_sha256_at_binding(
        path,
        promotion_id="promo--walk--loop_closure_pass",
    )
    expected_doc = dict(manifest)
    for promo in expected_doc["promotions"]:
        if promo["id"] in gv.ISSUE_61_PROMOTION_IDS:
            promo["status"] = "PENDING_VERIFICATION"
    expected = ge.sha256_bytes(
        (json.dumps(expected_doc, indent=2) + "\n").encode()
    )
    assert digest == expected


def test_issue_61_verification_records_validate_against_repository() -> None:
    if not _issue_61_records_present():
        pytest.skip("issue #61 verification records not written yet")
    verification_root = ROOT / "gate-controls" / "verification"
    for promotion_id in gv.ISSUE_61_PROMOTION_IDS:
        path = verification_root / f"{promotion_id}.json"
        assert path.is_file(), f"missing verification for {promotion_id}"
        gv.validate_verification_record(ROOT, path)


def test_issue_61_manifest_matches_verification_records() -> None:
    if not _issue_61_records_present():
        pytest.skip("issue #61 verification records not written yet")
    manifest = ge.load_manifest(ROOT / "gate-controls" / "manifest.json")
    verification_root = ROOT / "gate-controls" / "verification"
    for promotion_id in gv.ISSUE_61_PROMOTION_IDS:
        promotion = next(p for p in manifest.promotions if p.id == promotion_id)
        record_path = verification_root / f"{promotion_id}.json"
        record = json.loads(record_path.read_text())
        if record["status"] == "ACTIVE":
            assert promotion.status == "ACTIVE"
        else:
            assert promotion.status == "INVALIDATED"
