"""CLI for dwarf Cell part-map review rendering (issue #298)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.parts import PartMapError, load_part_map, render_part_map

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_PARTS_JSON = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "parts.json"
_DEFAULT_REVIEW_PNG = _REPO_ROOT / "assets" / "first-room" / "dwarf" / "parts-review.png"


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render dwarf Cell part-map review sheets.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render", help="Write the part-map review PNG.")
    render_parser.add_argument(
        "--parts-json",
        type=Path,
        default=_DEFAULT_PARTS_JSON,
        help="Cell part map document path.",
    )
    render_parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_REVIEW_PNG,
        help="Review PNG output path.",
    )

    args = parser.parse_args(argv)

    try:
        if args.command == "render":
            part_map = load_part_map(args.parts_json)
            payload = json.loads(args.parts_json.read_text(encoding="utf-8"))
            base_path = _REPO_ROOT / payload["base_raster_relative_path"]
            image = render_part_map(part_map, base_path)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            image.save(args.out, format="PNG", compress_level=6)
            print(args.out.resolve())
            return 0
    except PartMapError as exc:
        print(f"Error: {exc} ({exc.reason_code})", file=sys.stderr)
        return 2
    return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
