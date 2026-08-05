"""Promotion verification records for Wave A activation (issues #59–#61)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import canonical
from pipeline import corpus_paths as cp
from pipeline import gate_control as gc
from pipeline import gate_evidence as ge
from pipeline import gate_review as gr
from pipeline import gate_verification as gv

ROOT = Path(__file__).resolve().parents[1]
IDLE_CONTROL = ROOT / "gate-controls/raw/idle--silhouette_budget--001.png"
BINDING_GOOD = ROOT / "prototype/strip-coherence/inbox/07-NEG-palette-drift.png"


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


def test_apply_manifest_statuses_acquires_manifest_lock(tmp_path: Path) -> None:
    """C6: apply_manifest_statuses writes under .manifest.lock like other manifest mutations."""
    repo_gc = ROOT / "gate-controls"
    before = ge.fingerprint_tree(repo_gc)
    manifest_path = tmp_path / "gate-controls" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
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
                ],
            },
            indent=2,
        )
        + "\n"
    )
    lock_path = manifest_path.parent / ".manifest.lock"
    assert not lock_path.is_file()
    gv.apply_manifest_statuses(
        manifest_path,
        statuses={"promo--idle--palette_drift_pass": "ACTIVE"},
    )
    assert lock_path.is_file()
    after = ge.fingerprint_tree(repo_gc)
    assert after == before


def test_repository_review_dirs_validate_after_second_review_input() -> None:
    for promotion_id in gv.VERIFICATION_PROMOTION_IDS:
        attempt_id = gv.review_dir_for_promotion(ROOT, promotion_id)
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


def _seed_manifest_promotion_candidate(
    tmp_path: Path,
    *,
    spec_id: str = "idle/silhouette_budget",
    motion_class: str = "idle",
    target_gate: str = "silhouette_budget",
    attempt_id: str = "idle--silhouette_budget--099",
    promotion_id: str = "promo--idle--silhouette_budget",
) -> Path:
    """Minimal graph-valid PENDING_VERIFICATION candidate outside Wave A slices."""
    gc_root = tmp_path / "gate-controls"
    gc_root.mkdir(parents=True)
    shutil.copy2(
        ROOT / "gate-controls/acceptance-profiles.json",
        gc_root / "acceptance-profiles.json",
    )
    (gc_root / "attempts.jsonl").write_text("")
    for name in ("raw", "provenance", "reports", "reviews", "verification"):
        (gc_root / name).mkdir(exist_ok=True)

    raw_rel = f"gate-controls/raw/{attempt_id}.png"
    shutil.copy2(IDLE_CONTROL, tmp_path / raw_rel)
    raw_sha = ge.sha256_file(tmp_path / raw_rel)
    measurement_rel = f"gate-controls/reports/{attempt_id}/2026-07-27T12-00-00+00-00.json"
    measurement = {
        "schema": gc.MEASUREMENT_SCHEMA,
        "raw_sha256": raw_sha,
        "motion_class": motion_class,
        "target_gate": target_gate,
        "applicable_gates": [target_gate],
        "structural": {"recovered": True},
        "gates": {
            target_gate: {
                "outcome": "fail",
                "acceptance_outcome": "FAIL",
                "metric": 0.3,
                "budget": 0.2239,
                "hard_fail": 0.3,
            }
        },
        "isolation": "ISOLATED",
        "blockers": [],
        "caveats": [],
        "primary_failure": None,
    }
    provenance_rel = f"gate-controls/provenance/{attempt_id}.json"
    provenance = {
        "schema": "gate-control-provenance/0",
        "specification_id": spec_id,
        "attempt_id": attempt_id,
        "generator": "cursor-image-gen",
        "prompt_text": "prompt",
        "prompt_sha256": ge.sha256_bytes(b"prompt"),
        "reference_image_sha256": [],
        "generated_at": "2026-07-27T12:00:00+00:00",
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
        "ordinal": 99,
        "artifact_state": "retained",
        "isolation": "ISOLATED",
        "recorded_at": "2026-07-27T12:00:00+00:00",
        "measurement_path": measurement_rel,
        "provenance_path": provenance_rel,
        "raw_sha256": raw_sha,
        "promotion_blockers": [],
        "primary_failure": None,
    }
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [
            {
                "id": spec_id,
                "motion_class": motion_class,
                "target_gate": target_gate,
                "active_promotion": promotion_id,
            }
        ],
        "promotions": [
            {
                "id": promotion_id,
                "specification_id": spec_id,
                "attempt_id": attempt_id,
                "measurement_path": measurement_rel,
                "status": gv.PENDING_STATUS,
                "recorded_at": "2026-07-27T12:00:00+00:00",
            }
        ],
    }
    (tmp_path / measurement_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / measurement_rel).write_text(json.dumps(measurement, indent=2) + "\n")
    (tmp_path / provenance_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / provenance_rel).write_text(json.dumps(provenance, indent=2) + "\n")
    (gc_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    ge.append_attempt_record(gc_root / "attempts.jsonl", attempt)

    review_dir = gc_root / "reviews" / attempt_id
    review_dir.mkdir(parents=True, exist_ok=True)
    packet = gr.build_review_packet(
        root=tmp_path,
        attempt_id=attempt_id,
        gate=target_gate,
        budget_binding_good=BINDING_GOOD,
        packet_kind="PROMOTION_VERIFICATION",
        promotion_id=promotion_id,
    )
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    for index, review_id in enumerate(("review--01", "review--02"), start=1):
        record = gr.make_audit_record(
            packet=packet,
            review_id=review_id,
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="fixture",
            rationale="fixture",
            reviewer_identity=f"reviewer-{index}",
            model_identity="fixture-model",
            model_version="1",
            timestamp="2026-07-27T12:00:00+00:00",
        )
        gr.write_audit_record(review_dir / f"review--0{index}.json", record)
    gv.ensure_blinded_second_review_input(review_dir)
    return gc_root


def test_verify_promotion_rejects_absent_manifest_id(tmp_path: Path) -> None:
    _seed_manifest_promotion_candidate(tmp_path)
    with pytest.raises(ge.EvidenceError, match="unknown promotion_id"):
        gv.verify_promotion(tmp_path, "promo--missing--silhouette_budget")


def test_verify_promotion_accepts_manifest_backed_promotion(tmp_path: Path) -> None:
    promotion_id = "promo--idle--silhouette_budget"
    _seed_manifest_promotion_candidate(tmp_path, promotion_id=promotion_id)
    commands = [
        gv.CommandResult(command="npm test", exit_code=0, evidence_row="1 passed"),
        gv.CommandResult(
            command="npm run prototype:strip:corpus",
            exit_code=0,
            evidence_row="scored 1/1",
        ),
        gv.CommandResult(
            command="npm run prototype:strip:adversarial",
            exit_code=0,
            evidence_row="Separated=17",
        ),
        gv.CommandResult(
            command="npm run prototype:strip:alpha-budgets",
            exit_code=0,
            evidence_row="Separated=17",
        ),
    ]
    record = gv.verify_promotion(tmp_path, promotion_id, commands=commands)
    assert record["status"] == gv.ACTIVE_STATUS
    assert record["promotion_id"] == promotion_id
    assert record["attempt_id"] == "idle--silhouette_budget--099"


def test_review_dir_derived_from_manifest_attempt_not_promotion_id(
    tmp_path: Path,
) -> None:
    attempt_id = "synthetic--displacement_pass--007"
    promotion_id = "promo--synthetic--displacement_pass"
    _seed_manifest_promotion_candidate(
        tmp_path,
        spec_id="synthetic/displacement_pass",
        motion_class="airborne",
        target_gate="displacement_pass",
        attempt_id=attempt_id,
        promotion_id=promotion_id,
    )
    assert gv.review_dir_for_promotion(tmp_path, promotion_id) == attempt_id
    review_dir = tmp_path / "gate-controls" / "reviews" / attempt_id
    assert (review_dir / "packet.json").is_file()


def test_cli_run_accepts_manifest_promotion_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    promotion_id = "promo--idle--silhouette_budget"
    _seed_manifest_promotion_candidate(tmp_path, promotion_id=promotion_id)
    monkeypatch.chdir(tmp_path)
    with patch.object(gv, "run_required_commands") as run_commands:
        run_commands.return_value = [
            gv.CommandResult(command="npm test", exit_code=0, evidence_row="1 passed"),
            gv.CommandResult(
                command="npm run prototype:strip:corpus",
                exit_code=0,
                evidence_row="scored 1/1",
            ),
            gv.CommandResult(
                command="npm run prototype:strip:adversarial",
                exit_code=0,
                evidence_row="Separated=17",
            ),
            gv.CommandResult(
                command="npm run prototype:strip:alpha-budgets",
                exit_code=0,
                evidence_row="Separated=17",
            ),
        ]
        exit_code = gv.main(["run", promotion_id])
    assert exit_code == 0


def test_cli_run_rejects_absent_manifest_promotion_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_manifest_promotion_candidate(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert gv.main(["run", "promo--missing--silhouette_budget"]) != 0


def test_checked_in_gate_controls_unchanged_after_temp_verification(
    tmp_path: Path,
) -> None:
    from pipeline import gate_control_acquire as gca

    before = ge.fingerprint_tree(ROOT / "gate-controls")
    promotion_id = "promo--idle--silhouette_budget"
    gc_root = _seed_manifest_promotion_candidate(tmp_path, promotion_id=promotion_id)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(gc_root)}):
        gca.complete_promotion_verification(
            tmp_path,
            promotion_id,
            commands=[
                gv.CommandResult(command="npm test", exit_code=0, evidence_row="1 passed"),
                gv.CommandResult(
                    command="npm run prototype:strip:corpus",
                    exit_code=0,
                    evidence_row="scored 1/1",
                ),
                gv.CommandResult(
                    command="npm run prototype:strip:adversarial",
                    exit_code=0,
                    evidence_row="Separated=17",
                ),
                gv.CommandResult(
                    command="npm run prototype:strip:alpha-budgets",
                    exit_code=0,
                    evidence_row="Separated=17",
                ),
            ],
        )
    after = ge.fingerprint_tree(ROOT / "gate-controls")
    assert after == before


def test_verify_promotion_resolves_legacy_packet_corpus_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C5: verify_promotion resolves frozen corpus paths from packet.json."""
    monkeypatch.setattr(cp, "CORPUS_ROOT", Path("corpus/live"))
    promotion_id = "promo--idle--silhouette_budget"
    gc_root = _seed_manifest_promotion_candidate(tmp_path, promotion_id=promotion_id)
    attempt_id = "idle--silhouette_budget--099"
    review_dir = gc_root / "reviews" / attempt_id
    live_good = tmp_path / "corpus/live/inbox/07-NEG-palette-drift.png"
    live_good.parent.mkdir(parents=True, exist_ok=True)
    live_good.write_bytes(BINDING_GOOD.read_bytes())
    packet_doc = json.loads((review_dir / "packet.json").read_text())
    recorded_good = "prototype/strip-coherence/inbox/07-NEG-palette-drift.png"
    packet_doc["budget_binding_good"]["path"] = recorded_good
    packet_doc["packet_sha256"] = canonical.self_excluding_digest(
        packet_doc, field="packet_sha256"
    )
    (review_dir / "packet.json").write_text(
        json.dumps(packet_doc, indent=2, sort_keys=True) + "\n"
    )
    for review_id in ("review--01", "review--02"):
        review_doc = json.loads((review_dir / f"{review_id}.json").read_text())
        review_doc["packet_sha256"] = packet_doc["packet_sha256"]
        (review_dir / f"{review_id}.json").write_text(
            json.dumps(review_doc, indent=2, sort_keys=True) + "\n"
        )
    blinded = json.loads((review_dir / "review-input--02.json").read_text())
    blinded["packet_sha256"] = packet_doc["packet_sha256"]
    (review_dir / "review-input--02.json").write_text(
        json.dumps(blinded, indent=2, sort_keys=True) + "\n"
    )
    commands = [
        gv.CommandResult(command="npm test", exit_code=0, evidence_row="1 passed"),
        gv.CommandResult(
            command="npm run prototype:strip:corpus",
            exit_code=0,
            evidence_row="scored 1/1",
        ),
        gv.CommandResult(
            command="npm run prototype:strip:adversarial",
            exit_code=0,
            evidence_row="Separated=17",
        ),
        gv.CommandResult(
            command="npm run prototype:strip:alpha-budgets",
            exit_code=0,
            evidence_row="Separated=17",
        ),
    ]
    record = gv.verify_promotion(tmp_path, promotion_id, commands=commands)
    assert record["review_report"]["ok"] is True
    assert packet_doc["budget_binding_good"]["path"] == recorded_good
