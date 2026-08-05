"""CLI: validate and preview first-room asset packs."""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any

from pipeline.cli_support import emit_json
from pipeline.asset_pack import (
    AssetPackCheckResult,
    AssetPackError,
    InvalidAssetPackError,
    PackPreviewResult,
    check_asset_pack,
    load_asset_pack,
    render_pack_preview,
)


def _check_json_payload(result: AssetPackCheckResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "valid": result.valid,
        "outcome": result.outcome,
        "pack_id": result.pack_id,
        "manifest": str(result.manifest_path),
        "release_hashes": list(result.release_hashes),
    }
    if result.errors:
        payload["error"] = result.errors[0]
        payload["errors"] = list(result.errors)
        if result.reason_codes:
            payload["reason_code"] = result.reason_codes[0]
            payload["reason_codes"] = list(result.reason_codes)
    return payload


def _preview_json_payload(result: PackPreviewResult, manifest: pathlib.Path) -> dict[str, Any]:
    pack = load_asset_pack(manifest)
    return {
        "valid": True,
        "outcome": "PASS",
        "pack_id": pack.id,
        "manifest": str(manifest.resolve()),
        "native_path": str(result.native_path),
        "scale4x_path": str(result.scale4x_path),
        "native_sha256": result.native_sha256,
        "scale4x_sha256": result.scale4x_sha256,
        "release_hashes": list(result.release_hashes),
    }


def _format_check_report(result: AssetPackCheckResult) -> str:
    lines = [
        f"Manifest  {result.manifest_path}",
        f"Pack      {result.pack_id}",
        f"Overall   {result.outcome}",
    ]
    if result.errors:
        lines.append(f"Error     {result.errors[0]}")
    return "\n".join(lines)


def _format_preview_report(result: PackPreviewResult, manifest: pathlib.Path) -> str:
    pack = load_asset_pack(manifest)
    return "\n".join(
        [
            f"Manifest  {manifest.resolve()}",
            f"Pack      {pack.id}",
            f"Native    {result.native_path}",
            f"4x        {result.scale4x_path}",
            "Overall   PASS",
        ]
    )


def _handle_check(args: argparse.Namespace) -> int:
    try:
        result = check_asset_pack(args.manifest)
    except (InvalidAssetPackError, AssetPackError) as exc:
        print(str(exc), file=sys.stderr)
        reason_code = exc.reason_code if isinstance(exc, AssetPackError) else None
        if args.json:
            payload = {
                "valid": False,
                "outcome": "FAIL",
                "manifest": str(args.manifest.resolve()),
                "error": str(exc),
            }
            if reason_code is not None:
                payload["reason_code"] = reason_code
            emit_json(payload)
        return 2

    if args.json:
        emit_json(_check_json_payload(result))
    else:
        print(_format_check_report(result))
    return 0 if result.valid else 2


def _handle_preview(args: argparse.Namespace) -> int:
    try:
        result = render_pack_preview(args.manifest, args.out)
    except (InvalidAssetPackError, AssetPackError) as exc:
        print(str(exc), file=sys.stderr)
        reason_code = exc.reason_code if isinstance(exc, AssetPackError) else None
        if args.json:
            payload = {
                "valid": False,
                "outcome": "FAIL",
                "manifest": str(args.manifest.resolve()),
                "error": str(exc),
            }
            if reason_code is not None:
                payload["reason_code"] = reason_code
            emit_json(payload)
        return 2

    if args.json:
        emit_json(_preview_json_payload(result, args.manifest))
    else:
        print(_format_preview_report(result, args.manifest))
    return 0


def _configure_parser(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Validate an asset pack manifest")
    check.add_argument("manifest", type=pathlib.Path, help="Asset pack manifest JSON")
    check.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")

    preview = sub.add_parser("preview", help="Render deterministic pack previews")
    preview.add_argument("manifest", type=pathlib.Path, help="Asset pack manifest JSON")
    preview.add_argument("--out", type=pathlib.Path, required=True, help="Preview output directory")
    preview.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and preview first-room asset packs.")
    _configure_parser(parser)
    args = parser.parse_args(argv)

    if args.command == "check":
        return _handle_check(args)
    if args.command == "preview":
        return _handle_preview(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
