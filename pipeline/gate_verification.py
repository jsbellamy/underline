"""Full-repository Promotion verification for Wave A activation.

Validates review-approved Promotion candidates, runs the locked proof commands,
and writes immutable verification records without mutating existing evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline import gate_evidence as ge
from pipeline import gate_review as gr

VERIFICATION_SCHEMA = "gate-control-verification/0"
PENDING_STATUS = "PENDING_VERIFICATION"
ACTIVE_STATUS = "ACTIVE"
INVALIDATED_STATUS = "INVALIDATED"

REQUIRED_COMMANDS: tuple[tuple[str, ...], ...] = (
    ("npm", "test"),
    ("npm", "run", "prototype:strip:corpus"),
    ("npm", "run", "prototype:strip:adversarial"),
    ("npm", "run", "prototype:strip:alpha-budgets"),
)

ISSUE_59_PROMOTION_IDS: frozenset[str] = frozenset(
    {
        "promo--idle--palette_drift_pass",
        "promo--idle--silhouette_budget",
        "promo--blob_idle--loop_closure_pass",
        "promo--blob_idle--min_pair_cohort_pass",
        "promo--blob_idle--palette_drift_pass",
        "promo--blob_idle--silhouette_budget",
    }
)

PROMOTION_REVIEW_DIRS: dict[str, str] = {
    "promo--idle--palette_drift_pass": "idle--palette_drift_pass--001",
    "promo--idle--silhouette_budget": "idle--silhouette_budget--001",
    "promo--blob_idle--loop_closure_pass": "blob_idle--loop_closure_pass--004",
    "promo--blob_idle--min_pair_cohort_pass": "blob_idle--min_pair_cohort_pass--005",
    "promo--blob_idle--palette_drift_pass": "blob_idle--palette_drift_pass--001",
    "promo--blob_idle--silhouette_budget": "blob_idle--silhouette_budget--004",
}


class VerificationError(ValueError):
    """Fail-closed Promotion verification failure."""


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    evidence_row: str


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _command_string(argv: Sequence[str]) -> str:
    return " ".join(argv)


def _extract_evidence_row(command: str, output: str, exit_code: int) -> str:
    lines = [
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.strip().startswith("npm warn")
    ]
    if not lines:
        return f"exit_code={exit_code}"
    if command == "npm test":
        for line in reversed(lines):
            if re.search(r"\d+ passed", line):
                return line
    if command == "npm run prototype:strip:corpus":
        for line in reversed(lines):
            if line.startswith("scored "):
                return line
    if command == "npm run prototype:strip:adversarial":
        for line in reversed(lines):
            if line.startswith("Separated=") or "GAPS" in line:
                return line
    if command == "npm run prototype:strip:alpha-budgets":
        for line in reversed(lines):
            if line.startswith("Separated="):
                return line
    return lines[-1]


def run_required_commands(root: Path) -> list[CommandResult]:
    """Run the four locked proof commands and capture exit codes plus evidence rows."""
    results: list[CommandResult] = []
    for argv in REQUIRED_COMMANDS:
        command = _command_string(argv)
        completed = subprocess.run(
            list(argv),
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        results.append(
            CommandResult(
                command=command,
                exit_code=completed.returncode,
                evidence_row=_extract_evidence_row(command, output, completed.returncode),
            )
        )
    return results


def _manifest_doc_at_binding(
    manifest_path: Path,
    *,
    promotion_ids: frozenset[str],
    status: str = PENDING_STATUS,
) -> dict[str, Any]:
    doc = json.loads(manifest_path.read_text())
    for promo in doc.get("promotions", []):
        pid = promo.get("id")
        if isinstance(pid, str) and pid in promotion_ids:
            promo["status"] = status
    return doc


def manifest_sha256_at_binding(
    manifest_path: Path,
    *,
    promotion_ids: frozenset[str],
    status: str = PENDING_STATUS,
) -> str:
    """Hash the manifest as bound at verification time (named promotions at ``status``)."""
    doc = _manifest_doc_at_binding(
        manifest_path,
        promotion_ids=promotion_ids,
        status=status,
    )
    canonical = json.dumps(doc, indent=2) + "\n"
    return ge.sha256_bytes(canonical.encode())


def review_dir_for_promotion(promotion_id: str) -> str:
    attempt_id = PROMOTION_REVIEW_DIRS.get(promotion_id)
    if attempt_id is None:
        raise VerificationError(f"unknown promotion_id {promotion_id!r}")
    return attempt_id


def ensure_blinded_second_review_input(review_dir: Path) -> None:
    """Mechanically write review-input--02.json when audits exist but input does not."""
    path = review_dir / "review-input--02.json"
    if path.is_file():
        return
    packet_doc = ge.load_json(review_dir / "packet.json")
    packet = gr.review_packet_from_manifest(packet_doc)
    first_review = ge.load_json(review_dir / "review--01.json")
    second_review = ge.load_json(review_dir / "review--02.json")
    blinded = gr.blinded_packet_for_second_review(
        packet,
        first_review=first_review,
        second_review_id=str(second_review["review_id"]),
        second_reviewer_identity=str(second_review["reviewer_identity"]),
    )
    gr.write_second_review_input(path, blinded)


def validate_promotion_reviews(root: Path, promotion_id: str) -> dict[str, Any]:
    """Validate the review graph for one Promotion; require two matching APPROVE audits."""
    attempt_id = review_dir_for_promotion(promotion_id)
    review_dir = root / "gate-controls" / "reviews" / attempt_id
    ensure_blinded_second_review_input(review_dir)
    report = gr.validate_review_dir(review_dir, root=root)
    if not report.get("ok"):
        raise VerificationError(
            f"review validation failed for {promotion_id}: {report.get('error')}"
        )
    records = [
        ge.load_review(review_dir / name)
        for name in ("review--01.json", "review--02.json")
    ]
    verdicts = [record.verdict for record in records]
    if verdicts != ["APPROVE", "APPROVE"]:
        raise VerificationError(
            f"review disagreement for {promotion_id}: verdicts {verdicts!r}"
        )
    return report


def _relative_gc(path: Path, gc_root: Path) -> str:
    return str(path.resolve().relative_to(gc_root.resolve()))


def build_verification_record(
    *,
    root: Path,
    promotion_id: str,
    commands: Sequence[CommandResult],
    review_report: Mapping[str, Any],
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Assemble one immutable verification record for a Promotion candidate."""
    root = root.resolve()
    gc = root / "gate-controls"
    graph = ge.validate_evidence_graph(root, promotion_ids=[promotion_id])
    promo = graph.promotions[promotion_id]
    attempt = graph.attempts[promo.attempt_id]
    measurement = graph.measurements[promo.attempt_id]
    provenance = graph.provenances[promo.attempt_id]

    attempt_id = review_dir_for_promotion(promotion_id)
    review_dir = gc / "reviews" / attempt_id
    packet_path = review_dir / "packet.json"
    packet_doc = ge.load_json(packet_path)
    packet_sha256 = str(packet_doc["packet_sha256"])

    reviews: list[dict[str, str]] = []
    for name in ("review--01.json", "review--02.json"):
        path = review_dir / name
        record = ge.load_review(path)
        reviews.append(
            {
                "review_id": record.review_id,
                "path": _relative_gc(path, gc),
                "sha256": ge.sha256_file(path),
                "verdict": str(record.verdict),
            }
        )

    reviews_ok = all(item["verdict"] == "APPROVE" for item in reviews)
    commands_ok = all(item.exit_code == 0 for item in commands)
    if failure_reason is None and reviews_ok and commands_ok:
        status = ACTIVE_STATUS
        failure_reason = None
    else:
        status = INVALIDATED_STATUS
        if failure_reason is None:
            if not reviews_ok:
                failure_reason = "review_not_approved"
            else:
                failure_reason = "verification_command_failed"

    measurement_path = root / promo.measurement_path
    provenance_path = root / attempt.provenance_path

    return {
        "schema": VERIFICATION_SCHEMA,
        "promotion_id": promotion_id,
        "specification_id": promo.specification_id,
        "attempt_id": promo.attempt_id,
        "measurement_path": promo.measurement_path,
        "measurement_sha256": ge.sha256_file(measurement_path),
        "provenance_path": attempt.provenance_path,
        "provenance_sha256": ge.sha256_file(provenance_path),
        "raw_sha256": provenance.raw_sha256,
        "packet_path": _relative_gc(packet_path, gc),
        "packet_sha256": packet_sha256,
        "reviews": reviews,
        "manifest_sha256": manifest_sha256_at_binding(
            gc / "manifest.json",
            promotion_ids=ISSUE_59_PROMOTION_IDS,
            status=PENDING_STATUS,
        ),
        "repository_commit": _git_commit(root),
        "commands": [
            {
                "command": item.command,
                "exit_code": item.exit_code,
                "evidence_row": item.evidence_row,
            }
            for item in commands
        ],
        "recorded_at": _now(),
        "status": status,
        "failure_reason": failure_reason,
        "review_report": {
            "ok": review_report.get("ok"),
            "packet_sha256": review_report.get("packet_sha256"),
            "reviews": review_report.get("reviews"),
        },
    }


