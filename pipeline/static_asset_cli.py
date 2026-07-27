"""CLI: initialize, check, and finalize static asset bundles."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pipeline.static_asset import (
    BundleExistsError,
    InitializationRejectedError,
    InvalidBundleError,
    InvalidSpecError,
    StaticAssetCheckResult,
    StaticAssetError,
    check_static_bundle,
    finalize_static_bundle,
    initialize_static_bundle,
)


def _exit_code(outcome: str) -> int:
    if outcome == "PASS":
        return 0
    if outcome == "FAIL":
        return 1
    raise ValueError(f"unknown outcome {outcome!r}")


def _structural_payload(result: StaticAssetCheckResult) -> dict[str, Any]:
    return {
        "pass": result.structural.pass_,
        "outcome": result.structural.outcome,
        "violations": [
            {
                "code": violation.code,
                "item_id": violation.item_id,
                "x": violation.x,
                "y": violation.y,
                "detail": violation.detail,
            }
            for violation in result.structural.violations
        ],
    }


def _changed_cells_payload(result: StaticAssetCheckResult) -> dict[str, Any]:
    return {
        "edits": [
            {
                "item_id": edit.item_id,
                "x": edit.x,
                "y": edit.y,
                "draft_rgb": list(edit.draft_rgb),
                "polished_rgb": list(edit.polished_rgb),
            }
            for edit in result.delta.edits
        ],
        "per_item_counts": list(result.delta.per_item_counts),
        "total_edits": result.delta.total_edits,
    }


def _check_json_payload(
    bundle_root: pathlib.Path,
    result: StaticAssetCheckResult,
    *,
    report_path: pathlib.Path | None = None,
    release_paths: list[pathlib.Path] | None = None,
) -> dict[str, Any]:
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    payload: dict[str, Any] = {
        "bundle": str(bundle_root.resolve()),
        "provider": str((bundle_root / manifest["provider"]["relative_path"]).resolve()),
        "spec_id": manifest["spec_id"],
        "structural": _structural_payload(result),
        "changed_cells": _changed_cells_payload(result),
        "manifest_sha256": result.manifest_sha256,
        "provider_sha256": result.provider_sha256,
        "spec_sha256": result.spec_sha256,
        "palette_sha256": result.palette_sha256,
        "draft_hashes": list(result.draft_hashes),
        "polished_hashes": list(result.polished_hashes),
        "fingerprint": result.fingerprint,
        "outcome": result.outcome,
    }
    if report_path is not None:
        payload["report_path"] = str(report_path.resolve())
    if release_paths is not None:
        payload["release_paths"] = [str(path.resolve()) for path in release_paths]
    return payload


def _format_check_report(
    bundle_root: pathlib.Path,
    result: StaticAssetCheckResult,
    *,
    report_path: pathlib.Path | None = None,
    release_paths: list[pathlib.Path] | None = None,
) -> str:
    manifest = json.loads((bundle_root / "manifest.json").read_text())
    provider_path = bundle_root / manifest["provider"]["relative_path"]
    lines = [
        f"Bundle    {bundle_root.resolve()}",
        f"Provider  {provider_path.name}",
        f"Spec      {manifest['spec_id']}",
        (
            "Structural  "
            f"{result.structural.outcome}"
            f" ({len(result.structural.violations)} violations)"
        ),
        (
            "Edits     "
            f"total={result.delta.total_edits} "
            f"per_item={list(result.delta.per_item_counts)}"
        ),
        f"Overall  {result.outcome}",
    ]
    if report_path is not None:
        lines.append(f"Report    {report_path.resolve()}")
    if release_paths:
        lines.append("Release")
        for path in release_paths:
            lines.append(f"  {path.resolve()}")
    return "\n".join(lines)


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")))


def _handle_init(args: argparse.Namespace) -> int:
    try:
        initialize_static_bundle(
            args.provider,
            args.provenance,
            args.spec,
            args.out,
        )
    except BundleExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (InitializationRejectedError, InvalidSpecError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        result = check_static_bundle(args.out)
    except (InvalidBundleError, StaticAssetError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _emit_json(_check_json_payload(args.out, result))
    else:
        print(_format_check_report(args.out, result))
    return _exit_code(result.outcome)


def _handle_check(args: argparse.Namespace) -> int:
    try:
        result = check_static_bundle(args.bundle)
    except (InvalidBundleError, StaticAssetError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        _emit_json(_check_json_payload(args.bundle, result))
    else:
        print(_format_check_report(args.bundle, result))
    return _exit_code(result.outcome)


def _handle_finalize(args: argparse.Namespace) -> int:
    try:
        report_path, release_paths = finalize_static_bundle(args.bundle)
        result = check_static_bundle(args.bundle)
    except (InvalidBundleError, StaticAssetError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

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


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a static asset bundle from a provider sheet")
    init.add_argument("provider", type=pathlib.Path, help="Provider sheet PNG")
    init.add_argument("--provenance", type=pathlib.Path, required=True, help="Provenance sidecar JSON")
    init.add_argument("--spec", type=pathlib.Path, required=True, help="Static sheet specification JSON")
    init.add_argument("--out", type=pathlib.Path, required=True, help="Bundle destination directory")
    init.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    check = sub.add_parser("check", help="Validate a bundle without writing")
    check.add_argument("bundle", type=pathlib.Path, help="Static asset bundle directory")
    check.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    finalize = sub.add_parser("finalize", help="Record report and create release items on PASS")
    finalize.add_argument("bundle", type=pathlib.Path, help="Static asset bundle directory")
    finalize.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize, check, and finalize static asset bundles."
    )
    _configure_parser(parser)
    args = parser.parse_args(argv)

    if args.command == "init":
        return _handle_init(args)
    if args.command == "check":
        return _handle_check(args)
    if args.command == "finalize":
        return _handle_finalize(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
