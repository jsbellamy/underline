"""CLI adapter for declarative Motion Author (issue #277)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pipeline.cell_raster import read_cells, write_cells
from pipeline.final_polish import FinalPolishError, _load_base_release_frames
from pipeline.identity_lock import load_identity_lock_spec
from pipeline.motion_author import MotionAuthorError, author_motion
from pipeline.parts import load_part_map
from pipeline.palette_quantize import load_master_palette
from pipeline.strip import Cell


def _discover_base_frames(base_bundle: Path, motion_class: str) -> list[list[list[Cell]]]:
    """Load base Frames from ``base_bundle``, embedded onto ``motion_class``'s canvas."""
    if (base_bundle / "manifest.json").is_file():
        try:
            return _load_base_release_frames(base_bundle, motion_class)
        except FinalPolishError as exc:
            raise MotionAuthorError(str(exc), reason_code="authoring_boundary_violation") from exc
    paths = sorted(base_bundle.glob("frame-*.png"))
    if not paths:
        raise MotionAuthorError(
            f"no frame-*.png files in base bundle: {base_bundle}",
            reason_code="authoring_boundary_violation",
        )
    return [read_cells(path, label="base frame") for path in paths]


def _load_pose_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise MotionAuthorError(f"missing pose plan: {path}", reason_code="authoring_boundary_violation")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MotionAuthorError(
            f"invalid pose plan JSON: {path}",
            reason_code="authoring_boundary_violation",
        ) from exc
    if not isinstance(doc, dict):
        raise MotionAuthorError("pose plan must be an object", reason_code="authoring_boundary_violation")
    return doc


def _report_payload(result_report: dict[str, Any], *, frame_count: int) -> dict[str, Any]:
    return {
        "frame_count": frame_count,
        "ledger_digest": result_report["ledger_digest"],
        "report": result_report,
    }


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Author Motion Frames from a declarative pose plan.")
    parser.add_argument("--base-bundle", type=Path, required=True)
    parser.add_argument("--pose-plan", type=Path, required=True)
    parser.add_argument("--identity-locks", type=Path, required=True)
    parser.add_argument("--palette", type=Path, required=True)
    parser.add_argument("--part-map", type=Path, default=None)
    parser.add_argument("--frames-out", type=Path, required=True)
    parser.add_argument("--ledger-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        pose_plan = _load_pose_plan(args.pose_plan)
        motion_class = pose_plan.get("motion_class")
        if not isinstance(motion_class, str) or not motion_class:
            raise MotionAuthorError(
                "pose plan motion_class required", reason_code="authoring_boundary_violation"
            )
        identity_lock_spec = load_identity_lock_spec(args.identity_locks)
        palette = load_master_palette(args.palette)
        part_map = None
        if args.part_map is not None:
            part_map = load_part_map(args.part_map)
        base_frames = _discover_base_frames(args.base_bundle, motion_class)
        result = author_motion(
            base_frames,
            pose_plan,
            identity_lock_spec,
            palette,
            part_map=part_map,
        )

        args.frames_out.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(result.frames):
            write_cells(args.frames_out / f"frame-{index}.png", frame)
        args.ledger_out.parent.mkdir(parents=True, exist_ok=True)
        args.ledger_out.write_text(json.dumps(result.ledger, indent=2) + "\n", encoding="utf-8")

        payload = _report_payload(result.report, frame_count=len(result.frames))
        if args.json:
            print(json.dumps(payload, separators=(",", ":")))
        else:
            print(
                "\n".join(
                    [
                        f"Frames    {args.frames_out.resolve()} ({len(result.frames)})",
                        f"Ledger    {args.ledger_out.resolve()}",
                        f"Digest    {result.report['ledger_digest']}",
                    ]
                )
            )
        return 0
    except MotionAuthorError as exc:
        if args.json:
            print(
                json.dumps(
                    {"error": str(exc), "reason_code": exc.reason_code},
                    separators=(",", ":"),
                )
            )
        else:
            print(f"Error: {exc} ({exc.reason_code})", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