def validate_verification_record(root: Path, path: Path) -> None:
    """Fail closed on schema, identity, hash, and terminal-state mismatches."""
    root = root.resolve()
    gc = root / "gate-controls"
    doc = ge.load_json(path)
    ge.require_schema(doc, ge.KNOWN_SCHEMAS["verification"], where=str(path))

    promotion_id = str(doc["promotion_id"])
    if promotion_id not in ISSUE_59_PROMOTION_IDS:
        raise VerificationError(
            f"verification record promotion_id {promotion_id!r} outside issue #59 scope"
        )

    promo = ge.load_manifest(gc / "manifest.json")
    promotion = next((p for p in promo.promotions if p.id == promotion_id), None)
    if promotion is None:
        raise VerificationError(f"unknown promotion_id {promotion_id!r}")

    for field, expected in (
        ("specification_id", promotion.specification_id),
        ("attempt_id", promotion.attempt_id),
        ("measurement_path", promotion.measurement_path),
    ):
        if doc.get(field) != expected:
            raise VerificationError(
                f"identity mismatch: verification {field} {doc.get(field)!r} "
                f"!= manifest {expected!r}"
            )

    bound_manifest = manifest_sha256_at_binding(
        gc / "manifest.json",
        promotion_ids=ISSUE_59_PROMOTION_IDS,
        status=PENDING_STATUS,
    )
    if doc.get("manifest_sha256") != bound_manifest:
        raise VerificationError(
            f"manifest_sha256 mismatch for {promotion_id}: "
            f"record {doc.get('manifest_sha256')} != bound {bound_manifest}"
        )

    measurement_path = root / str(doc["measurement_path"])
    if ge.sha256_file(measurement_path) != doc.get("measurement_sha256"):
        raise VerificationError(
            f"measurement_sha256 mismatch for promotion {promotion_id}"
        )

    provenance_path = root / str(doc["provenance_path"])
    if ge.sha256_file(provenance_path) != doc.get("provenance_sha256"):
        raise VerificationError(
            f"provenance_sha256 mismatch for promotion {promotion_id}"
        )

    packet_path = gc / str(doc["packet_path"])
    packet_doc = ge.load_json(packet_path)
    if packet_doc.get("packet_sha256") != doc.get("packet_sha256"):
        raise VerificationError(f"packet_sha256 mismatch for promotion {promotion_id}")

    for review in doc.get("reviews", []):
        if not isinstance(review, dict):
            raise VerificationError("invalid reviews entry")
        review_path = gc / str(review["path"])
        if ge.sha256_file(review_path) != review.get("sha256"):
            raise VerificationError(
                f"review sha256 mismatch for {review.get('review_id')}"
            )

    status = doc.get("status")
    reviews_ok = all(
        item.get("verdict") == "APPROVE" for item in doc.get("reviews", [])
    )
    commands_ok = all(
        item.get("exit_code") == 0 for item in doc.get("commands", [])
    )
    if status == ACTIVE_STATUS:
        if not reviews_ok or not commands_ok:
            raise VerificationError(
                f"ACTIVE verification for {promotion_id} lacks approving evidence"
            )
        if promotion.status != ACTIVE_STATUS:
            raise VerificationError(
                f"manifest status for {promotion_id} is {promotion.status!r}, "
                f"expected {ACTIVE_STATUS!r}"
            )
    elif status == INVALIDATED_STATUS:
        if not doc.get("failure_reason"):
            raise VerificationError(
                f"INVALIDATED verification for {promotion_id} missing failure_reason"
            )
    else:
        raise VerificationError(f"invalid verification status {status!r}")

    if status == ACTIVE_STATUS and doc.get("failure_reason") is not None:
        raise VerificationError(
            f"ACTIVE verification for {promotion_id} must not record failure_reason"
        )


