"""Bundle-native Polish visual review packets, audits, and validation (issue #235)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image

from pipeline import canonical
from pipeline.final_polish import (
    CELL_AUTHOR_GENERATION_MODE,
    CELL_AUTHOR_PROVENANCE_SCHEMA,
    EXPECTED_FRAME_NAMES,
    InvalidBundleError,
    _frame_dir,
    _is_cell_authored_manifest,
    _load_bound_profile,
    _load_manifest,
    load_polish_brief,
)
from pipeline.gate_evidence import EvidenceError, sha256_file, write_json_immutable

PACKET_SCHEMA = "polish-review-packet/0"
AUDIT_SCHEMA = "polish-review-audit/0"
POLISH_REVIEW_VERDICTS = frozenset({"PASS", "EDIT", "UNCERTAIN"})
PACKET_DIGEST_FIELD = "packet_sha256"
RECORD_DIGEST_FIELD = "record_sha256"
ENLARGEMENT_SCALE = 4


class PolishReviewError(ValueError):
    """Fail-closed Polish review packet / audit validation failure."""


@dataclass(frozen=True)
class ReviewPacket:
    schema: str
    motion_class: str
    profile_id: str
    profile_sha256: str
    fixed_questions: tuple[dict[str, str], ...]
    motion_questions: tuple[dict[str, str], ...]
    candidate_frames: tuple[dict[str, Any], ...]
    identity_reference: dict[str, str] | None
    origin_evidence: dict[str, Any]
    packet_sha256: str

    @property
    def questions(self) -> tuple[dict[str, str], ...]:
        return self.fixed_questions + self.motion_questions

    def to_manifest(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "motion_class": self.motion_class,
            "profile": {
                "id": self.profile_id,
                "sha256": self.profile_sha256,
            },
            "fixed_questions": [dict(row) for row in self.fixed_questions],
            "motion_questions": [dict(row) for row in self.motion_questions],
            "candidate_frames": [dict(row) for row in self.candidate_frames],
            "identity_reference": (
                None if self.identity_reference is None else dict(self.identity_reference)
            ),
            "origin_evidence": dict(self.origin_evidence),
            "digests": {
                "profile_sha256": self.profile_sha256,
                "frame_sha256": [row["sha256"] for row in self.candidate_frames],
                "identity_sha256": (
                    None
                    if self.identity_reference is None
                    else self.identity_reference["sha256"]
                ),
                "origin_evidence_sha256": self.origin_evidence["sha256"],
            },
        }
        payload[PACKET_DIGEST_FIELD] = canonical.self_excluding_digest(
            payload,
            field=PACKET_DIGEST_FIELD,
        )
        return payload


def bundle_reviews_dir(bundle_root: Path) -> Path:
    return bundle_root / "reviews"


def bundle_requires_visual_review(attestation_state: str | None) -> bool:
    return attestation_state != "legacy"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _binding_sha256(binding: Mapping[str, Any]) -> str:
    return str(binding["sha256"])


def _question_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], ...]:
    return tuple({"id": str(row["id"]), "question": str(row["question"])} for row in rows)


def _origin_evidence(bundle_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    if _is_cell_authored_manifest(manifest):
        authoring = manifest["cell_authoring"]
        base_frames = tuple(
            {
                "index": int(row["index"]),
                "relative_path": str(row["relative_path"]),
                "sha256": str(row["sha256"]),
            }
            for row in authoring["base_release_frames"]
        )
        payload = {
            "kind": CELL_AUTHOR_GENERATION_MODE,
            "base_specification_id": str(authoring["base_specification_id"]),
            "base_frame_mapping": list(authoring["base_frame_mapping"]),
            "base_frames": list(base_frames),
        }
        digest = canonical.self_excluding_digest({"origin": payload}, field="digest")
        return {"kind": CELL_AUTHOR_GENERATION_MODE, **payload, "sha256": digest}

    provider_binding = manifest["provider"]
    frames: list[dict[str, Any]] = [
        {
            "role": "provider",
            "relative_path": str(provider_binding["relative_path"]),
            "sha256": str(provider_binding["sha256"]),
        }
    ]
    edit_binding = manifest.get("edit_source")
    if isinstance(edit_binding, Mapping):
        frames.append(
            {
                "role": "edit_source",
                "relative_path": str(edit_binding["relative_path"]),
                "sha256": str(edit_binding["sha256"]),
            }
        )
    payload = {
        "kind": str(manifest.get("generation_mode") or "provider"),
        "frames": frames,
    }
    digest = canonical.self_excluding_digest({"origin": payload}, field="digest")
    return {"kind": payload["kind"], "frames": frames, "sha256": digest}


def _candidate_frames(bundle_root: Path) -> tuple[dict[str, Any], ...]:
    polished = _frame_dir(bundle_root, "polished")
    rows: list[dict[str, Any]] = []
    for index, name in enumerate(EXPECTED_FRAME_NAMES):
        path = polished / name
        if not path.is_file():
            raise PolishReviewError(f"missing polished candidate frame: {path}")
        rows.append(
            {
                "index": index,
                "relative_path": f"polished/{name}",
                "sha256": sha256_file(path),
            }
        )
    return tuple(rows)


def _identity_reference(bundle_root: Path, manifest: Mapping[str, Any]) -> dict[str, str] | None:
    binding = manifest.get("identity_reference")
    if not isinstance(binding, Mapping):
        return None
    relative_path = str(binding["relative_path"])
    digest = str(binding["sha256"])
    path = bundle_root / relative_path
    if not path.is_file():
        raise PolishReviewError(f"missing identity reference: {path}")
    actual = sha256_file(path)
    if actual != digest:
        raise PolishReviewError(
            f"identity reference digest mismatch: manifest {digest} != file {actual}"
        )
    return {"relative_path": relative_path, "sha256": digest}


def _producer_session_id(bundle_root: Path, manifest: Mapping[str, Any]) -> str | None:
    if not _is_cell_authored_manifest(manifest):
        return None
    provenance_binding = manifest["cell_authoring"]["provenance"]
    provenance_path = bundle_root / str(provenance_binding["relative_path"])
    record = _load_json(provenance_path)
    if record.get("schema") != CELL_AUTHOR_PROVENANCE_SCHEMA:
        raise PolishReviewError("cell-author provenance schema mismatch")
    session_id = record.get("authoring_session_id")
    if not isinstance(session_id, str) or not session_id:
        raise PolishReviewError("cell-author provenance missing authoring_session_id")
    return session_id


def build_review_packet(bundle_root: Path) -> ReviewPacket:
    bundle_root = bundle_root.resolve()
    manifest = _load_manifest(bundle_root)
    profile = _load_bound_profile(bundle_root, manifest)
    if profile is None:
        raise PolishReviewError("bundle has no embedded Polish profile")
    brief = load_polish_brief(bundle_root)
    profile_binding = manifest["polish_profile"]
    packet = ReviewPacket(
        schema=PACKET_SCHEMA,
        motion_class=str(manifest["motion_class"]),
        profile_id=str(profile["id"]),
        profile_sha256=str(profile_binding["sha256"]),
        fixed_questions=_question_rows(brief["fixed_questions"]),
        motion_questions=_question_rows(brief["motion_questions"]),
        candidate_frames=_candidate_frames(bundle_root),
        identity_reference=_identity_reference(bundle_root, manifest),
        origin_evidence=_origin_evidence(bundle_root, manifest),
        packet_sha256="",
    )
    manifest_doc = packet.to_manifest()
    return ReviewPacket(
        schema=packet.schema,
        motion_class=packet.motion_class,
        profile_id=packet.profile_id,
        profile_sha256=packet.profile_sha256,
        fixed_questions=packet.fixed_questions,
        motion_questions=packet.motion_questions,
        candidate_frames=packet.candidate_frames,
        identity_reference=packet.identity_reference,
        origin_evidence=packet.origin_evidence,
        packet_sha256=str(manifest_doc[PACKET_DIGEST_FIELD]),
    )


def review_packet_from_manifest(doc: Mapping[str, Any]) -> dict[str, Any]:
    schema = doc.get("schema")
    if schema != PACKET_SCHEMA:
        raise PolishReviewError(f"unknown packet schema {schema!r}")
    digest = canonical.self_excluding_digest(doc, field=PACKET_DIGEST_FIELD)
    if digest != doc.get(PACKET_DIGEST_FIELD):
        raise PolishReviewError("packet manifest hash does not match recomputed digest")
    return dict(doc)


def _paste_strip(image: Image.Image, frame_paths: Sequence[Path], *, scale: int, y: int) -> int:
    if not frame_paths:
        return y
    with Image.open(frame_paths[0]) as first:
        frame_w, frame_h = first.size
    strip_w = len(frame_paths) * frame_w * scale + max(0, len(frame_paths) - 1)
    x = 0
    for path in frame_paths:
        with Image.open(path) as frame:
            rgba = frame.convert("RGBA")
            if scale == 1:
                panel = rgba
            else:
                panel = rgba.resize(
                    (frame_w * scale, frame_h * scale),
                    Image.NEAREST,
                )
            image.paste(panel, (x, y), panel)
            x += frame_w * scale + 1
    return y + frame_h * scale + 8


def _render_packet_png(bundle_root: Path, packet: ReviewPacket, out_path: Path) -> None:
    polished_paths = [
        bundle_root / str(row["relative_path"]) for row in packet.candidate_frames
    ]
    panels: list[tuple[str, Sequence[Path], int]] = [
        ("candidate-native", polished_paths, 1),
        ("candidate-enlarged", polished_paths, ENLARGEMENT_SCALE),
    ]
    if packet.identity_reference is not None:
        panels.append(
            (
                "identity-reference",
                [bundle_root / packet.identity_reference["relative_path"]],
                ENLARGEMENT_SCALE,
            )
        )
    origin = packet.origin_evidence
    if origin.get("kind") == CELL_AUTHOR_GENERATION_MODE:
        base_paths = [
            bundle_root / str(row["relative_path"]) for row in origin["base_frames"]
        ]
        panels.append(("origin-base-frames", base_paths, ENLARGEMENT_SCALE))
    else:
        origin_paths = [
            bundle_root / str(row["relative_path"]) for row in origin.get("frames", [])
        ]
        if origin_paths:
            panels.append(("origin-evidence", origin_paths, ENLARGEMENT_SCALE))

    max_width = 0
    total_height = 8
    for _, paths, scale in panels:
        with Image.open(paths[0]) as first:
            frame_w, frame_h = first.size
        width = len(paths) * frame_w * scale + max(0, len(paths) - 1)
        max_width = max(max_width, width)
        total_height += frame_h * scale + 8

    image = Image.new("RGBA", (max_width, total_height), (0, 0, 0, 0))
    y = 4
    for _, paths, scale in panels:
        y = _paste_strip(image, paths, scale=scale, y=y)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", compress_level=6)


def write_review_packet(
    bundle_root: Path,
    *,
    review_dir: Path | None = None,
) -> dict[str, Any]:
    packet = build_review_packet(bundle_root)
    target = review_dir or bundle_reviews_dir(bundle_root)
    target.mkdir(parents=True, exist_ok=True)
    manifest = packet.to_manifest()
    manifest_path = target / "packet.json"
    if manifest_path.exists():
        existing = _load_json(manifest_path)
        if canonical.self_excluding_digest(existing, field=PACKET_DIGEST_FIELD) != manifest[
            PACKET_DIGEST_FIELD
        ]:
            raise PolishReviewError("refusing to mutate existing packet manifest")
    else:
        write_json_immutable(manifest_path, manifest)
    png_path = target / "packet.png"
    if not png_path.exists():
        _render_packet_png(bundle_root, packet, png_path)
    return manifest


def compute_required_review_count(
    packet: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
) -> int:
    motion_questions = packet.get("motion_questions") or []
    if motion_questions:
        return 2
    if not reviews:
        return 1
    first = reviews[0]
    for answer in first.get("answers", []):
        if answer.get("verdict") in {"EDIT", "UNCERTAIN"}:
            return 2
    return 1


def _expected_question_ids(packet: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("fixed_questions", "motion_questions"):
        for row in packet.get(key, []):
            ids.append(str(row["id"]))
    return ids


def _answer_map(record: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    answers = record.get("answers")
    if not isinstance(answers, list):
        raise PolishReviewError("audit answers must be an array")
    mapped: dict[str, Mapping[str, Any]] = {}
    for row in answers:
        if not isinstance(row, Mapping):
            raise PolishReviewError("audit answer must be an object")
        question_id = row.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise PolishReviewError("audit answer missing question_id")
        if question_id in mapped:
            raise PolishReviewError(f"duplicate answer for question {question_id!r}")
        mapped[question_id] = row
    return mapped


def validate_audit_record(
    record: Mapping[str, Any],
    *,
    packet: Mapping[str, Any],
    require_digest: bool = True,
) -> None:
    if record.get("schema") != AUDIT_SCHEMA:
        raise PolishReviewError(f"unknown audit schema {record.get('schema')!r}")
    for field in (
        PACKET_DIGEST_FIELD,
        "candidate_frame_digests",
        "profile_sha256",
        "reviewer_id",
        "reviewer_session_id",
        "review_ordinal",
        "answers",
    ):
        if field not in record:
            raise PolishReviewError(f"missing audit field: {field}")
    if require_digest and RECORD_DIGEST_FIELD not in record:
        raise PolishReviewError(f"missing audit field: {RECORD_DIGEST_FIELD}")
    if record[PACKET_DIGEST_FIELD] != packet[PACKET_DIGEST_FIELD]:
        raise PolishReviewError("audit packet digest is stale")
    expected_frames = packet["digests"]["frame_sha256"]
    if list(record["candidate_frame_digests"]) != list(expected_frames):
        raise PolishReviewError("audit frame digest is stale")
    if record["profile_sha256"] != packet["digests"]["profile_sha256"]:
        raise PolishReviewError("audit profile digest is stale")
    if require_digest:
        digest = canonical.self_excluding_digest(record, field=RECORD_DIGEST_FIELD)
        if digest != record[RECORD_DIGEST_FIELD]:
            raise PolishReviewError("audit record hash does not match recomputed digest")
    expected_ids = _expected_question_ids(packet)
    answers = _answer_map(record)
    if set(answers) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(answers))
        extra = sorted(set(answers) - set(expected_ids))
        if missing:
            raise PolishReviewError(f"missing answer for question {missing[0]!r}")
        if extra:
            raise PolishReviewError(f"extra answer for question {extra[0]!r}")
    for answer in answers.values():
        verdict = answer.get("verdict")
        if verdict not in POLISH_REVIEW_VERDICTS:
            raise PolishReviewError(f"invalid verdict {verdict!r}")
        rationale = answer.get("rationale")
        if not isinstance(rationale, str) or not rationale:
            raise PolishReviewError("audit answer missing rationale")


def make_audit_record(
    *,
    packet: Mapping[str, Any],
    reviewer_id: str,
    reviewer_session_id: str,
    review_ordinal: int,
    answers: Sequence[Mapping[str, Any]],
    bundle_root: Path | None = None,
) -> dict[str, Any]:
    if bundle_root is not None:
        manifest = _load_manifest(bundle_root)
        producer_session = _producer_session_id(bundle_root, manifest)
        if producer_session is not None and reviewer_session_id == producer_session:
            raise PolishReviewError("reviewer session must not reuse producer session")
    record: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        PACKET_DIGEST_FIELD: packet[PACKET_DIGEST_FIELD],
        "candidate_frame_digests": list(packet["digests"]["frame_sha256"]),
        "profile_sha256": packet["digests"]["profile_sha256"],
        "reviewer_id": reviewer_id,
        "reviewer_session_id": reviewer_session_id,
        "review_ordinal": review_ordinal,
        "answers": [dict(row) for row in answers],
    }
    validate_audit_record(record, packet=packet, require_digest=False)
    record[RECORD_DIGEST_FIELD] = canonical.self_excluding_digest(
        record,
        field=RECORD_DIGEST_FIELD,
    )
    return record


def write_audit_record(path: Path, record: Mapping[str, Any]) -> None:
    try:
        write_json_immutable(path, record)
    except EvidenceError as exc:
        raise PolishReviewError(str(exc)) from exc


def write_second_review_input(path: Path, payload: Mapping[str, Any]) -> None:
    if not payload.get("blinded") or payload.get("prior_review_visible") is not False:
        raise PolishReviewError("second-review input must be blinded with prior review hidden")
    try:
        write_json_immutable(path, payload)
    except EvidenceError as exc:
        raise PolishReviewError(str(exc)) from exc


def build_blinded_second_review_input(
    packet: Mapping[str, Any],
    *,
    first_review: Mapping[str, Any],
    second_review_id: str,
    second_reviewer_id: str,
) -> dict[str, Any]:
    if second_review_id == first_review.get("reviewer_id"):
        raise PolishReviewError("second review identity must be distinct")
    if second_reviewer_id == first_review.get("reviewer_id"):
        raise PolishReviewError("second review identity must be distinct")
    payload = {
        "schema": PACKET_SCHEMA,
        "review_id": second_review_id,
        "reviewer_id": second_reviewer_id,
        PACKET_DIGEST_FIELD: packet[PACKET_DIGEST_FIELD],
        "questions": list(packet.get("fixed_questions", []))
        + list(packet.get("motion_questions", [])),
        "blinded": True,
        "prior_review_visible": False,
    }
    leak_blob = json.dumps(
        {
            "questions": payload["questions"],
            PACKET_DIGEST_FIELD: payload[PACKET_DIGEST_FIELD],
        },
        sort_keys=True,
    )
    for leak in (
        str(first_review.get("reviewer_id", "")),
        str(first_review.get("reviewer_session_id", "")),
        str(first_review.get(RECORD_DIGEST_FIELD, "")),
    ):
        if leak and leak in leak_blob:
            raise PolishReviewError("blinded second-review serialization leaked prior review")
    return payload


def _verify_packet_files(bundle_root: Path, packet: Mapping[str, Any]) -> None:
    for row in packet["candidate_frames"]:
        path = bundle_root / str(row["relative_path"])
        actual = sha256_file(path)
        if actual != row["sha256"]:
            raise PolishReviewError(
                f"frame digest mismatch for {row['relative_path']}: "
                f"packet {row['sha256']} != file {actual}"
            )
    identity = packet.get("identity_reference")
    if isinstance(identity, Mapping):
        path = bundle_root / str(identity["relative_path"])
        actual = sha256_file(path)
        if actual != identity["sha256"]:
            raise PolishReviewError("identity reference digest mismatch")
    origin = packet["origin_evidence"]
    if origin.get("kind") == CELL_AUTHOR_GENERATION_MODE:
        for row in origin["base_frames"]:
            path = bundle_root / str(row["relative_path"])
            actual = sha256_file(path)
            if actual != row["sha256"]:
                raise PolishReviewError("origin base frame digest mismatch")
    else:
        for row in origin.get("frames", []):
            path = bundle_root / str(row["relative_path"])
            actual = sha256_file(path)
            if actual != row["sha256"]:
                raise PolishReviewError("origin evidence digest mismatch")


def _load_review_records(review_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(review_dir.glob("review--*.json")):
        records.append(_load_json(path))
    return records


def _unresolved_question_ids(reviews: Sequence[Mapping[str, Any]]) -> list[str]:
    unresolved: set[str] = set()
    for record in reviews:
        for answer in record.get("answers", []):
            if answer.get("verdict") in {"EDIT", "UNCERTAIN"}:
                unresolved.add(str(answer["question_id"]))
    return sorted(unresolved)


def validate_bundle_review_dir(
    review_dir: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    review_dir = review_dir.resolve()
    bundle_root = bundle_root.resolve()
    if not review_dir.is_dir():
        raise PolishReviewError(f"missing review directory: {review_dir}")
    packet_path = review_dir / "packet.json"
    if not packet_path.is_file():
        raise PolishReviewError("missing packet manifest")
    packet = review_packet_from_manifest(_load_json(packet_path))
    _verify_packet_files(bundle_root, packet)
    manifest = _load_manifest(bundle_root)
    producer_session = _producer_session_id(bundle_root, manifest)

    records = _load_review_records(review_dir)
    if not records:
        raise PolishReviewError("missing review records")

    ordinals: set[int] = set()
    sessions: set[str] = set()
    record_digests: list[str] = []
    for record in records:
        validate_audit_record(record, packet=packet)
        ordinal = int(record["review_ordinal"])
        if ordinal in ordinals:
            raise PolishReviewError("duplicate review ordinal")
        ordinals.add(ordinal)
        session = str(record["reviewer_session_id"])
        if session in sessions:
            raise PolishReviewError("duplicate reviewer session")
        if producer_session is not None and session == producer_session:
            raise PolishReviewError("reviewer session must not reuse producer session")
        sessions.add(session)
        record_digests.append(str(record[RECORD_DIGEST_FIELD]))

    required = compute_required_review_count(packet, records)
    if len(records) < required:
        if required >= 2:
            raise PolishReviewError("missing second review")
        raise PolishReviewError("missing review records")

    if len(records) >= 2:
        blinded_path = review_dir / "review-input--02.json"
        if not blinded_path.is_file():
            raise PolishReviewError("missing blinded second-review input record")
        blinded = _load_json(blinded_path)
        if blinded.get("blinded") is not True or blinded.get("prior_review_visible") is not False:
            raise PolishReviewError("second-review input must be blinded with prior review hidden")
        if blinded.get(PACKET_DIGEST_FIELD) != packet[PACKET_DIGEST_FIELD]:
            raise PolishReviewError("second-review input packet digest is stale")
        leak_blob = json.dumps(
            {"questions": blinded.get("questions", []), PACKET_DIGEST_FIELD: blinded.get(PACKET_DIGEST_FIELD)},
            sort_keys=True,
        )
        first = records[0]
        for leak in (
            str(first.get("reviewer_id", "")),
            str(first.get("reviewer_session_id", "")),
            str(first.get(RECORD_DIGEST_FIELD, "")),
        ):
            if leak and leak in leak_blob:
                raise PolishReviewError("blinded second-review serialization leaked prior review")

    unresolved = _unresolved_question_ids(records)
    return {
        "ok": len(unresolved) == 0 and len(records) >= required,
        "required_review_count": required,
        "record_digests": record_digests,
        "unresolved_question_ids": unresolved,
        "packet_sha256": packet[PACKET_DIGEST_FIELD],
        "review_dir": str(review_dir),
    }


def ensure_visual_reviews_for_finalize(bundle_root: Path, attestation_state: str | None) -> None:
    if not bundle_requires_visual_review(attestation_state):
        return
    review_dir = bundle_reviews_dir(bundle_root)
    try:
        report = validate_bundle_review_dir(review_dir, bundle_root)
    except PolishReviewError as exc:
        raise InvalidBundleError(str(exc), reason_code="visual_review_missing") from exc
    if report["unresolved_question_ids"]:
        raise InvalidBundleError(
            "visual review contains unresolved EDIT or UNCERTAIN answers",
            reason_code="visual_review_unresolved",
        )
    if not report["ok"]:
        raise InvalidBundleError(
            "visual review directory is incomplete",
            reason_code="visual_review_missing",
        )


def attestation_state_name(attestation: object | None) -> str | None:
    if attestation is None:
        return None
    return str(getattr(attestation, "state", None))
