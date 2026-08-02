"""Helpers for Polish Bundle visual-review tests (issue #235)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline import polish_review as pr


def _packet_questions(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(packet.get("fixed_questions", [])) + list(packet.get("motion_questions", []))


def build_packet(bundle: Path, *, review_dir: Path | None = None) -> dict[str, Any]:
    return pr.write_review_packet(bundle, review_dir=review_dir)


def write_review(
    bundle: Path,
    *,
    ordinal: int,
    reviewer_id: str,
    reviewer_session_id: str,
    answers: Mapping[str, tuple[str, str]] | None = None,
    review_dir: Path | None = None,
) -> dict[str, Any]:
    """Write one immutable review record; answers map question_id -> (verdict, rationale)."""
    target = review_dir or pr.bundle_reviews_dir(bundle)
    packet_path = target / "packet.json"
    if not packet_path.is_file():
        build_packet(bundle, review_dir=target)
    packet = pr.review_packet_from_manifest(
        __import__("json").loads(packet_path.read_text(encoding="utf-8"))
    )
    if answers is None:
        answers = {
            question["id"]: ("PASS", "fixture pass") for question in _packet_questions(packet)
        }
    record = pr.make_audit_record(
        packet=packet,
        reviewer_id=reviewer_id,
        reviewer_session_id=reviewer_session_id,
        review_ordinal=ordinal,
        answers=[
            {
                "question_id": question_id,
                "verdict": verdict,
                "rationale": rationale,
            }
            for question_id, (verdict, rationale) in answers.items()
        ],
        bundle_root=bundle,
    )
    path = target / f"review--{ordinal:02d}.json"
    pr.write_audit_record(path, record)
    if ordinal == 1 and pr.compute_required_review_count(packet, [record]) >= 2:
        blinded = pr.build_blinded_second_review_input(
            packet,
            first_review=record,
            second_review_id=f"review-{ordinal + 1:02d}",
            second_reviewer_id=f"{reviewer_id}-2",
        )
        pr.write_second_review_input(target / "review-input--02.json", blinded)
    return record


def write_passing_reviews(
    bundle: Path,
    *,
    review_dir: Path | None = None,
    reviewer_id: str = "reviewer-a",
    reviewer_session_id: str = "review-session-a",
    second_reviewer_id: str = "reviewer-b",
    second_reviewer_session_id: str = "review-session-b",
) -> list[dict[str, Any]]:
    target = review_dir or pr.bundle_reviews_dir(bundle)
    build_packet(bundle, review_dir=target)
    packet = pr.review_packet_from_manifest(
        __import__("json").loads((target / "packet.json").read_text(encoding="utf-8"))
    )
    first = write_review(
        bundle,
        ordinal=1,
        reviewer_id=reviewer_id,
        reviewer_session_id=reviewer_session_id,
        review_dir=target,
    )
    records = [first]
    if pr.compute_required_review_count(packet, records) >= 2:
        records.append(
            write_review(
                bundle,
                ordinal=2,
                reviewer_id=second_reviewer_id,
                reviewer_session_id=second_reviewer_session_id,
                review_dir=target,
            )
        )
    return records