def write_verification_record(path: Path, record: Mapping[str, Any]) -> None:
    ge.write_json_immutable(path, record)


def verify_promotion(
    root: Path,
    promotion_id: str,
    *,
    commands: Sequence[CommandResult] | None = None,
) -> dict[str, Any]:
    """Validate reviews and assemble a verification record for one Promotion."""
    if promotion_id not in ISSUE_59_PROMOTION_IDS:
        raise VerificationError(f"promotion {promotion_id!r} is outside issue #59")
    ge.validate_evidence_graph(root, promotion_ids=[promotion_id])
    review_report = validate_promotion_reviews(root, promotion_id)
    command_results = list(commands) if commands is not None else run_required_commands(root)
    return build_verification_record(
        root=root,
        promotion_id=promotion_id,
        commands=command_results,
        review_report=review_report,
    )


def apply_manifest_statuses(
    manifest_path: Path,
    *,
    statuses: Mapping[str, str],
) -> None:
    """Transition named Promotion statuses in one manifest write."""
    doc = json.loads(manifest_path.read_text())
    seen: set[str] = set()
    for promo in doc.get("promotions", []):
        pid = promo.get("id")
        if isinstance(pid, str) and pid in statuses:
            promo["status"] = statuses[pid]
            seen.add(pid)
    missing = set(statuses) - seen
    if missing:
        raise VerificationError(f"manifest missing promotions: {sorted(missing)}")
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run and validate Wave A Promotion verification records."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Verify one Promotion and print its record")
    run.add_argument("promotion_id", choices=sorted(ISSUE_59_PROMOTION_IDS))

    write = sub.add_parser("write", help="Write verification JSON for one Promotion")
    write.add_argument("promotion_id", choices=sorted(ISSUE_59_PROMOTION_IDS))
    write.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: cwd)",
    )

    validate = sub.add_parser("validate", help="Validate verification JSON files")
    validate.add_argument("paths", nargs="+", type=Path)
    validate.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root (default: cwd)",
    )

    ensure = sub.add_parser(
        "ensure-review-input",
        help="Mechanically write missing review-input--02.json for issue #59 reviews",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        record = verify_promotion(Path(".").resolve(), args.promotion_id)
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0 if record["status"] == ACTIVE_STATUS else 1

    if args.command == "write":
        root = args.root.resolve()
        record = verify_promotion(root, args.promotion_id)
        out = root / "gate-controls" / "verification" / f"{args.promotion_id}.json"
        write_verification_record(out, record)
        print(json.dumps({"ok": True, "path": str(out), "status": record["status"]}))
        return 0

    if args.command == "validate":
        root = args.root.resolve()
        exit_code = 0
        for path in args.paths:
            try:
                validate_verification_record(root, path)
                report = {"ok": True, "path": str(path)}
            except (VerificationError, ge.EvidenceError) as exc:
                report = {"ok": False, "path": str(path), "error": str(exc)}
                exit_code = 1
            print(json.dumps(report, sort_keys=True))
        return exit_code

    if args.command == "ensure-review-input":
        root = Path(".").resolve()
        for promotion_id in sorted(ISSUE_59_PROMOTION_IDS):
            attempt_id = review_dir_for_promotion(promotion_id)
            review_dir = root / "gate-controls" / "reviews" / attempt_id
            ensure_blinded_second_review_input(review_dir)
            print(json.dumps({"ok": True, "review_dir": str(review_dir)}))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
