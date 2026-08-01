"""CLI: initialize, check, and finalize final-polish bundles."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pipeline.final_polish import (
    BundleExistsError,
    FinalPolishCheckResult,
    FinalPolishError,
    InitializationRejectedError,
    InvalidBundleError,
    _silhouette_artifacts_report_payload,
    check_bundle,
    finalize_bundle,
    initialize_bundle,
    load_polish_brief,
)
from pipeline.identity_lock import build_identity_seed, identity_lock_report_payload
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
        "provider": str((bundle_root / manifest["provider"]["relative_path"]).resolve()),
        "motion_class": manifest["motion_class"],
        "structural": _structural_payload(result),
        "visible_cell_delta": _delta_payload(result),
        "identity_lock": _identity_lock_payload(result),
        "coherence": result.coherence,
        **gate_views,
        "manifest_sha256": result.manifest_sha256,
        "provider_sha256": result.provider_sha256,
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
    silhouette_artifacts = _silhouette_artifacts_payload(result)
    if silhouette_artifacts is not None:
        payload["silhouette_artifacts"] = silhouette_artifacts
    if report_path is not None:
        payload["report_path"] = str(report_path.resolve())
    if release_paths is not None:
        payload["release_frames"] = [str(path.resolve()) for path in release_paths]
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


def _format_check_report(
    bundle_root: pathlib.Path,
    result: FinalPolishCheckResult,
    *,
    report_path: pathlib.Path | None = None,
    release_paths: list[pathlib.Path] | None = None,
) -> str:
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    provider_path = bundle_root / manifest["provider"]["relative_path"]
    lines = [
        f"Bundle    {bundle_root.resolve()}",
        f"Provider  {provider_path.name}",
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
        (
            "Edits     "
            f"total={result.delta.total_edits} "
            f"per_frame={list(result.delta.per_frame_counts)}"
        ),
        "Gates",
    ]
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

    if args.json:
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


def _handle_seed(args: argparse.Namespace) -> int:
    try:
        meta = build_identity_seed(args.identity_declaration, args.out)
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

    check = sub.add_parser("check", help="Validate a bundle without writing")
    check.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    check.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    brief = sub.add_parser("brief", help="Read the bundle's visual audit profile")
    brief.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    brief.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    finalize = sub.add_parser("finalize", help="Record report and create release frames on PASS")
    finalize.add_argument("bundle", type=pathlib.Path, help="Final-polish bundle directory")
    finalize.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

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
    seed.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize, brief, check, and finalize final-polish bundles."
    )
    _configure_parser(parser)
    args = parser.parse_args(argv)

    if args.command == "init":
        return _handle_init(args)
    if args.command == "check":
        return _handle_check(args)
    if args.command == "brief":
        return _handle_brief(args)
    if args.command == "finalize":
        return _handle_finalize(args)
    if args.command == "seed":
        return _handle_seed(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
