"""Production Gate-control acquisition state machine and CLI (#65).

Drives the locked AFK acquisition loop through validated append-only evidence,
Review packets, retention, and guarded terminal Promotion. The agent supplies
Cursor Image Gen bytes externally; this module never invents a provider client.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import sys
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from pipeline import gate_control as gc
from pipeline import gate_evidence as ge
from pipeline import gate_review as gr
from pipeline import gate_verification as gv

ATTEMPT_SCHEMA = "gate-control-acquisition/0"
PROVENANCE_SCHEMA = "gate-control-provenance/0"
GENERATOR = "cursor-image-gen"
ESCALATION_THRESHOLD = 3

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class AcquisitionError(ValueError):
    """Fail-closed acquisition failure."""


@dataclass(frozen=True)
class AttemptIdentity:
    specification_id: str
    ordinal: int
    attempt_id: str
    predecessor_attempt_id: str | None


Clock = Callable[[], str]


def gate_controls_root(repo_root: pathlib.Path | None = None) -> pathlib.Path:
    root = repo_root or REPO_ROOT
    override = os.environ.get("UNDERLINE_GATE_CONTROLS_ROOT")
    if override:
        return pathlib.Path(override)
    return root / "gate-controls"


def repository_root(repo_root: pathlib.Path | None = None) -> pathlib.Path:
    return gate_controls_root(repo_root).parent


def specification_id(motion_class: str, target_gate: str) -> str:
    return f"{motion_class}/{target_gate}"


def promotion_id_for_spec(spec_id: str) -> str:
    return f"promo--{spec_id.replace('/', '--')}"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _image_dimensions(path: pathlib.Path) -> list[int]:
    from PIL import Image

    with Image.open(path) as image:
        return list(image.size)


def _load_prototype_build_composite() -> Any:
    path = REPO_ROOT / "prototype" / "strip-coherence" / "gate_control.py"
    spec = importlib.util.spec_from_file_location(
        "prototype_gate_control_composite", path
    )
    if spec is None or spec.loader is None:
        raise AcquisitionError(f"cannot load review composite builder from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = getattr(module, "build_composite", None)
    if builder is None:
        raise AcquisitionError("prototype gate_control missing build_composite")
    return builder


def allocate_attempt_identity(
    gc_root: pathlib.Path,
    spec_id: str,
) -> AttemptIdentity:
    """Monotonic Attempt ID allocation under an exclusive repository lock."""
    lock_path = gc_root / ".attempt-alloc.lock"
    attempts_path = gc_root / "attempts.jsonl"
    counters_path = gc_root / ".attempt-counters.json"
    with ge.repository_lock(lock_path):
        ledger_max = 0
        predecessor: str | None = None
        if attempts_path.is_file():
            for line in attempts_path.read_text().splitlines():
                if not line.strip():
                    continue
                doc = json.loads(line)
                if doc.get("specification_id") != spec_id:
                    continue
                row_ordinal = int(doc.get("ordinal", 0))
                if row_ordinal >= ledger_max:
                    ledger_max = row_ordinal
                    predecessor = str(doc["attempt_id"])
        counters: dict[str, int] = {}
        if counters_path.is_file():
            counters = {
                str(key): int(value)
                for key, value in json.loads(counters_path.read_text()).items()
            }
        ordinal = max(ledger_max, counters.get(spec_id, 0)) + 1
        counters[spec_id] = ordinal
        counters_path.write_text(json.dumps(counters, sort_keys=True) + "\n")
        attempt_id = f"{spec_id.replace('/', '--')}--{ordinal:03d}"
        pred = predecessor if ordinal > 1 else None
        return AttemptIdentity(
            specification_id=spec_id,
            ordinal=ordinal,
            attempt_id=attempt_id,
            predecessor_attempt_id=pred,
        )


def gates_requiring_review(run: Mapping[str, Any]) -> list[str]:
    """Gates whose Measurement row is in the Review band."""
    gates: list[str] = []
    for gate, row in (run.get("gates") or {}).items():
        if not isinstance(row, Mapping):
            continue
        if row.get("acceptance_outcome") == "REVIEW":
            gates.append(str(gate))
            continue
        metric = row.get("metric")
        budget = row.get("budget")
        hard_fail = row.get("hard_fail")
        if (
            row.get("outcome") == "fail"
            and isinstance(metric, (int, float))
            and isinstance(budget, (int, float))
            and isinstance(hard_fail, (int, float))
            and hard_fail > budget
            and budget < metric < hard_fail
        ):
            gates.append(str(gate))
    return sorted(gates)


def review_required(
    run: Mapping[str, Any],
    *,
    promotion_verification: bool = False,
) -> bool:
    if promotion_verification:
        return True
    return bool(gates_requiring_review(run))


def decide_artifact_retention(
    run: Mapping[str, Any],
    *,
    ordinal: int,
    unseparated_evidence: bool = False,
    product_decision: bool = False,
) -> str:
    isolation = str(run.get("isolation"))
    if isolation == "ISOLATED":
        return "retained"
    if isolation == "INDETERMINATE" or unseparated_evidence or product_decision:
        return "retained"
    if ordinal <= 3:
        return "retained"
    return "discarded"


def consecutive_primary_reason_streak(
    attempts: Sequence[ge.Attempt],
    spec_id: str,
    reason_code: str,
) -> int:
    streak = 0
    spec_rows = [row for row in attempts if row.specification_id == spec_id]
    for row in reversed(spec_rows):
        primary = row.raw.get("primary_failure")
        if not isinstance(primary, Mapping):
            break
        code = primary.get("code")
        if code == reason_code:
            streak += 1
        else:
            break
    return streak


def acquisition_escalation_required(streak: int) -> bool:
    return streak >= ESCALATION_THRESHOLD


def _measurement_filename(recorded_at: str) -> str:
    return recorded_at.replace(":", "-") + ".json"


def _validate_specification(
    motion_class: str,
    target_gate: str,
    *,
    repo_root: pathlib.Path,
) -> str:
    applicable = gc.applicable_gates(motion_class, repo_root=repo_root)
    if target_gate not in applicable:
        raise gc.SpecificationError(
            f"target gate {target_gate!r} is inapplicable to motion class "
            f"{motion_class!r}; applicable: {', '.join(applicable)}"
        )
    if target_gate in gc.STRUCTURAL_GATES:
        raise gc.SpecificationError(
            f"target gate {target_gate!r} is structural and can never be a target Gate"
        )
    return specification_id(motion_class, target_gate)


def _write_raw_bytes(raw_path: pathlib.Path, png: pathlib.Path) -> str:
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(png, raw_path)
    return ge.sha256_file(raw_path)


def _build_provenance(
    *,
    spec_id: str,
    attempt_id: str,
    prompt_text: str,
    generated_at: str,
    agent: str,
    repository_commit: str,
    raw_rel: str,
    raw_sha256: str,
    dimensions: list[int],
    reference_image_sha256: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": PROVENANCE_SCHEMA,
        "specification_id": spec_id,
        "attempt_id": attempt_id,
        "generator": GENERATOR,
        "prompt_text": prompt_text,
        "prompt_sha256": hashlib.sha256(prompt_text.encode()).hexdigest(),
        "reference_image_sha256": list(reference_image_sha256),
        "generated_at": generated_at,
        "acquiring_agent": agent,
        "repository_commit": repository_commit,
        "raw_path": raw_rel,
        "raw_sha256": raw_sha256,
        "media_type": "image/png",
        "dimensions": dimensions,
    }


def _promotion_blockers(run: Mapping[str, Any]) -> list[str]:
    blockers = list(run.get("blockers") or [])
    if run.get("isolation") != "ISOLATED":
        blockers.append("not ISOLATED")
    return blockers


def _maybe_build_review_composite(
    *,
    raw_path: pathlib.Path,
    run: Mapping[str, Any],
    composite_path: pathlib.Path,
    promotion_verification: bool,
) -> pathlib.Path | None:
    if not run.get("structural", {}).get("recovered"):
        return None
    if not review_required(run, promotion_verification=promotion_verification):
        return None
    build_composite = _load_prototype_build_composite()
    build_composite(raw_path, dict(run), composite_path)
    return composite_path


def _attempt_row(
    *,
    identity: AttemptIdentity,
    recorded_at: str,
    prompt_path: str | None,
    prompt_sha256: str,
    prompt_delta: str | None,
    agent: str,
    artifact_state: str,
    run: Mapping[str, Any],
    measurement_rel: str | None,
    provenance_rel: str,
    composite_rel: str | None,
    raw_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema": ATTEMPT_SCHEMA,
        "attempt_id": identity.attempt_id,
        "specification_id": identity.specification_id,
        "ordinal": identity.ordinal,
        "predecessor_attempt_id": identity.predecessor_attempt_id,
        "recorded_at": recorded_at,
        "prompt_path": prompt_path,
        "prompt_sha256": prompt_sha256,
        "prompt_delta": prompt_delta,
        "acquiring_agent": agent,
        "artifact_state": artifact_state,
        "isolation": run.get("isolation", "INDETERMINATE"),
        "primary_failure": run.get("primary_failure"),
        "promotion_blockers": _promotion_blockers(run),
        "measurement_path": measurement_rel,
        "provenance_path": provenance_rel,
        "composite_path": composite_rel,
        "raw_sha256": raw_sha256,
    }


def record_attempt(
    png: pathlib.Path,
    motion_class: str,
    target_gate: str,
    *,
    repo_root: pathlib.Path | None = None,
    prompt_text: str | None = None,
    prompt_path: pathlib.Path | None = None,
    prompt_delta: str | None = None,
    agent: str = "cursor-agent",
    generated_at: str | None = None,
    reference_image_sha256: Sequence[str] = (),
    unseparated_evidence: bool = False,
    product_decision: bool = False,
    promotion_verification: bool = False,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Measure one candidate and append validated acquisition evidence."""
    root = repository_root(repo_root).resolve()
    gc_root = gate_controls_root(repo_root)
    recorded_at = generated_at or clock()
    repository_commit = gc.git_commit(root)

    try:
        spec_id = _validate_specification(motion_class, target_gate, repo_root=root)
    except gc.SpecificationError as exc:
        raise AcquisitionError(str(exc)) from exc

    if not png.is_file():
        raise AcquisitionError(f"missing candidate PNG: {png}")

    if prompt_text is None:
        prompt_text = prompt_path.read_text() if prompt_path else ""
    prompt_sha = hashlib.sha256(prompt_text.encode()).hexdigest()

    identity = allocate_attempt_identity(gc_root, spec_id)
    raw_rel = f"gate-controls/raw/{identity.attempt_id}.png"
    raw_path = root / raw_rel
    provenance_rel = f"gate-controls/provenance/{identity.attempt_id}.json"
    provenance_path = root / provenance_rel

    raw_sha256 = _write_raw_bytes(raw_path, png)
    dimensions = _image_dimensions(raw_path)
    provenance = _build_provenance(
        spec_id=spec_id,
        attempt_id=identity.attempt_id,
        prompt_text=prompt_text,
        generated_at=recorded_at,
        agent=agent,
        repository_commit=repository_commit,
        raw_rel=raw_rel,
        raw_sha256=raw_sha256,
        dimensions=dimensions,
        reference_image_sha256=reference_image_sha256,
    )
    ge.write_provenance_record(provenance_path, provenance)

    try:
        run = gc.measure(
            raw_path,
            motion_class,
            target_gate,
            attempt_id=identity.attempt_id,
            recorded_at=recorded_at,
            scorer_commit=repository_commit,
            repo_root=root,
        )
    except gc.SpecificationError as exc:
        raise AcquisitionError(str(exc)) from exc

    measurement_rel: str | None = None
    report_dir = gc_root / "reports" / identity.attempt_id
    report_path = report_dir / _measurement_filename(recorded_at)
    gc.persist_measurement_run(report_path, run)
    measurement_rel = str(report_path.relative_to(root))

    composite_rel: str | None = None
    composite_path = gc_root / "reviews" / identity.attempt_id / "composite.png"
    built = _maybe_build_review_composite(
        raw_path=raw_path,
        run=run,
        composite_path=composite_path,
        promotion_verification=promotion_verification,
    )
    if built is not None:
        composite_rel = str(built.relative_to(root))

    artifact_state = decide_artifact_retention(
        run,
        ordinal=identity.ordinal,
        unseparated_evidence=unseparated_evidence,
        product_decision=product_decision,
    )
    if artifact_state == "discarded":
        raw_path.unlink(missing_ok=True)

    row = _attempt_row(
        identity=identity,
        recorded_at=recorded_at,
        prompt_path=str(prompt_path) if prompt_path else None,
        prompt_sha256=prompt_sha,
        prompt_delta=prompt_delta,
        agent=agent,
        artifact_state=artifact_state,
        run=run,
        measurement_rel=measurement_rel,
        provenance_rel=provenance_rel,
        composite_rel=composite_rel,
        raw_sha256=raw_sha256,
    )
    ge.append_attempt_record(gc_root / "attempts.jsonl", row)

    attempts = ge.load_attempts(gc_root / "attempts.jsonl")
    primary = run.get("primary_failure") or {}
    reason_code = primary.get("code") if isinstance(primary, Mapping) else None
    escalation: dict[str, Any] | None = None
    if reason_code:
        streak = consecutive_primary_reason_streak(attempts, spec_id, str(reason_code))
        if acquisition_escalation_required(streak):
            escalation = {
                "motion_class": motion_class,
                "target_gate": target_gate,
                "reason_code": reason_code,
                "consecutive_attempts": streak,
                "message": (
                    "acquisition escalation: three consecutive Attempts failed for "
                    f"{motion_class}/{target_gate} with reason {reason_code}"
                ),
            }

    return {
        **row,
        "measurement": run,
        "retry_action": run.get("retry_action"),
        "gates_in_review": gates_requiring_review(run),
        "review_required": review_required(
            run, promotion_verification=promotion_verification
        ),
        "escalation": escalation,
    }


