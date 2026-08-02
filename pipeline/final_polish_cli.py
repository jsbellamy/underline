"""CLI: initialize, check, and finalize final-polish bundles."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pipeline.asset_acquire import AssetAcquisitionError, record_asset_attempt
from pipeline.final_polish import (
    BundleExistsError,
    CELL_AUTHOR_GENERATION_MODE,
    FinalPolishCheckResult,
    FinalPolishError,
    InitializationRejectedError,
    InvalidBundleError,
    _silhouette_artifacts_report_payload,
    check_bundle,
    finalize_bundle,
    initialize_bundle,
    initialize_cell_authored_bundle,
    load_polish_brief,
)
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import build_identity_seed, identity_lock_report_payload
from pipeline.polish_review import (
    PolishReviewError,
    validate_bundle_review_dir,
    write_review_packet,
)
from pipeline.strip import (
    DEFAULT_LAYOUT,
    IngestResult,
    Outcome,
    StripLayout,
    coherence_split_json_gates,
    format_coherence_split_report,
    ingest_strip_provider,
)


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _exit_code(outcome: Outcome) -> int:
    if outcome == "PASS":
        return 0
    if outcome == "FAIL":
        return 1
    if outcome == "REVIEW":
        return 3
    raise ValueError(f"unknown outcome {outcome!r}")


def _structural_payload(result: FinalPolishCheckResult) -> dict[str, Any]:
    return {
        "pass": result.structural.pass_,
        "outcome": result.structural.outcome,
        "violations": [
            {
                "code": violation.code,
                "frame_index": violation.frame_index,
                "x": violation.x,
                "y": violation.y,
                "detail": violation.detail,
            }
            for violation in result.structural.violations
        ],
    }


def _delta_payload(result: FinalPolishCheckResult) -> dict[str, Any]:
    return {
        "edits": [
            {
                "frame_index": edit.frame_index,
                "x": edit.x,
                "y": edit.y,
                "draft_rgb": list(edit.draft_rgb),
                "polished_rgb": list(edit.polished_rgb),
            }
            for edit in result.delta.edits
        ],
        "per_frame_counts": list(result.delta.per_frame_counts),
        "total_edits": result.delta.total_edits,
    }


def _identity_lock_payload(result: FinalPolishCheckResult) -> dict[str, Any] | None:
    if result.identity_lock is None:
        return None
    return identity_lock_report_payload(result.identity_lock)


def _silhouette_artifacts_payload(result: FinalPolishCheckResult) -> dict[str, Any] | None:
    if result.silhouette_artifacts is None:
        return None
    return _silhouette_artifacts_report_payload(result.silhouette_artifacts)


def _check_json_payload(
    bundle_root: pathlib.Path,
    result: FinalPolishCheckResult,
    *,
    report_path: pathlib.Path | None = None,
    release_paths: list[pathlib.Path] | None = None,
) -> dict[str, Any]:
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    gate_views = coherence_split_json_gates(result.coherence)
    payload: dict[str, Any] = {
        "provider_outcome": result.provider_outcome,
        "bundle": str(bundle_root.resolve()),
        "motion_class": manifest["motion_class"],
        "structural": _structural_payload(result),
        "visible_cell_delta": _delta_payload(result),
        "provider_post_edit": result.provider_post_edit,
        "identity_lock": _identity_lock_payload(result),
        "coherence": result.coherence,
        **gate_views,
        "manifest_sha256": result.manifest_sha256,
        "draft_hashes": list(result.draft_hashes),
        "polished_hashes": list(result.polished_hashes),
        "fingerprint": result.fingerprint,
        "polish_profile": (
            None
            if result.profile_id is None
            else {
                "id": result.profile_id,
                "sha256": result.profile_sha256,
            }
        ),
        "outcome": result.outcome,
    }
    if manifest.get("generation_mode") == CELL_AUTHOR_GENERATION_MODE:
        payload["generation_mode"] = CELL_AUTHOR_GENERATION_MODE
        if result.attestation is not None:
            payload["base_specification_id"] = result.attestation.base_specification_id
    else:
        payload["provider"] = str(
            (bundle_root / manifest["provider"]["relative_path"]).resolve()
        )
        payload["provider_sha256"] = result.provider_sha256
    silhouette_artifacts = _silhouette_artifacts_payload(result)
    if silhouette_artifacts is not None:
        payload["silhouette_artifacts"] = silhouette_artifacts
    if report_path is not None:
        payload["report_path"] = str(report_path.resolve())
    if release_paths is not None:
        payload["release_frames"] = [str(path.resolve()) for path in release_paths]
    return payload


def _check_summary_json_payload(result: FinalPolishCheckResult) -> dict[str, Any]:
    payload = {
        "outcome": result.outcome,
        "fingerprint": result.fingerprint,
        "frame_dimensions": result.coherence["dimensions"],
        "identity_lock": (
            None if result.identity_lock is None else result.identity_lock.outcome
        ),
        "gate_outcomes": result.coherence["gate_outcomes"],
    }
    if result.attestation is not None:
        payload["attestation"] = {"state": result.attestation.state}
        if result.attestation.state == CELL_AUTHOR_GENERATION_MODE:
            payload["generation_mode"] = CELL_AUTHOR_GENERATION_MODE
            payload["base_specification_id"] = result.attestation.base_specification_id
            payload["base_frames_sha256"] = (
                list(result.attestation.base_frames_sha256)
                if result.attestation.base_frames_sha256 is not None
                else None
            )
            payload["base_frame_mapping"] = (
                list(result.attestation.base_frame_mapping)
                if result.attestation.base_frame_mapping is not None
                else None
            )
            payload["cell_delta_ledger_sha256"] = result.attestation.cell_delta_ledger_sha256
    return payload


def _init_rejection_json_payload(
    provider_path: pathlib.Path,
    motion_class: str,
    ingest: IngestResult,
) -> dict[str, Any]:
    gate_views = coherence_split_json_gates(ingest.coherence)
    return {
        "pass": ingest.pass_,
        "provider": str(provider_path.resolve()),
        "motion_class": motion_class,
        "coherence": ingest.coherence,
        **gate_views,
        "outcome": ingest.outcome,
    }


def _init_provenance_rejection_json_payload(
    provider_path: pathlib.Path,
    motion_class: str,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "pass": False,
        "provider": str(provider_path.resolve()),
        "motion_class": motion_class,
        "outcome": "FAIL",
        "reason_code": reason_code,
    }


def _init_cell_rejection_json_payload(
    motion_class: str,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "pass": False,
        "motion_class": motion_class,
        "outcome": "FAIL",
        "reason_code": reason_code,
    }


def _format_provider_post_edit(payload: dict[str, Any] | None) -> str:
    if payload is None:
        return "(n/a)"
    outcome = payload["outcome"]
    reason_code = payload.get("reason_code")
    if reason_code is None:
        return str(outcome)
    return f"{outcome} ({reason_code})"


def _format_check_report(
    bundle_root: pathlib.Path,
    result: FinalPolishCheckResult,
    *,
    report_path: pathlib.Path | None = None,
    release_paths: list[pathlib.Path] | None = None,
) -> str:
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    lines = [
        f"Bundle    {bundle_root.resolve()}",
    ]
    if manifest.get("generation_mode") == CELL_AUTHOR_GENERATION_MODE:
        lines.append(f"Mode      {CELL_AUTHOR_GENERATION_MODE}")
    else:
        provider_path = bundle_root / manifest["provider"]["relative_path"]
        lines.append(f"Provider  {provider_path.name}")
    lines.extend([
        f"Motion    {manifest['motion_class']}",
        f"Profile   {result.profile_id or '(none)'}",
        (
            "Structural  "
            f"{result.structural.outcome}"
            f" ({len(result.structural.violations)} violations)"
        ),
        (
            "Identity    "
            f"{result.identity_lock.outcome if result.identity_lock is not None else '(n/a)'}"
        ),
        f"Post-edit   {_format_provider_post_edit(result.provider_post_edit)}",
        (
            "Edits     "
            f"total={result.delta.total_edits} "
            f"per_frame={list(result.delta.per_frame_counts)}"
        ),
        "Gates",
    ])
    lines.extend(format_coherence_split_report(result.coherence))
    lines.append(f"Overall  {result.outcome}")
    silhouette_artifacts = _silhouette_artifacts_payload(result)
    if silhouette_artifacts is not None:
        lines.append("Silhouette")
        lines.append(f"  strip  {silhouette_artifacts['strip']['relative_path']}")
        lines.append(f"  gif    {silhouette_artifacts['gif']['relative_path']}")
    if report_path is not None:
        lines.append(f"Report    {report_path.resolve()}")
    if release_paths:
        lines.append("Release")
        for path in release_paths:
            lines.append(f"  {path.resolve()}")
    return "\n".join(lines)


def _format_init_rejection_report(
    provider_path: pathlib.Path,
    motion_class: str,
    ingest: IngestResult,
) -> str:
    lines = [
        f"Provider  {provider_path.name}",
        f"Motion    {motion_class}",
        "Gates",
    ]
    lines.extend(format_coherence_split_report(ingest.coherence))
    lines.append(f"Overall  {ingest.outcome}")
    lines.append("Bundle    (not created)")
    return "\n".join(lines)


def _release_paths(bundle_root: pathlib.Path, result: FinalPolishCheckResult) -> list[pathlib.Path]:
    if result.outcome != "PASS":
        return []
    release_dir = bundle_root / "release"
    return sorted(release_dir.glob("frame-*.png"))


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")))


def _format_brief(brief: dict[str, Any]) -> str:
    lines = [
        f"Profile   {brief['profile']['id']} ({brief['profile']['sha256']})",
        f"Motion    {brief['motion_class']}",
        f"Verdicts  {', '.join(brief['verdicts'])}",
        f"Occlusion {brief['occlusion_rule']}",
        "Fixed questions",
    ]
    for row in brief["fixed_questions"]:
        lines.append(f"  {row['id']}: {row['question']}")
    lines.append("Motion questions")
    if brief["motion_questions"]:
        for row in brief["motion_questions"]:
            lines.append(f"  {row['id']}: {row['question']}")
    else:
        lines.append("  (none)")
    lines.append("Editing rules")
    lines.extend(f"  - {rule}" for rule in brief["editing_rules"])
    lines.append("Audit workflow")
    lines.extend(f"  {index}. {step}" for index, step in enumerate(brief["audit_workflow"], 1))
    return "\n".join(lines)


def _handle_init_cell(args: argparse.Namespace) -> int:
    try:
        initialize_cell_authored_bundle(
            args.authored_frames_dir,
            args.motion_class,
            args.out,
            specification_id=args.specification_id,
            base_bundle_root=args.base_bundle,
            cell_delta_ledger=args.cell_delta_ledger,
            pose_plan=args.pose_plan,
            polish_profile=args.polish_profile,
            identity_reference=args.identity_reference,
            authoring_agent=args.authoring_agent,
            authoring_session_id=args.authoring_session_id,
        )
    except BundleExistsError as exc:
        if args.json:
            _emit_json(
                _init_cell_rejection_json_payload(
                    args.motion_class,
                    exc.reason_code or "bundle_exists",
                )
            )
        print(str(exc), file=sys.stderr)
        return 2
    except InitializationRejectedError as exc:
        if args.json:
            _emit_json(
                _init_cell_rejection_json_payload(
                    args.motion_class,
                    exc.reason_code or "unknown",
                )
            )
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        if args.json:
            _emit_json(
                _init_cell_rejection_json_payload(args.motion_class, "invalid_arguments")
            )
        print(str(exc), file=sys.stderr)
        return 2

    try:
        result = check_bundle(args.out)
    except (InvalidBundleError, FinalPolishError) as exc:
        if args.json:
            _emit_json(
                _init_cell_rejection_json_payload(
                    args.motion_class,
                    exc.reason_code or "invalid_bundle",
                )
            )
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _emit_json(_check_json_payload(args.out, result))
    else:
        print(_format_check_report(args.out, result))
    return _exit_code(result.outcome)


def _handle_init(args: argparse.Namespace) -> int:
    try:
        initialize_bundle(
            args.provider,
            args.motion_class,
            args.out,
            provenance_sidecar=args.provenance,
            polish_profile=args.polish_profile,
            identity_reference=args.identity_reference,
            edit_source=args.edit_source,
        )
    except BundleExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except InitializationRejectedError as exc:
        if exc.reason_code != "ingest_not_pass":
            if args.json:
                _emit_json(
                    _init_provenance_rejection_json_payload(
                        args.provider,
                        args.motion_class,
                        exc.reason_code or "unknown",
                    )
                )
            print(str(exc), file=sys.stderr)
            return 2
        try:
            ingest = ingest_strip_provider(args.provider, _corpus_layout(), motion_class=args.motion_class)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            _emit_json(_init_rejection_json_payload(args.provider, args.motion_class, ingest))
        else:
            print(_format_init_rejection_report(args.provider, args.motion_class, ingest))
        return _exit_code(ingest.outcome)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        result = check_bundle(args.out)
    except (InvalidBundleError, FinalPolishError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _emit_json(_check_json_payload(args.out, result))
    else:
        print(_format_check_report(args.out, result))
    return _exit_code(result.outcome)


def _handle_check(args: argparse.Namespace) -> int:
    try:
        result = check_bundle(args.bundle)
    except (InvalidBundleError, FinalPolishError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.summary_json:
        _emit_json(_check_summary_json_payload(result))
    elif args.json:
        _emit_json(_check_json_payload(args.bundle, result))
    else:
        print(_format_check_report(args.bundle, result))
    return _exit_code(result.outcome)


def _handle_brief(args: argparse.Namespace) -> int:
    try:
        brief = load_polish_brief(args.bundle)
    except (InvalidBundleError, FinalPolishError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit_json(brief)
    else:
        print(_format_brief(brief))
    return 0


def _handle_finalize(args: argparse.Namespace) -> int:
    try:
        report_path = finalize_bundle(args.bundle)
        result = check_bundle(args.bundle)
    except (InvalidBundleError, FinalPolishError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    release_paths = _release_paths(args.bundle, result)
    if args.json:
        _emit_json(
            _check_json_payload(
                args.bundle,
                result,
                report_path=report_path,
                release_paths=release_paths or None,
            )
        )
    else:
        print(
            _format_check_report(
                args.bundle,
                result,
                report_path=report_path,
                release_paths=release_paths or None,
            )
        )
    return _exit_code(result.outcome)


def _handle_review_packet(args: argparse.Namespace) -> int:
    try:
        packet = write_review_packet(args.bundle)
    except (InvalidBundleError, FinalPolishError, PolishReviewError) as exc:
        reason_code = getattr(exc, "reason_code", None)
        if args.json:
            _emit_json(
                {
                    "ok": False,
                    "error": str(exc),
                    "reason_code": reason_code,
                }
            )
        print(str(exc), file=sys.stderr)
        return 2
    review_dir = args.bundle / "reviews"
    payload = {
        "ok": True,
        "packet_sha256": packet["packet_sha256"],
        "packet_json": str((review_dir / "packet.json").resolve()),
        "packet_png": str((review_dir / "packet.png").resolve()),
    }
    if args.json:
        _emit_json(payload)
    else:
        print(f"Packet    {payload['packet_json']}")
        print(f"PNG       {payload['packet_png']}")
        print(f"SHA-256   {payload['packet_sha256']}")
    return 0


def _handle_validate_reviews(args: argparse.Namespace) -> int:
    review_dir = args.bundle / "reviews"
    try:
        report = validate_bundle_review_dir(review_dir, args.bundle)
    except PolishReviewError as exc:
        report = {
            "ok": False,
            "error": str(exc),
            "review_dir": str(review_dir.resolve()),
        }
    if args.json:
        _emit_json(report)
    else:
        print(f"Reviews   {report.get('review_dir', review_dir)}")
        print(f"OK        {report.get('ok')}")
        if report.get("required_review_count") is not None:
            print(f"Required  {report['required_review_count']}")
        if report.get("record_digests"):
            for digest in report["record_digests"]:
                print(f"  {digest}")
        if report.get("unresolved_question_ids"):
            print(f"Unresolved {', '.join(report['unresolved_question_ids'])}")
        if report.get("error"):
            print(report["error"], file=sys.stderr)
    return 0 if report.get("ok") else 1


def _handle_seed(args: argparse.Namespace) -> int:
    try:
        meta = build_identity_seed(
            args.identity_declaration,
            args.out,
            motion_class=args.motion_class,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _emit_json(meta)
    else:
        print(f"Seed      {meta['out_path']}")
        print(f"Size      {meta['dimensions'][0]}x{meta['dimensions'][1]}")
        print(f"SHA-256   {meta['sha256']}")
    return 0


_ACQUIRE_ACQUIRING_AGENT = "cursor-agent"


def _acquire_json_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt_id": row["attempt_id"],
        "ordinal": row["ordinal"],
        "predecessor_attempt_id": row["predecessor_attempt_id"],
        "outcome": row["outcome"],
        "raw_path": row["raw_path"],
        "raw_sha256": row["raw_sha256"],
        "dimensions": row["dimensions"],
        "provenance_path": row["provenance_path"],
    }


def _format_acquire_report(row: dict[str, Any]) -> str:
    dimensions = row["dimensions"]
    lines = [
        f"Attempt      {row['attempt_id']}",
        f"Ordinal      {row['ordinal']}",
        f"Predecessor  {row['predecessor_attempt_id'] or '(none)'}",
        f"Outcome      {row['outcome']}",
        f"Raw          {row['raw_path']}",
        f"SHA-256      {row['raw_sha256']}",
        f"Dimensions   {dimensions[0]}x{dimensions[1]}",
        f"Provenance   {row['provenance_path']}",
    ]
    return "\n".join(lines)


def _handle_acquire(args: argparse.Namespace) -> int:
    try:
        row = record_asset_attempt(
            args.candidate,
            args.specification_id,
            motion_class=args.motion_class,
            generation_mode=args.generation_mode,
            acquiring_agent=_ACQUIRE_ACQUIRING_AGENT,
            prompt_path=args.prompt_file,
            edit_source=args.edit_source,
            reference_image_sha256=(
                sha256_file(args.identity_reference) if args.identity_reference else None
            ),
            outcome="rejected" if args.reject else "accepted",
            rejection_reason=args.reject,
        )
    except AssetAcquisitionError as exc:
        if args.json:
            _emit_json(
                {
                    "pass": False,
                    "outcome": "FAIL",
                    "reason_code": exc.reason_code or "asset_acquisition_error",
                }
            )
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _emit_json(_acquire_json_payload(row))
    else:
        print(_format_acquire_report(row))
    return 0


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a final-polish bundle from a provider strip")
    init.add_argument("provider", type=pathlib.Path, help="Provider strip PNG")
    init.add_argument(
        "--provenance",
        type=pathlib.Path,
        required=True,
        help="Animation provenance sidecar (animation-strip-provenance/0)",
    )
    init.add_argument("--motion-class", required=True, help="Motion class for gating")
    init.add_argument("--out", type=pathlib.Path, required=True, help="Bundle destination directory")
    init.add_argument("--polish-profile", help="Embed a checked-in visual audit profile")
    init.add_argument(
        "--identity-reference",
        type=pathlib.Path,
        help="Canonical identity PNG (required for dwarf-miner walk/swing)",
    )
    init.add_argument(
        "--edit-source",
        type=pathlib.Path,
        help="Seed strip PNG for image-edit generation (required for dwarf-miner walk/swing)",
    )
    init.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    init_cell = sub.add_parser(
        "init-cell",
        help="Create a cell-authored final-polish bundle without a provider raster",
    )
    init_cell.add_argument(
        "authored_frames_dir",
        type=pathlib.Path,
        help="Directory of authored logical frame PNGs (frame-0.png …)",
    )
    init_cell.add_argument(
        "--base-bundle",
        type=pathlib.Path,
        required=True,
        help="Finalized provider base bundle directory",
    )
    init_cell.add_argument(
        "--cell-delta-ledger",
        type=pathlib.Path,
        required=True,
        help="Cell-delta ledger sidecar (cell-delta-ledger/0)",
    )
    init_cell.add_argument(
        "--pose-plan",
        type=pathlib.Path,
        required=True,
        help="Motion pose plan sidecar (motion-pose-plan/0)",
    )
    init_cell.add_argument(
        "--specification-id",
        required=True,
        help="Slash-delimited specification id for the cell-authored bundle",
    )
    init_cell.add_argument("--motion-class", required=True, help="Motion class for gating")
    init_cell.add_argument("--out", type=pathlib.Path, required=True, help="Bundle destination directory")
    init_cell.add_argument("--polish-profile", required=True, help="Embed a checked-in visual audit profile")
    init_cell.add_argument(
        "--identity-reference",
        type=pathlib.Path,
        help="Canonical identity PNG (required for dwarf-miner walk/swing)",
    )
    init_cell.add_argument("--authoring-agent", required=True, help="Authoring agent identifier")
    init_cell.add_argument(
        "--authoring-session-id",
        required=True,
        help="Authoring session identifier",
    )
    init_cell.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    check = sub.add_parser("check", help="Validate a bundle without writing")
    check.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    check_output = check.add_mutually_exclusive_group()
    check_output.add_argument(
        "--json", action="store_true", help="Emit complete machine-readable JSON on stdout"
    )
    check_output.add_argument(
        "--summary-json",
        action="store_true",
        help="Emit compact baseline fields for agent dispatch on stdout",
    )

    brief = sub.add_parser("brief", help="Read the bundle's visual audit profile")
    brief.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    brief.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    finalize = sub.add_parser("finalize", help="Record report and create release frames on PASS")
    finalize.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    finalize.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    review_packet = sub.add_parser(
        "review-packet",
        help="Build blinded visual-review packet evidence under reviews/",
    )
    review_packet.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    review_packet.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    validate_reviews = sub.add_parser(
        "validate-reviews",
        help="Validate immutable visual-review records for a bundle",
    )
    validate_reviews.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    validate_reviews.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    seed = sub.add_parser(
        "seed",
        help=(
            "Emit image-edit seed from identity.json generation_source; "
            "when seed_pad_px is declared, adds uniform #FF00FF border "
            "(does not read identity.png)"
        ),
    )
    seed.add_argument(
        "--identity-declaration",
        type=pathlib.Path,
        required=True,
        help=(
            "Dwarf identity declaration JSON (e.g. assets/first-room/dwarf/identity.json); "
            "NOT identity.png"
        ),
    )
    seed.add_argument(
        "--out",
        type=pathlib.Path,
        required=True,
        help="Output edit-source strip PNG (padded seed when seed_pad_px declared)",
    )
    seed.add_argument(
        "--motion-class",
        help=(
            "Motion class for action-canvas geometry (swing: 24-Cell interior); "
            "omit for the 16-Cell uniform-pad seed"
        ),
    )
    seed.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    acquire = sub.add_parser(
        "acquire",
        help="Record an attested asset-acquisition Attempt in acquisition-controls/",
    )
    acquire.add_argument("candidate", type=pathlib.Path, help="Candidate PNG bytes")
    acquire.add_argument(
        "--specification-id",
        dest="specification_id",
        required=True,
        help="Bundle's slash-delimited asset path, e.g. first-room/dwarf/swing",
    )
    acquire.add_argument("--motion-class", required=True, help="Motion class for the Attempt")
    acquire.add_argument(
        "--generation-mode",
        dest="generation_mode",
        required=True,
        help="text-to-image or image-edit",
    )
    acquire.add_argument(
        "--prompt-file",
        dest="prompt_file",
        type=pathlib.Path,
        required=True,
        help="Prompt text file hashed into the provenance record",
    )
    acquire.add_argument(
        "--edit-source",
        dest="edit_source",
        type=pathlib.Path,
        help="Seed strip PNG for image-edit generation",
    )
    acquire.add_argument(
        "--identity-reference",
        dest="identity_reference",
        type=pathlib.Path,
        help="Canonical identity PNG hashed into reference_image_sha256",
    )
    acquire.add_argument(
        "--reject",
        metavar="REASON",
        help="Record this Attempt as rejected with the given reason",
    )
    acquire.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize, brief, check, and finalize final-polish bundles."
    )
    _configure_parser(parser)
    args = parser.parse_args(argv)

    if args.command == "init":
        return _handle_init(args)
    if args.command == "init-cell":
        return _handle_init_cell(args)
    if args.command == "check":
        return _handle_check(args)
    if args.command == "brief":
        return _handle_brief(args)
    if args.command == "finalize":
        return _handle_finalize(args)
    if args.command == "review-packet":
        return _handle_review_packet(args)
    if args.command == "validate-reviews":
        return _handle_validate_reviews(args)
    if args.command == "seed":
        return _handle_seed(args)
    if args.command == "acquire":
        return _handle_acquire(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
