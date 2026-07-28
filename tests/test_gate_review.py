"""Review packet, panel selection, audit, and second-review triggers (issue #49)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pipeline import gate_evidence as ge
from pipeline import gate_review as gr

ROOT = Path(__file__).resolve().parents[1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _png(tag: bytes) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + tag + b"\x00" * 32


def _evidence(tmp_path: Path, *, separated: bool = True) -> dict[str, object]:
    gc = tmp_path / "gate-controls"
    raw = _png(b"candidate-raw")
    raw_sha = _sha(raw)
    good = _png(b"binding-good")
    good_sha = _sha(good)
    attempt_id = "idle--silhouette_budget--001"
    spec_id = "idle/silhouette_budget"
    promo_id = "promo--idle--silhouette_budget"
    measurement_rel = f"gate-controls/reports/{attempt_id}/m1.json"
    provenance_rel = f"gate-controls/provenance/{attempt_id}.json"
    raw_rel = f"gate-controls/raw/{attempt_id}.png"
    good_rel = "inbox/binding-good.png"

    measurement = {
        "schema": "gate-control-measurement/0",
        "raw": str(tmp_path / raw_rel),
        "raw_sha256": raw_sha,
        "scorer_gate_config_sha256": "abc",
        "motion_class": "idle",
        "target_gate": "silhouette_budget",
        "applicable_gates": ["silhouette_budget"],
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "fail",
                "metric": 0.3,
                "budget": 0.17,
                "reason": None,
            }
        },
        "isolation": "ISOLATED",
        "blockers": [],
        "caveats": ["displacement undecidable"],
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
    gate_status = "SEPARATED" if separated else "UNSEPARATED"
    gate_entry: dict[str, object] = {
        "status": gate_status,
        "budget": 0.17,
    }
    if separated:
        gate_entry["hard_fail"] = 0.3
        gate_entry["active_promotion"] = promo_id
        gate_entry["control_attempt"] = attempt_id
    else:
        gate_entry["evidence_attempt"] = attempt_id
        gate_entry["rationale"] = "fixture unseparated"
    profiles = {
        "schema": "acceptance-profile-index/0",
        "profiles": {"idle": {"motion_class": "idle", "gates": {"silhouette_budget": gate_entry}}},
    }
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [
            {
                "id": spec_id,
                "motion_class": "idle",
                "target_gate": "silhouette_budget",
                "active_promotion": promo_id if separated else None,
            }
        ],
        "promotions": [],
    }
    if separated:
        manifest["promotions"] = [
            {
                "id": promo_id,
                "specification_id": spec_id,
                "attempt_id": attempt_id,
                "measurement_path": measurement_rel,
                "status": "PENDING_VERIFICATION",
                "recorded_at": "2026-07-26T16:00:00+00:00",
                "note": "fixture",
            }
        ]
        manifest["specifications"][0]["active_promotion"] = promo_id

    _write(tmp_path / raw_rel, raw)
    _write(tmp_path / good_rel, good)
    _write(tmp_path / measurement_rel, measurement)
    _write(tmp_path / provenance_rel, provenance)
    _write(gc / "manifest.json", manifest)
    (gc / "attempts.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (gc / "attempts.jsonl").write_text(json.dumps(attempt, sort_keys=True) + "\n")
    _write(gc / "acceptance-profiles.json", profiles)
    return {
        "root": tmp_path,
        "gc": gc,
        "attempt_id": attempt_id,
        "promo_id": promo_id,
        "spec_id": spec_id,
        "raw_sha": raw_sha,
        "good_sha": good_sha,
        "raw_path": tmp_path / raw_rel,
        "good_path": tmp_path / good_rel,
        "measurement": measurement,
        "separated": separated,
    }


def test_every_gate_selects_required_panel_kind() -> None:
    assert gr.panel_kind_for_gate("silhouette_budget") == "occupancy_difference"
    assert gr.panel_kind_for_gate("loop_closure_pass") == "occupancy_difference"
    assert gr.panel_kind_for_gate("min_pair_cohort_pass") == "occupancy_difference"
    assert gr.panel_kind_for_gate("palette_drift_pass") == "quantized_palette_histogram"
    assert gr.panel_kind_for_gate("displacement_pass") == "best_alignment_vectors"


def test_separated_packet_includes_control_and_is_deterministic(tmp_path: Path) -> None:
    fx = _evidence(tmp_path, separated=True)
    packet_a = gr.build_review_packet(
        root=fx["root"],
        attempt_id=fx["attempt_id"],
        gate="silhouette_budget",
        budget_binding_good=fx["good_path"],
        packet_kind="CANDIDATE_REVIEW",
    )
    packet_b = gr.build_review_packet(
        root=fx["root"],
        attempt_id=fx["attempt_id"],
        gate="silhouette_budget",
        budget_binding_good=fx["good_path"],
        packet_kind="CANDIDATE_REVIEW",
    )
    assert packet_a.to_manifest() == packet_b.to_manifest()
    assert packet_a.packet_sha256 == packet_b.packet_sha256
    assert packet_a.panel_kind == "occupancy_difference"
    assert packet_a.candidate.role == "candidate"
    assert packet_a.candidate.raw_sha256 == fx["raw_sha"]
    assert packet_a.budget_binding_good.role == "budget_binding_good"
    assert packet_a.budget_binding_good.raw_sha256 == fx["good_sha"]
    assert packet_a.gate_control is not None
    assert packet_a.gate_control.role == "gate_control"
    assert packet_a.no_autonomous_hard_fail is False
    assert packet_a.metric == 0.3
    assert packet_a.budget == 0.17
    assert packet_a.hard_fail_boundary == 0.3


def test_unseparated_packet_states_no_autonomous_hard_fail(tmp_path: Path) -> None:
    fx = _evidence(tmp_path, separated=False)
    packet = gr.build_review_packet(
        root=fx["root"],
        attempt_id=fx["attempt_id"],
        gate="silhouette_budget",
        budget_binding_good=fx["good_path"],
        packet_kind="CANDIDATE_REVIEW",
    )
    assert packet.gate_control is None
    assert packet.no_autonomous_hard_fail is True
    assert "no autonomous hard-fail reference" in packet.no_autonomous_hard_fail_reason


def test_promotion_verification_labels_subject_and_proposed_control(tmp_path: Path) -> None:
    fx = _evidence(tmp_path, separated=True)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    assert packet.packet_kind == "PROMOTION_VERIFICATION"
    assert packet.candidate.role == "candidate"
    assert packet.proposed_hard_fail_reference is not None
    assert packet.proposed_hard_fail_reference.role == "proposed_hard_fail_reference"
    assert packet.candidate.raw_sha256 == packet.proposed_hard_fail_reference.raw_sha256
    assert packet.candidate.raw_sha256 == fx["raw_sha"]
    # Does not represent the Promotion as ACTIVE.
    assert packet.promotion_status == "PENDING_VERIFICATION"
    assert packet.promotion_status != "ACTIVE"


def test_audit_rejects_each_missing_required_field(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    base = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="intentional pose change",
        rationale="matches binding good identity",
        reviewer_identity="agent-test",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
        caveats=list(packet.caveats),
    )
    for field in gr.AUDIT_REQUIRED_FIELDS:
        bad = dict(base)
        bad.pop(field)
        with pytest.raises(gr.ReviewError, match=field):
            gr.validate_audit_record(bad)


def test_reject_audit_requires_primary_reason_and_retry_intent(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    base = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="REJECT",
        frames=[0, 1],
        observed_feature="identity break",
        rationale="subject changes",
        reviewer_identity="agent-test",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
        primary_gate="silhouette_budget",
        primary_reason_code="IDENTITY_DRIFT",
        retry_intent="keep identity stable across frames",
    )
    gr.validate_audit_record(base)
    for field in ("primary_gate", "primary_reason_code", "retry_intent"):
        bad = dict(base)
        bad.pop(field)
        with pytest.raises(gr.ReviewError, match=field):
            gr.validate_audit_record(bad)


def test_second_review_triggers_midpoint_multi_uncertain_caveat() -> None:
    # Midpoint of [0.17, 0.3] inclusive is 0.235; 0.235 and above trigger.
    assert "metric_at_or_beyond_midpoint" in gr.compute_second_review_triggers(
        metric=0.235,
        budget=0.17,
        hard_fail_boundary=0.3,
        gates_in_review=1,
        first_verdict=None,
        relies_on_caveated_dimension=False,
    )
    assert "metric_at_or_beyond_midpoint" not in gr.compute_second_review_triggers(
        metric=0.234,
        budget=0.17,
        hard_fail_boundary=0.3,
        gates_in_review=1,
        first_verdict=None,
        relies_on_caveated_dimension=False,
    )
    assert "multiple_gates_in_review" in gr.compute_second_review_triggers(
        metric=0.18,
        budget=0.17,
        hard_fail_boundary=0.3,
        gates_in_review=2,
        first_verdict=None,
        relies_on_caveated_dimension=False,
    )
    assert "first_verdict_uncertain" in gr.compute_second_review_triggers(
        metric=0.18,
        budget=0.17,
        hard_fail_boundary=0.3,
        gates_in_review=1,
        first_verdict="UNCERTAIN",
        relies_on_caveated_dimension=False,
    )
    assert "caveat_reliance" in gr.compute_second_review_triggers(
        metric=0.18,
        budget=0.17,
        hard_fail_boundary=0.3,
        gates_in_review=1,
        first_verdict="APPROVE",
        relies_on_caveated_dimension=True,
    )


def test_promotion_verification_always_triggers_second_review_at_boundary_c(
    tmp_path: Path,
) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    # Candidate sits at hard-fail boundary C → inclusive midpoint trigger.
    assert packet.metric == packet.hard_fail_boundary
    triggers = gr.compute_second_review_triggers(
        metric=packet.metric,
        budget=packet.budget,
        hard_fail_boundary=packet.hard_fail_boundary,
        gates_in_review=1,
        first_verdict=None,
        relies_on_caveated_dimension=False,
    )
    assert "metric_at_or_beyond_midpoint" in triggers
    assert gr.promotion_verification_requires_second_review(packet) is True


def test_blind_second_review_has_distinct_identity_and_hides_prior(
    tmp_path: Path,
) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    first = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose transition",
        rationale="secret rationale must not leak",
        reviewer_identity="reviewer-a",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    second_input = gr.blinded_packet_for_second_review(
        packet,
        first_review=first,
        second_review_id="review--02",
        second_reviewer_identity="reviewer-b",
    )
    assert second_input["review_id"] == "review--02"
    assert second_input["reviewer_identity"] == "reviewer-b"
    assert second_input["reviewer_identity"] != first["reviewer_identity"]
    blob = json.dumps(second_input, sort_keys=True)
    assert "APPROVE" not in blob
    assert "secret rationale" not in blob
    assert first["review_id"] not in blob
    assert second_input["packet_sha256"] == packet.packet_sha256


def test_write_audit_is_immutable(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    audit = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose transition",
        rationale="ok",
        reviewer_identity="reviewer-a",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    out = fx["gc"] / "reviews" / fx["attempt_id"] / "review--01.json"
    gr.write_audit_record(out, audit)
    with pytest.raises(ge.EvidenceError, match="refusing to mutate"):
        gr.write_audit_record(out, audit)


def test_review_primitives_do_not_mutate_repository_evidence(tmp_path: Path) -> None:
    repo_gc = ROOT / "gate-controls"
    before = ge.fingerprint_tree(repo_gc)
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    audit = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose transition",
        rationale="ok",
        reviewer_identity="reviewer-a",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    out = tmp_path / "reviews-out" / "review--01.json"
    gr.write_audit_record(out, audit)
    after = ge.fingerprint_tree(repo_gc)
    assert before == after
    assert not str(out).startswith(str(repo_gc))


def _write_two_audits(review_dir: Path, packet: gr.ReviewPacket) -> dict[str, object]:
    audits: dict[str, object] = {}
    for review_id, identity in (("review--01", "reviewer-a"), ("review--02", "reviewer-b")):
        audit = gr.make_audit_record(
            packet=packet,
            review_id=review_id,
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="pose transition",
            rationale=f"ok-{review_id}",
            reviewer_identity=identity,
            model_identity="composer",
            model_version="2.5",
            timestamp="2026-07-27T00:00:00+00:00",
            second_review_triggers=["metric_at_or_beyond_midpoint"],
        )
        gr.write_audit_record(review_dir / f"{review_id}.json", audit)
        audits[review_id] = audit
    blinded = gr.blinded_packet_for_second_review(
        packet,
        first_review=audits["review--01"],
        second_review_id="review--02",
        second_reviewer_identity="reviewer-b",
    )
    gr.write_second_review_input(review_dir / "review-input--02.json", blinded)
    return audits


def test_packet_to_manifest_and_validate_review_dir_round_trip(tmp_path: Path) -> None:
    """C3: write path (to_manifest) and read path (validate_review_dir) share one digest expression."""
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    manifest_path = review_dir / "packet.json"
    gr.write_packet_manifest(manifest_path, packet)
    report = gr.validate_review_dir(review_dir)
    assert report["ok"] is True

    doc = json.loads(manifest_path.read_text())
    doc["metric"] = 0.99
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")
    with pytest.raises(gr.ReviewError, match="SHA-256 mismatch"):
        gr.validate_review_dir(review_dir)


def test_review_packet_from_manifest_rehydrates_stored_packet(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    manifest_path = review_dir / "packet.json"
    gr.write_packet_manifest(manifest_path, packet)
    restored = gr.review_packet_from_manifest(json.loads(manifest_path.read_text()))
    assert restored.packet_sha256 == packet.packet_sha256
    assert restored.promotion_status == "PENDING_VERIFICATION"


def test_validate_cli_accepts_written_packet_and_audits(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    _write_two_audits(review_dir, packet)
    report = gr.validate_review_dir(review_dir)
    assert report["ok"] is True
    assert report["reviews"] == ["review--01", "review--02"]
    assert report["packet_sha256"] == packet.packet_sha256


def test_validate_review_dir_recomputes_packet_input_hashes(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    _write_two_audits(review_dir, packet)
    fx["raw_path"].write_bytes(_png(b"tampered-candidate"))
    with pytest.raises(gr.ReviewError, match="SHA-256 mismatch"):
        gr.validate_review_dir(review_dir)


def test_validate_review_dir_requires_blinded_second_review_input(
    tmp_path: Path,
) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    for review_id, identity in (("review--01", "reviewer-a"), ("review--02", "reviewer-b")):
        audit = gr.make_audit_record(
            packet=packet,
            review_id=review_id,
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="pose",
            rationale="ok",
            reviewer_identity=identity,
            model_identity="composer",
            model_version="2.5",
            timestamp="2026-07-27T00:00:00+00:00",
            second_review_triggers=["metric_at_or_beyond_midpoint"],
        )
        gr.write_audit_record(review_dir / f"{review_id}.json", audit)
    with pytest.raises(gr.ReviewError, match="blinded second-review input"):
        gr.validate_review_dir(review_dir)


@pytest.mark.parametrize(
    ("gate", "panel_kind"),
    [
        ("silhouette_budget", "occupancy_difference"),
        ("loop_closure_pass", "occupancy_difference"),
        ("min_pair_cohort_pass", "occupancy_difference"),
        ("palette_drift_pass", "quantized_palette_histogram"),
        ("displacement_pass", "best_alignment_vectors"),
    ],
)
def test_packet_construction_selects_panel_and_reference_set(
    tmp_path: Path, gate: str, panel_kind: str
) -> None:
    fx = _evidence(tmp_path, separated=True)
    measurement_path = fx["root"] / "gate-controls/reports" / fx["attempt_id"] / "m1.json"
    measurement = json.loads(measurement_path.read_text())
    measurement["target_gate"] = gate
    measurement["gates"] = {
        gate: {"outcome": "fail", "metric": 0.3, "budget": 0.17, "reason": None}
    }
    _write(measurement_path, measurement)

    profiles_path = fx["gc"] / "acceptance-profiles.json"
    profiles = json.loads(profiles_path.read_text())
    profiles["profiles"]["idle"]["gates"] = {
        gate: {
            "status": "SEPARATED",
            "budget": 0.17,
            "hard_fail": 0.3,
            "active_promotion": fx["promo_id"],
            "control_attempt": fx["attempt_id"],
        }
    }
    _write(profiles_path, profiles)

    manifest_path = fx["gc"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["specifications"][0]["target_gate"] = gate
    manifest["specifications"][0]["id"] = f"idle/{gate}"
    manifest["promotions"][0]["specification_id"] = f"idle/{gate}"
    _write(manifest_path, manifest)

    attempt_path = fx["gc"] / "attempts.jsonl"
    attempt = json.loads(attempt_path.read_text())
    attempt["specification_id"] = f"idle/{gate}"
    attempt_path.write_text(json.dumps(attempt, sort_keys=True) + "\n")

    provenance_path = fx["root"] / "gate-controls/provenance" / f"{fx['attempt_id']}.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["specification_id"] = f"idle/{gate}"
    _write(provenance_path, provenance)

    packet = gr.build_review_packet(
        root=fx["root"],
        attempt_id=fx["attempt_id"],
        gate=gate,
        budget_binding_good=fx["good_path"],
        packet_kind="CANDIDATE_REVIEW",
    )
    assert packet.panel_kind == panel_kind
    assert packet.candidate.role == "candidate"
    assert packet.budget_binding_good.role == "budget_binding_good"
    assert packet.gate_control is not None
    assert packet.gate_control.role == "gate_control"
    assert packet.no_autonomous_hard_fail is False


def test_audit_rejects_empty_string_required_fields(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    base = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose",
        rationale="ok",
        reviewer_identity="reviewer-a",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    bad = dict(base)
    bad["rationale"] = ""
    with pytest.raises(gr.ReviewError, match="rationale"):
        gr.validate_audit_record(bad)


def test_validate_review_dir_rejects_duplicate_review_ids(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    first = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose",
        rationale="ok-first",
        reviewer_identity="reviewer-a",
        model_identity="composer",
        model_version="2.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    for name, identity in (("review--01.json", "reviewer-a"), ("review--02.json", "reviewer-b")):
        audit = gr.make_audit_record(
            packet=packet,
            review_id="review--01",
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="pose",
            rationale="ok",
            reviewer_identity=identity,
            model_identity="composer",
            model_version="2.5",
            timestamp="2026-07-27T00:00:00+00:00",
            second_review_triggers=["metric_at_or_beyond_midpoint"],
        )
        gr.write_audit_record(review_dir / name, audit)
    blinded = gr.blinded_packet_for_second_review(
        packet,
        first_review=first,
        second_review_id="review--02",
        second_reviewer_identity="reviewer-b",
    )
    gr.write_second_review_input(review_dir / "review-input--02.json", blinded)
    with pytest.raises(gr.ReviewError, match="distinct"):
        gr.validate_review_dir(review_dir)


def test_validate_cli_emits_machine_readable_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing-review-dir"
    code = gr.main(["validate", str(missing)])
    assert code == 1
    report = json.loads(capsys.readouterr().out.strip())
    assert report["ok"] is False
    assert "error" in report


def test_written_review_packet_and_audits_validate_fail_closed(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    _write_two_audits(review_dir, packet)
    report = gr.validate_review_dir(review_dir)
    assert report["ok"] is True


def test_validate_review_dir_rehashes_packet_input_roles(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    audits: dict[str, object] = {}
    for review_id, identity in (("review--01", "cursor-agent/issue-54/review-01"),
                                ("review--02", "cursor-agent/issue-54/review-02")):
        audit = gr.make_audit_record(
            packet=packet,
            review_id=review_id,
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="pose transition",
            rationale=f"rationale for {review_id}",
            reviewer_identity=identity,
            model_identity="cursor-grok-4.5",
            model_version="grok-4.5",
            timestamp="2026-07-27T00:00:00+00:00",
            second_review_triggers=["metric_at_or_beyond_midpoint"],
        )
        gr.write_audit_record(review_dir / f"{review_id}.json", audit)
        audits[review_id] = audit
    blinded = gr.blinded_packet_for_second_review(
        packet,
        first_review=audits["review--01"],
        second_review_id="review--02",
        second_reviewer_identity="cursor-agent/issue-54/review-02",
    )
    gr.write_second_review_input(review_dir / "review-input--02.json", blinded)
    report = gr.validate_review_dir(review_dir)
    assert report["ok"] is True
    assert report["roles"] == {
        "candidate": "candidate",
        "budget_binding_good": "budget_binding_good",
        "proposed_hard_fail_reference": "proposed_hard_fail_reference",
    }

    # Tamper binding-good bytes without updating packet → fail closed.
    fx["good_path"].write_bytes(_png(b"tampered-good"))
    with pytest.raises(gr.ReviewError, match="SHA-256 mismatch"):
        gr.validate_review_dir(review_dir)


def test_validate_review_dir_rejects_first_review_leak_into_second(tmp_path: Path) -> None:
    fx = _evidence(tmp_path)
    packet = gr.build_promotion_verification_packet(
        root=fx["root"],
        promotion_id=fx["promo_id"],
        budget_binding_good=fx["good_path"],
    )
    review_dir = fx["gc"] / "reviews" / fx["attempt_id"]
    gr.write_packet_manifest(review_dir / "packet.json", packet)
    first = gr.make_audit_record(
        packet=packet,
        review_id="review--01",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose transition",
        rationale="secret first rationale must not appear in second",
        reviewer_identity="cursor-agent/issue-54/review-01",
        model_identity="cursor-grok-4.5",
        model_version="grok-4.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    gr.write_audit_record(review_dir / "review--01.json", first)
    second = gr.make_audit_record(
        packet=packet,
        review_id="review--02",
        verdict="APPROVE",
        frames=[0, 1],
        observed_feature="pose transition",
        rationale="independent second rationale",
        reviewer_identity="cursor-agent/issue-54/review-02",
        model_identity="cursor-grok-4.5",
        model_version="grok-4.5",
        timestamp="2026-07-27T00:00:00+00:00",
        second_review_triggers=["metric_at_or_beyond_midpoint"],
    )
    gr.write_audit_record(review_dir / "review--02.json", second)
    blinded = gr.blinded_packet_for_second_review(
        packet,
        first_review=first,
        second_review_id="review--02",
        second_reviewer_identity="cursor-agent/issue-54/review-02",
    )
    blinded["packet"]["leak_probe"] = first["rationale"]
    gr.write_second_review_input(review_dir / "review-input--02.json", blinded)
    with pytest.raises(gr.ReviewError, match="leaked prior review"):
        gr.validate_review_dir(review_dir)