def _ensure_specification(manifest: dict[str, Any], spec_id: str, motion_class: str, target_gate: str) -> None:
    specs = manifest.setdefault("specifications", [])
    if not any(item.get("id") == spec_id for item in specs):
        specs.append(
            {
                "id": spec_id,
                "motion_class": motion_class,
                "target_gate": target_gate,
            }
        )


def write_pending_promotion(
    root: pathlib.Path,
    *,
    motion_class: str,
    target_gate: str,
    attempt_id: str,
    note: str | None = None,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Write PENDING_VERIFICATION after targeted verification and approved Review."""
    root = root.resolve()
    gc_root = gate_controls_root(root)
    spec_id = specification_id(motion_class, target_gate)
    promo_id = promotion_id_for_spec(spec_id)
    manifest_path = gc_root / "manifest.json"

    graph = ge.validate_evidence_graph(root)
    attempt = graph.attempts.get(attempt_id)
    if attempt is None:
        raise AcquisitionError(f"unknown attempt_id {attempt_id!r}")
    if attempt.artifact_state == "discarded":
        raise AcquisitionError(
            f"discarded attempt {attempt_id} cannot back promotion {promo_id}"
        )
    measurement = graph.measurements.get(attempt_id)
    if measurement is None or measurement.isolation != "ISOLATED":
        raise AcquisitionError(
            f"promotion candidate {attempt_id} is not ISOLATED"
        )

    review_dir = gc_root / "reviews" / attempt_id
    if not (review_dir / "packet.json").is_file():
        raise AcquisitionError(f"missing review packet for attempt {attempt_id}")
    review_report = gr.validate_review_dir(review_dir, root=root)
    if not review_report.get("ok"):
        raise AcquisitionError(
            f"review validation failed for {attempt_id}: {review_report.get('error')}"
        )
    records = [
        ge.load_review(review_dir / name)
        for name in ("review--01.json", "review--02.json")
        if (review_dir / name).is_file()
    ]
    if len(records) < 2 or any(record.verdict != "APPROVE" for record in records):
        raise AcquisitionError(
            f"promotion candidate {attempt_id} lacks two approving reviews"
        )

    measurement_path = attempt.measurement_path
    if measurement_path is None:
        raise AcquisitionError(f"missing measurement_path for attempt {attempt_id}")

    def _mutator(doc: dict[str, Any]) -> dict[str, Any]:
        _ensure_specification(doc, spec_id, motion_class, target_gate)
        promotions = doc.setdefault("promotions", [])
        existing = next((p for p in promotions if p.get("id") == promo_id), None)
        payload = {
            "id": promo_id,
            "specification_id": spec_id,
            "attempt_id": attempt_id,
            "measurement_path": measurement_path,
            "status": gv.PENDING_STATUS,
            "recorded_at": clock(),
            "note": note,
        }
        if existing is None:
            promotions.append(payload)
        else:
            existing.update(payload)
        for spec in doc.get("specifications", []):
            if spec.get("id") == spec_id:
                spec["active_promotion"] = promo_id
        return doc

    manifest = ge.mutate_manifest_document(manifest_path, _mutator)
    ge.validate_evidence_graph(root, promotion_ids=[promo_id])
    promotion = next(p for p in manifest["promotions"] if p["id"] == promo_id)
    return promotion


def complete_promotion_verification(
    root: pathlib.Path,
    promotion_id: str,
    *,
    commands: Sequence[gv.CommandResult] | None = None,
) -> dict[str, Any]:
    """Run full verification and transition Promotion to ACTIVE or INVALIDATED."""
    root = root.resolve()
    gc_root = gate_controls_root(root)
    record = gv.build_verification_record(
        root=root,
        promotion_id=promotion_id,
        commands=list(commands) if commands is not None else gv.run_required_commands(root),
        review_report=gv.validate_promotion_reviews(root, promotion_id),
    )
    out = gc_root / "verification" / f"{promotion_id}.json"
    gv.write_verification_record(out, record)
    ge.mutate_manifest_document(
        gc_root / "manifest.json",
        lambda doc: _apply_promotion_status(doc, promotion_id, str(record["status"])),
    )
    return record


def _apply_promotion_status(
    doc: dict[str, Any], promotion_id: str, status: str
) -> dict[str, Any]:
    for promo in doc.get("promotions", []):
        if promo.get("id") == promotion_id:
            promo["status"] = status
            break
    else:
        raise AcquisitionError(f"manifest missing promotion {promotion_id!r}")
    return doc


def invalidate_stale_active_promotion(
    root: pathlib.Path,
    promotion_id: str,
) -> bool:
    """Invalidate an ACTIVE Promotion when its Measurement is no longer ISOLATED."""
    root = root.resolve()
    gc_root = gate_controls_root(root)
    manifest = ge.load_manifest(gc_root / "manifest.json")
    promotion = next((p for p in manifest.promotions if p.id == promotion_id), None)
    if promotion is None:
        raise AcquisitionError(f"unknown promotion_id {promotion_id!r}")
    if promotion.status != gv.ACTIVE_STATUS:
        return False
    graph = ge.validate_evidence_graph(root, promotion_ids=[promotion_id])
    measurement = graph.measurements[promotion.attempt_id]
    if measurement.isolation == "ISOLATED":
        return False
    ge.mutate_manifest_document(
        gc_root / "manifest.json",
        lambda doc: _apply_promotion_status(doc, promotion_id, gv.INVALIDATED_STATUS),
    )
    return True


def promote_isolated(
    png: pathlib.Path,
    motion_class: str,
    target_gate: str,
    *,
    repo_root: pathlib.Path | None = None,
    prompt_text: str | None = None,
    prompt_path: pathlib.Path | None = None,
    prompt_delta: str | None = None,
    agent: str = "cursor-agent",
    note: str | None = None,
    budget_binding_good: pathlib.Path | None = None,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Record one ISOLATED candidate and register a PENDING_VERIFICATION Promotion."""
    root = repository_root(repo_root).resolve()
    row = record_attempt(
        png,
        motion_class,
        target_gate,
        repo_root=root,
        prompt_text=prompt_text,
        prompt_path=prompt_path,
        prompt_delta=prompt_delta,
        agent=agent,
        promotion_verification=True,
        clock=clock,
    )
    if row["isolation"] != "ISOLATED":
        raise AcquisitionError(
            f"{motion_class}/{target_gate} expected ISOLATED, got {row['isolation']}"
        )
    if budget_binding_good is not None:
        packet = gr.build_review_packet(
            root=root,
            attempt_id=row["attempt_id"],
            gate=target_gate,
            budget_binding_good=budget_binding_good,
            packet_kind="CANDIDATE_REVIEW",
        )
        review_dir = gate_controls_root(root) / "reviews" / row["attempt_id"]
        gr.write_packet_manifest(review_dir / "packet.json", packet)
    review_dir = gate_controls_root(root) / "reviews" / row["attempt_id"]
    if (review_dir / "review--01.json").is_file() and (
        review_dir / "review--02.json"
    ).is_file():
        return write_pending_promotion(
            root,
            motion_class=motion_class,
            target_gate=target_gate,
            attempt_id=row["attempt_id"],
            note=note,
            clock=clock,
        )
    return {
        "attempt_id": row["attempt_id"],
        "isolation": row["isolation"],
        "status": "AWAITING_REVIEW",
        "note": note,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")

    record = sub.add_parser("record", help="Measure one candidate Attempt")
    record.add_argument("png", type=pathlib.Path)
    record.add_argument("--motion-class", required=True)
    record.add_argument("--target-gate", required=True, choices=gc.GATE_ORDER)
    record.add_argument("--prompt", type=pathlib.Path)
    record.add_argument("--prompt-text")
    record.add_argument("--prompt-delta")
    record.add_argument("--agent", default="cursor-agent")
    record.add_argument("--product-decision", action="store_true")
    record.add_argument("--unseparated-evidence", action="store_true")

    promote = sub.add_parser(
        "promote", help="Record an ISOLATED Attempt and write PENDING_VERIFICATION"
    )
    promote.add_argument("png", type=pathlib.Path)
    promote.add_argument("--motion-class", required=True)
    promote.add_argument("--target-gate", required=True, choices=gc.GATE_ORDER)
    promote.add_argument("--prompt", type=pathlib.Path)
    promote.add_argument("--prompt-text")
    promote.add_argument("--prompt-delta")
    promote.add_argument("--agent", default="cursor-agent")
    promote.add_argument("--note")
    promote.add_argument(
        "--budget-binding-good",
        type=pathlib.Path,
        help="Manifest-good reference Strip for the Review packet",
    )

    verify = sub.add_parser("verify", help="Run full Promotion verification")
    verify.add_argument("promotion_id")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2

    try:
        if args.command == "record":
            row = record_attempt(
                args.png,
                args.motion_class,
                args.target_gate,
                prompt_path=args.prompt,
                prompt_text=args.prompt_text,
                prompt_delta=args.prompt_delta,
                agent=args.agent,
                product_decision=args.product_decision,
                unseparated_evidence=args.unseparated_evidence,
            )
            print(json.dumps(row, indent=2, sort_keys=True))
            return 0 if row["isolation"] == "ISOLATED" and row.get("escalation") is None else 1

        if args.command == "promote":
            promo = promote_isolated(
                args.png,
                args.motion_class,
                args.target_gate,
                prompt_path=args.prompt,
                prompt_text=args.prompt_text,
                prompt_delta=args.prompt_delta,
                agent=args.agent,
                note=args.note,
                budget_binding_good=args.budget_binding_good,
            )
            print(json.dumps(promo, indent=2, sort_keys=True))
            return 0

        if args.command == "verify":
            record = complete_promotion_verification(REPO_ROOT, args.promotion_id)
            print(json.dumps(record, indent=2, sort_keys=True))
            return 0 if record["status"] == gv.ACTIVE_STATUS else 1
    except (AcquisitionError, ge.EvidenceError, gr.ReviewError, gv.VerificationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
