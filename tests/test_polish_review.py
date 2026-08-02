"""Polish Bundle visual-review packet, audit, and validation (issue #235)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from pipeline import polish_review as pr
from pipeline.final_polish import InvalidBundleError, finalize_bundle
from pipeline.gate_evidence import sha256_file
from tests.support import polish_bundle as pb
from tests.support.final_polish_testkit import PASS_STRIP, ROOT, check_bundle, swing_provider_strip
from tests.support.polish_review_fixture import _packet_questions, build_packet, write_passing_reviews, write_review

PACKET_FORBIDDEN_KEYS = frozenset(
    {
        "outcome",
        "pass",
        "fingerprint",
        "structural",
        "gates",
        "coherence",
        "identity_lock",
        "provider_post_edit",
        "delta",
        "visible_edits",
        "completion_matrix",
        "acquiring_agent",
        "acquiring_rationale",
        "verdict",
        "rationale",
        "review_id",
        "reviewer_identity",
        "reviewer_session_id",
        "review_ordinal",
        "answers",
        "packet_kind",
        "gate",
        "metric",
        "budget",
        "hard_fail_boundary",
        "attempt_id",
        "promotion_id",
        "second_review_triggers",
        "observed_feature",
        "candidate_sha256",
        "reference_hashes",
        "caveats",
        "audit",
        "reviews",
    }
)


def _collect_keys(value: object, *, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.add(path)
            keys.update(_collect_keys(nested, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            keys.update(_collect_keys(item, prefix=f"{prefix}[{index}]"))
    return keys


def _init_attested_idle_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path, polish_profile="miner")
    pb.init_bundle(attempt, bundle)
    return bundle


def test_packet_excludes_forbidden_keys(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    keys = _collect_keys(packet)
    forbidden = {key for key in keys if key.split("[", 1)[0].split(".")[-1] in PACKET_FORBIDDEN_KEYS}
    assert forbidden == set()
    assert packet["schema"] == pr.PACKET_SCHEMA
    assert packet["fixed_questions"]
    assert packet["candidate_frames"]
    review_dir = pr.bundle_reviews_dir(bundle)
    assert (review_dir / "packet.json").is_file()
    assert (review_dir / "packet.png").is_file()


def test_valid_two_record_directory(tmp_path: Path) -> None:
    bundle = tmp_path / "swing"
    attempt = pb.prepare(
        swing_provider_strip(tmp_path),
        "swing",
        tmp_path,
        polish_profile="dwarf-miner",
    )
    pb.init_bundle(attempt, bundle)
    write_passing_reviews(bundle)
    report = pr.validate_bundle_review_dir(pr.bundle_reviews_dir(bundle), bundle)
    assert report["ok"] is True
    assert report["required_review_count"] == 2
    assert len(report["record_digests"]) == 2


def test_stale_frame_digest_rejected(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    write_passing_reviews(bundle)
    polished = bundle / "polished" / "frame-0.png"
    polished.write_bytes(polished.read_bytes() + b"x")
    with pytest.raises(pr.PolishReviewError, match="frame digest"):
        pr.validate_bundle_review_dir(pr.bundle_reviews_dir(bundle), bundle)


def test_missing_and_extra_answers_rejected(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    review_dir = pr.bundle_reviews_dir(bundle)
    question_ids = [row["id"] for row in _packet_questions(packet)]
    with pytest.raises(pr.PolishReviewError, match="missing answer"):
        pr.make_audit_record(
            packet=packet,
            reviewer_id="r1",
            reviewer_session_id="s1",
            review_ordinal=1,
            answers=[
                {"question_id": question_ids[0], "verdict": "PASS", "rationale": "ok"},
            ],
        )

    extra_answers = [
        {"question_id": qid, "verdict": "PASS", "rationale": "ok"} for qid in question_ids
    ]
    extra_answers.append({"question_id": "bogus", "verdict": "PASS", "rationale": "ok"})
    with pytest.raises(pr.PolishReviewError, match="extra answer"):
        pr.make_audit_record(
            packet=packet,
            reviewer_id="r1",
            reviewer_session_id="s1",
            review_ordinal=1,
            answers=extra_answers,
        )


def test_duplicate_sessions_and_producer_session_rejected(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    answers = [
        {"question_id": row["id"], "verdict": "PASS", "rationale": "ok"}
        for row in _packet_questions(packet)
    ]
    first = pr.make_audit_record(
        packet=packet,
        reviewer_id="r1",
        reviewer_session_id="shared",
        review_ordinal=1,
        answers=answers,
    )
    second = pr.make_audit_record(
        packet=packet,
        reviewer_id="r2",
        reviewer_session_id="shared",
        review_ordinal=2,
        answers=answers,
    )
    review_dir = pr.bundle_reviews_dir(bundle)
    pr.write_audit_record(review_dir / "review--01.json", first)
    pr.write_audit_record(review_dir / "review--02.json", second)
    with pytest.raises(pr.PolishReviewError, match="duplicate reviewer session"):
        pr.validate_bundle_review_dir(review_dir, bundle)

    prepared = pb.prepare_cell_author("idle", tmp_path / "cell-fixture")
    cell_bundle = tmp_path / "cell-bundle"
    pb.init_cell_bundle(prepared, cell_bundle)
    packet = build_packet(cell_bundle)
    with pytest.raises(pr.PolishReviewError, match="producer session"):
        pr.make_audit_record(
            packet=packet,
            reviewer_id="r1",
            reviewer_session_id=prepared.authoring_session_id,
            review_ordinal=1,
            answers=answers,
            bundle_root=cell_bundle,
        )


def test_immutable_write_refuses_overwrite(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    write_review(bundle, ordinal=1, reviewer_id="r1", reviewer_session_id="s1")
    review_path = pr.bundle_reviews_dir(bundle) / "review--01.json"
    with pytest.raises(pr.PolishReviewError, match="refusing to mutate"):
        pr.write_audit_record(review_path, json.loads(review_path.read_text()))


def test_swing_clean_pass_still_requires_review_two(tmp_path: Path) -> None:
    bundle = tmp_path / "swing"
    attempt = pb.prepare(
        swing_provider_strip(tmp_path),
        "swing",
        tmp_path,
        polish_profile="dwarf-miner",
    )
    pb.init_bundle(attempt, bundle)
    packet = build_packet(bundle)
    assert pr.compute_required_review_count(packet, []) == 2
    first = write_review(bundle, ordinal=1, reviewer_id="r1", reviewer_session_id="s1")
    assert pr.compute_required_review_count(packet, [first]) == 2


def test_idle_no_override_clean_pass_requires_only_review_one(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    assert packet["motion_questions"] == []
    first = write_review(bundle, ordinal=1, reviewer_id="r1", reviewer_session_id="s1")
    assert pr.compute_required_review_count(packet, [first]) == 1
    report = pr.validate_bundle_review_dir(pr.bundle_reviews_dir(bundle), bundle)
    assert report["ok"] is True
    assert report["required_review_count"] == 1


def test_unresolved_review_one_requires_review_two(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    answers = {
        row["id"]: ("UNCERTAIN" if index == 0 else "PASS", "fixture")
        for index, row in enumerate(_packet_questions(packet))
    }
    first = write_review(
        bundle,
        ordinal=1,
        reviewer_id="r1",
        reviewer_session_id="s1",
        answers=answers,
    )
    assert pr.compute_required_review_count(packet, [first]) == 2
    with pytest.raises(pr.PolishReviewError, match="missing second review"):
        pr.validate_bundle_review_dir(pr.bundle_reviews_dir(bundle), bundle)


def test_blinded_second_review_input_hides_review_one(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    answers = {row["id"]: ("EDIT", "needs edit") for row in _packet_questions(packet)}
    first = write_review(
        bundle,
        ordinal=1,
        reviewer_id="r1",
        reviewer_session_id="s1",
        answers=answers,
    )
    blinded = pr.build_blinded_second_review_input(
        packet,
        first_review=first,
        second_review_id="review-02",
        second_reviewer_id="reviewer-b",
    )
    blob = json.dumps(blinded, sort_keys=True)
    assert first["reviewer_id"] not in blob
    assert first["record_sha256"] not in blob
    assert blinded["blinded"] is True
    assert blinded["prior_review_visible"] is False


def test_validate_reviews_json_reports_unresolved_ids(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    packet = build_packet(bundle)
    answers = {row["id"]: ("EDIT", "fix") for row in _packet_questions(packet)}
    write_review(
        bundle,
        ordinal=1,
        reviewer_id="r1",
        reviewer_session_id="s1",
        answers=answers,
    )
    write_review(
        bundle,
        ordinal=2,
        reviewer_id="r2",
        reviewer_session_id="s2",
        answers=answers,
    )
    report = pr.validate_bundle_review_dir(pr.bundle_reviews_dir(bundle), bundle)
    assert report["ok"] is False
    assert report["unresolved_question_ids"]


def test_review_packet_does_not_modify_candidate_frames(tmp_path: Path) -> None:
    bundle = _init_attested_idle_bundle(tmp_path)
    before = {
        path.name: sha256_file(path) for path in sorted((bundle / "polished").glob("*.png"))
    }
    build_packet(bundle)
    after = {
        path.name: sha256_file(path) for path in sorted((bundle / "polished").glob("*.png"))
    }
    assert before == after


def test_no_production_reads_of_reports_audit_json() -> None:
    pipeline_root = ROOT / "pipeline"
    offenders: list[str] = []
    for path in pipeline_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "reports/audit.json" in text or "polish-visual-audit/0" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
