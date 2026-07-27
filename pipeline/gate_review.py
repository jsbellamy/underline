"""Deterministic Review packets, panel selection, audits, and second-review triggers.

Final packet/audit schemas for Wave A and the production AFK acquisition loop.
Primitives never mutate existing Gate-control evidence or Promotion status.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline import gate_evidence as ge

FIXED_QUESTIONS: dict[str, str] = {
    "silhouette_budget": (
        "Intentional pose transition vs identity drift / framing / translation?"
    ),
    "palette_drift_pass": (
        "Intentional subject/Motion-class change (e.g. emissive flicker) "
        "vs unintended recolour?"
    ),
    "min_pair_cohort_pass": (
        "Same subject, one coherent animation despite no sufficiently similar pair?"
    ),
    "loop_closure_pass": (
        "Final→first reads as deliberate continuous loop vs pose jump / identity break?"
    ),
    "displacement_pass": (
        "Genuine subject motion vs entire Frame translated on the grid?"
    ),
}

PANEL_KIND_FOR_GATE: dict[str, str] = {
    "silhouette_budget": "occupancy_difference",
    "loop_closure_pass": "occupancy_difference",
    "min_pair_cohort_pass": "occupancy_difference",
    "palette_drift_pass": "quantized_palette_histogram",
    "displacement_pass": "best_alignment_vectors",
}

PACKET_SCHEMA = "gate-review-packet/0"
AUDIT_SCHEMA = "gate-review-audit/0"

AUDIT_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema",
    "fixed_question",
    "verdict",
    "frames",
    "observed_feature",
    "metric",
    "budget",
    "hard_fail_boundary",
    "candidate_sha256",
    "reference_hashes",
    "caveats",
    "second_review_triggers",
    "rationale",
    "reviewer_identity",
    "model_identity",
    "model_version",
    "review_id",
    "timestamp",
    "packet_sha256",
)

REJECT_REQUIRED_FIELDS: tuple[str, ...] = (
    "primary_gate",
    "primary_reason_code",
    "retry_intent",
)


class ReviewError(ValueError):
    """Fail-closed Review packet / audit validation failure."""


def panel_kind_for_gate(gate: str) -> str:
    kind = PANEL_KIND_FOR_GATE.get(gate)
    if kind is None:
        raise ReviewError(f"no evidence panel defined for gate {gate!r}")
    return kind


def fixed_question_for_gate(gate: str) -> str:
    question = FIXED_QUESTIONS.get(gate)
    if question is None:
        raise ReviewError(f"no fixed visual question for gate {gate!r}")
    return question


@dataclass(frozen=True)
class PacketReference:
    role: str
    path: str
    raw_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "path": self.path,
            "raw_sha256": self.raw_sha256,
        }


@dataclass(frozen=True)
class ReviewPacket:
    schema: str
    packet_kind: str
    motion_class: str
    gate: str
    panel_kind: str
    fixed_question: str
    attempt_id: str
    promotion_id: str | None
    promotion_status: str | None
    candidate: PacketReference
    budget_binding_good: PacketReference
    gate_control: PacketReference | None
    proposed_hard_fail_reference: PacketReference | None
    no_autonomous_hard_fail: bool
    no_autonomous_hard_fail_reason: str | None
    metric: float | None
    budget: float | None
    hard_fail_boundary: float | None
    caveats: tuple[str, ...]
    packet_sha256: str

    def to_manifest(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "packet_kind": self.packet_kind,
            "motion_class": self.motion_class,
            "gate": self.gate,
            "panel_kind": self.panel_kind,
            "fixed_question": self.fixed_question,
            "attempt_id": self.attempt_id,
            "promotion_id": self.promotion_id,
            "promotion_status": self.promotion_status,
            "candidate": self.candidate.to_dict(),
            "budget_binding_good": self.budget_binding_good.to_dict(),
            "gate_control": (
                None if self.gate_control is None else self.gate_control.to_dict()
            ),
            "proposed_hard_fail_reference": (
                None
                if self.proposed_hard_fail_reference is None
                else self.proposed_hard_fail_reference.to_dict()
            ),
            "no_autonomous_hard_fail": self.no_autonomous_hard_fail,
            "no_autonomous_hard_fail_reason": self.no_autonomous_hard_fail_reason,
            "metric": self.metric,
            "budget": self.budget,
            "hard_fail_boundary": self.hard_fail_boundary,
            "caveats": list(self.caveats),
        }
        # Hash excludes the digest field itself.
        digest = ge.sha256_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        )
        payload["packet_sha256"] = digest
        return payload


def _relpath(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _gate_metric(measurement: ge.MeasurementRun, gate: str) -> float | None:
    entry = measurement.gates.get(gate) or {}
    metric = entry.get("metric")
    return float(metric) if isinstance(metric, (int, float)) else None


def _profile_entry(
    profiles: ge.AcceptanceProfiles, motion_class: str, gate: str
) -> ge.GateProfile:
    class_gates = profiles.profiles.get(motion_class)
    if class_gates is None or gate not in class_gates:
        raise ReviewError(f"missing Acceptance profile for {motion_class}/{gate}")
    return class_gates[gate]


def _reference(root: Path, role: str, path: Path) -> PacketReference:
    if not path.is_file():
        raise ReviewError(f"missing required file for packet role {role}: {path}")
    return PacketReference(
        role=role,
        path=_relpath(root, path),
        raw_sha256=ge.sha256_file(path),
    )


def _finalize(packet: ReviewPacket) -> ReviewPacket:
    manifest = packet.to_manifest()
    return ReviewPacket(
        schema=packet.schema,
        packet_kind=packet.packet_kind,
        motion_class=packet.motion_class,
        gate=packet.gate,
        panel_kind=packet.panel_kind,
        fixed_question=packet.fixed_question,
        attempt_id=packet.attempt_id,
        promotion_id=packet.promotion_id,
        promotion_status=packet.promotion_status,
        candidate=packet.candidate,
        budget_binding_good=packet.budget_binding_good,
        gate_control=packet.gate_control,
        proposed_hard_fail_reference=packet.proposed_hard_fail_reference,
        no_autonomous_hard_fail=packet.no_autonomous_hard_fail,
        no_autonomous_hard_fail_reason=packet.no_autonomous_hard_fail_reason,
        metric=packet.metric,
        budget=packet.budget,
        hard_fail_boundary=packet.hard_fail_boundary,
        caveats=packet.caveats,
        packet_sha256=str(manifest["packet_sha256"]),
    )


def build_review_packet(
    *,
    root: Path,
    attempt_id: str,
    gate: str,
    budget_binding_good: Path,
    packet_kind: str = "CANDIDATE_REVIEW",
    promotion_id: str | None = None,
) -> ReviewPacket:
    """Build a deterministic hash-bound Review packet for one Gate."""
    root = root.resolve()
    focus = [promotion_id] if promotion_id is not None else None
    graph = ge.validate_evidence_graph(root, promotion_ids=focus)
    attempt = graph.attempts.get(attempt_id)
    if attempt is None:
        raise ReviewError(f"unknown attempt_id {attempt_id!r}")

    # Ensure the subject Attempt's Measurement/provenance are loaded even when
    # the call focused on a Promotion that already validated them.
    if attempt_id not in graph.measurements:
        if not attempt.measurement_path:
            raise ReviewError(f"missing Measurement run for attempt {attempt_id}")
        mpath = root / attempt.measurement_path
        if not mpath.is_file():
            raise ReviewError(f"missing Measurement run for attempt {attempt_id}")
        measurements = dict(graph.measurements)
        measurements[attempt_id] = ge.load_measurement(mpath)
    else:
        measurements = dict(graph.measurements)
    measurement = measurements[attempt_id]

    if measurement.target_gate != gate and packet_kind == "PROMOTION_VERIFICATION":
        raise ReviewError(
            f"identity mismatch: measurement target {measurement.target_gate!r} "
            f"!= packet gate {gate!r}"
        )

    if attempt_id not in graph.provenances:
        if not attempt.provenance_path:
            raise ReviewError(f"missing provenance for attempt {attempt_id}")
        ppath = root / attempt.provenance_path
        if not ppath.is_file():
            raise ReviewError(f"missing provenance for attempt {attempt_id}")
        provenances = dict(graph.provenances)
        provenances[attempt_id] = ge.load_provenance(ppath)
    else:
        provenances = dict(graph.provenances)
    provenance = provenances[attempt_id]

    raw_path = root / provenance.raw_path
    if not raw_path.is_file():
        raise ReviewError(f"missing required file for packet role candidate: {raw_path}")
    actual = ge.sha256_file(raw_path)
    if provenance.raw_sha256 != actual or (
        attempt.raw_sha256 is not None and attempt.raw_sha256 != actual
    ):
        raise ReviewError(
            f"SHA-256 mismatch for candidate attempt {attempt_id}: "
            f"raw {actual} vs provenance {provenance.raw_sha256}"
        )
    candidate = _reference(root, "candidate", raw_path)
    binding = _reference(root, "budget_binding_good", Path(budget_binding_good))

    profile = _profile_entry(graph.profiles, measurement.motion_class, gate)
    separated = profile.status == "SEPARATED"
    gate_control: PacketReference | None = None
    no_hard_fail = False
    no_hard_fail_reason: str | None = None
    hard_fail = profile.hard_fail
    promo_status: str | None = None
    proposed: PacketReference | None = None

    if packet_kind == "PROMOTION_VERIFICATION":
        if promotion_id is None:
            raise ReviewError("promotion_id required for PROMOTION_VERIFICATION")
        promo = graph.promotions.get(promotion_id)
        if promo is None:
            raise ReviewError(f"unknown promotion_id {promotion_id!r}")
        if promo.attempt_id != attempt_id:
            raise ReviewError(
                f"identity mismatch: promotion {promotion_id} attempt "
                f"{promo.attempt_id!r} != {attempt_id!r}"
            )
        promo_status = promo.status
        # Pending control candidate is both subject and proposed hard-fail reference.
        proposed = PacketReference(
            role="proposed_hard_fail_reference",
            path=candidate.path,
            raw_sha256=candidate.raw_sha256,
        )
        gate_control = None
        no_hard_fail = False
        no_hard_fail_reason = None
    elif separated:
        control_attempt_id = profile.control_attempt
        if control_attempt_id is None:
            raise ReviewError(
                f"Separated pair {measurement.motion_class}/{gate} missing control_attempt"
            )
        control_prov = provenances.get(control_attempt_id)
        if control_prov is None:
            control_attempt = graph.attempts.get(control_attempt_id)
            if control_attempt is None or not control_attempt.provenance_path:
                raise ReviewError(
                    f"missing provenance for Gate control attempt {control_attempt_id}"
                )
            cpath = root / control_attempt.provenance_path
            if not cpath.is_file():
                raise ReviewError(
                    f"missing provenance for Gate control attempt {control_attempt_id}"
                )
            control_prov = ge.load_provenance(cpath)
        control_raw = root / control_prov.raw_path
        gate_control = _reference(root, "gate_control", control_raw)
        if promotion_id is None and profile.active_promotion:
            promotion_id = profile.active_promotion
        if promotion_id and promotion_id in graph.promotions:
            promo_status = graph.promotions[promotion_id].status
    else:
        no_hard_fail = True
        no_hard_fail_reason = (
            "no autonomous hard-fail reference exists for this Unseparated "
            f"Motion-class/Gate pair ({measurement.motion_class}/{gate})"
        )

    metric = _gate_metric(measurement, gate)
    budget = profile.budget
    if budget is None:
        measured_budget = (measurement.gates.get(gate) or {}).get("budget")
        budget = (
            float(measured_budget)
            if isinstance(measured_budget, (int, float))
            else None
        )

    packet = ReviewPacket(
        schema=PACKET_SCHEMA,
        packet_kind=packet_kind,
        motion_class=measurement.motion_class,
        gate=gate,
        panel_kind=panel_kind_for_gate(gate),
        fixed_question=fixed_question_for_gate(gate),
        attempt_id=attempt_id,
        promotion_id=promotion_id,
        promotion_status=promo_status,
        candidate=candidate,
        budget_binding_good=binding,
        gate_control=gate_control,
        proposed_hard_fail_reference=proposed,
        no_autonomous_hard_fail=no_hard_fail,
        no_autonomous_hard_fail_reason=no_hard_fail_reason,
        metric=metric,
        budget=budget,
        hard_fail_boundary=hard_fail,
        caveats=measurement.caveats,
        packet_sha256="",
    )
    return _finalize(packet)


def build_promotion_verification_packet(
    *,
    root: Path,
    promotion_id: str,
    budget_binding_good: Path,
) -> ReviewPacket:
    root = root.resolve()
    graph = ge.validate_evidence_graph(root, promotion_ids=[promotion_id])
    promo = graph.promotions.get(promotion_id)
    if promo is None:
        raise ReviewError(f"unknown promotion_id {promotion_id!r}")
    spec = graph.specifications.get(promo.specification_id)
    if spec is None:
        raise ReviewError(
            f"broken reference: promotion {promotion_id} specification "
            f"{promo.specification_id!r}"
        )
    return build_review_packet(
        root=root,
        attempt_id=promo.attempt_id,
        gate=spec.target_gate,
        budget_binding_good=budget_binding_good,
        packet_kind="PROMOTION_VERIFICATION",
        promotion_id=promotion_id,
    )


def review_band_midpoint(budget: float, hard_fail_boundary: float) -> float:
    return (budget + hard_fail_boundary) / 2.0


def compute_second_review_triggers(
    *,
    metric: float | None,
    budget: float | None,
    hard_fail_boundary: float | None,
    gates_in_review: int,
    first_verdict: str | None,
    relies_on_caveated_dimension: bool,
) -> list[str]:
    """Locked §10 second-review triggers (deterministic, ordered)."""
    triggers: list[str] = []
    if (
        metric is not None
        and budget is not None
        and hard_fail_boundary is not None
        and hard_fail_boundary > budget
    ):
        midpoint = review_band_midpoint(budget, hard_fail_boundary)
        if metric >= midpoint:
            triggers.append("metric_at_or_beyond_midpoint")
    if gates_in_review >= 2:
        triggers.append("multiple_gates_in_review")
    if first_verdict == "UNCERTAIN":
        triggers.append("first_verdict_uncertain")
    if relies_on_caveated_dimension:
        triggers.append("caveat_reliance")
    return triggers


def promotion_verification_requires_second_review(packet: ReviewPacket) -> bool:
    """Promotion verification always requires two reviews: candidate is at C."""
    triggers = compute_second_review_triggers(
        metric=packet.metric,
        budget=packet.budget,
        hard_fail_boundary=packet.hard_fail_boundary,
        gates_in_review=1,
        first_verdict=None,
        relies_on_caveated_dimension=False,
    )
    return "metric_at_or_beyond_midpoint" in triggers


def make_audit_record(
    *,
    packet: ReviewPacket,
    review_id: str,
    verdict: str,
    frames: Sequence[int],
    observed_feature: str,
    rationale: str,
    reviewer_identity: str,
    model_identity: str,
    model_version: str,
    timestamp: str,
    second_review_triggers: Sequence[str] | None = None,
    caveats: Sequence[str] | None = None,
    primary_gate: str | None = None,
    primary_reason_code: str | None = None,
    retry_intent: str | None = None,
) -> dict[str, Any]:
    if second_review_triggers is None:
        second_review_triggers = compute_second_review_triggers(
            metric=packet.metric,
            budget=packet.budget,
            hard_fail_boundary=packet.hard_fail_boundary,
            gates_in_review=1,
            first_verdict=None,
            relies_on_caveated_dimension=False,
        )
    reference_hashes = {
        "budget_binding_good": packet.budget_binding_good.raw_sha256,
    }
    if packet.gate_control is not None:
        reference_hashes["gate_control"] = packet.gate_control.raw_sha256
    if packet.proposed_hard_fail_reference is not None:
        reference_hashes["proposed_hard_fail_reference"] = (
            packet.proposed_hard_fail_reference.raw_sha256
        )
    record: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "fixed_question": packet.fixed_question,
        "verdict": verdict,
        "frames": list(frames),
        "observed_feature": observed_feature,
        "metric": packet.metric,
        "budget": packet.budget,
        "hard_fail_boundary": packet.hard_fail_boundary,
        "candidate_sha256": packet.candidate.raw_sha256,
        "reference_hashes": reference_hashes,
        "caveats": list(caveats if caveats is not None else packet.caveats),
        "second_review_triggers": list(second_review_triggers),
        "rationale": rationale,
        "reviewer_identity": reviewer_identity,
        "model_identity": model_identity,
        "model_version": model_version,
        "review_id": review_id,
        "timestamp": timestamp,
        "packet_sha256": packet.packet_sha256,
        "gate": packet.gate,
        "attempt_id": packet.attempt_id,
        "promotion_id": packet.promotion_id,
    }
    if verdict == "REJECT":
        record["primary_gate"] = primary_gate
        record["primary_reason_code"] = primary_reason_code
        record["retry_intent"] = retry_intent
    validate_audit_record(record)
    return record


def validate_audit_record(record: Mapping[str, Any]) -> None:
    schema = record.get("schema")
    if schema not in ge.KNOWN_SCHEMAS["review"]:
        raise ReviewError(f"unknown schema {schema!r} for audit record")
    for field in AUDIT_REQUIRED_FIELDS:
        if field not in record:
            raise ReviewError(f"missing audit field: {field}")
    verdict = record.get("verdict")
    if verdict not in {"APPROVE", "REJECT", "UNCERTAIN"}:
        raise ReviewError(f"invalid verdict {verdict!r}")
    if verdict == "REJECT":
        for field in REJECT_REQUIRED_FIELDS:
            if field not in record or record[field] in (None, ""):
                raise ReviewError(f"missing audit field: {field}")


def write_audit_record(path: Path, record: Mapping[str, Any]) -> None:
    validate_audit_record(record)
    ge.write_json_immutable(path, record)


def write_packet_manifest(path: Path, packet: ReviewPacket) -> None:
    ge.write_json_immutable(path, packet.to_manifest())


def blinded_packet_for_second_review(
    packet: ReviewPacket,
    *,
    first_review: Mapping[str, Any],
    second_review_id: str,
    second_reviewer_identity: str,
) -> dict[str, Any]:
    """Serialize the same packet for a fresh review without first-review leakage."""
    if second_review_id == first_review.get("review_id"):
        raise ReviewError("second review identity must be distinct")
    if second_reviewer_identity == first_review.get("reviewer_identity"):
        raise ReviewError("second review identity must be distinct")
    payload = {
        "schema": PACKET_SCHEMA,
        "review_id": second_review_id,
        "reviewer_identity": second_reviewer_identity,
        "packet": packet.to_manifest(),
        "packet_sha256": packet.packet_sha256,
        "blinded": True,
        "prior_review_visible": False,
    }
    blob = json.dumps(payload, sort_keys=True)
    for leak in (
        str(first_review.get("verdict", "")),
        str(first_review.get("rationale", "")),
        str(first_review.get("review_id", "")),
    ):
        if leak and leak in blob:
            raise ReviewError("blinded second-review serialization leaked prior review")
    return payload


def validate_review_dir(review_dir: Path) -> dict[str, Any]:
    """Validate a review directory's packet manifest and audit records."""
    review_dir = review_dir.resolve()
    if not review_dir.is_dir():
        raise ReviewError(f"missing review directory: {review_dir}")
    packet_path = review_dir / "packet.json"
    packet_doc = ge.load_json(packet_path)
    ge.require_schema(packet_doc, ge.KNOWN_SCHEMAS["packet"], where=str(packet_path))
    expected_hash = packet_doc.get("packet_sha256")
    recomputed = dict(packet_doc)
    recomputed.pop("packet_sha256", None)
    digest = ge.sha256_bytes(
        json.dumps(recomputed, sort_keys=True, separators=(",", ":")).encode()
    )
    if expected_hash != digest:
        raise ReviewError(
            f"SHA-256 mismatch: packet manifest hash {expected_hash} != {digest}"
        )

    reviews: list[str] = []
    identities: set[str] = set()
    for path in sorted(review_dir.glob("review--*.json")):
        record = ge.load_review(path)
        validate_audit_record(record.raw)
        if record.packet_sha256 != expected_hash:
            raise ReviewError(
                f"SHA-256 mismatch: audit {path.name} packet hash "
                f"{record.packet_sha256} != {expected_hash}"
            )
        reviews.append(record.review_id)
        identity = str(record.raw.get("reviewer_identity"))
        if identity in identities:
            raise ReviewError("second review identity must be distinct")
        identities.add(identity)

    return {
        "ok": True,
        "review_dir": str(review_dir),
        "packet_sha256": expected_hash,
        "reviews": reviews,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Gate-review packets and immutable audit records."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate one or more review directories")
    validate.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="Review directories containing packet.json and review--*.json",
    )
    args = parser.parse_args(argv)

    if args.command == "validate":
        reports = []
        for path in args.paths:
            report = validate_review_dir(path)
            reports.append(report)
            print(json.dumps(report, sort_keys=True))
        return 0 if all(r["ok"] for r in reports) else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
