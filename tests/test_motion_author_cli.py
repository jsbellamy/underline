"""CLI coverage for cross-dimension cell authoring (issue #290 C2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pipeline.cell_raster import read_cells, write_cells
from pipeline.motion_author import MOTION_POSE_PLAN_SCHEMA, MOTION_POSE_PLAN_SCHEMA_V1

from tests.support import polish_bundle as pb

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
IDENTITY_LOCKS_PATH = ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
PARTS_JSON = ROOT / "assets" / "first-room" / "dwarf" / "parts.json"


def _swing_pose_plan(*, frame_ops: list[list[dict[str, object]]]) -> dict[str, object]:
    return {
        "schema": MOTION_POSE_PLAN_SCHEMA,
        "motion_class": "swing",
        "frame_size": [24, 24],
        "frame_count": len(frame_ops),
        "canonical_origin": [1, 0],
        "base_specification_id": "first-room/dwarf/swing",
        "base_frame_mapping": [0] * len(frame_ops),
        "frames": frame_ops,
    }


def _run_author_module(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.motion_author_cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_embeds_a_bundle_root_base_onto_the_target_class_canvas(tmp_path: Path) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)

    pose_plan_path = tmp_path / "pose-plan.json"
    pose_plan_path.write_text(
        json.dumps(
            _swing_pose_plan(
                frame_ops=[
                    [
                        {
                            "op": "paint",
                            "x": 2,
                            "y": 22,
                            "palette_role": "amber-emission",
                            "color": "#F0A33A",
                        }
                    ],
                    [
                        {
                            "op": "paint",
                            "x": 2,
                            "y": 23,
                            "palette_role": "amber-emission",
                            "color": "#F0A33A",
                        }
                    ],
                    [
                        {
                            "op": "paint",
                            "x": 21,
                            "y": 22,
                            "palette_role": "amber-emission",
                            "color": "#F0A33A",
                        }
                    ],
                    [
                        {
                            "op": "paint",
                            "x": 21,
                            "y": 23,
                            "palette_role": "amber-emission",
                            "color": "#F0A33A",
                        }
                    ],
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    frames_out = tmp_path / "authored"
    ledger_out = tmp_path / "ledger.json"
    result = _run_author_module(
        [
            "--base-bundle",
            str(prepared.base_bundle),
            "--pose-plan",
            str(pose_plan_path),
            "--identity-locks",
            str(IDENTITY_LOCKS_PATH),
            "--palette",
            str(PALETTE_PATH),
            "--frames-out",
            str(frames_out),
            "--ledger-out",
            str(ledger_out),
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["frame_count"] == 4
    for index in range(4):
        authored = read_cells(frames_out / f"frame-{index}.png", size=(24, 24))
        assert len(authored) == 24
        assert len(authored[0]) == 24
    first_frame = read_cells(frames_out / "frame-0.png", size=(24, 24))
    assert first_frame[22][2] == (240, 163, 58)


REAL_DWARF_IDLE_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "idle"


def test_cli_passes_part_map_for_v1_pose_plan(tmp_path: Path) -> None:
    part_map_digest = json.loads(PARTS_JSON.read_text(encoding="utf-8"))["base_raster_sha256"]
    pose_plan_path = tmp_path / "pose-plan.json"
    pose_plan_path.write_text(
        json.dumps(
            {
                "schema": MOTION_POSE_PLAN_SCHEMA_V1,
                "motion_class": "swing",
                "frame_size": [24, 24],
                "frame_count": 1,
                "canonical_origin": [1, 0],
                "base_specification_id": "first-room/dwarf/swing",
                "base_frame_mapping": [0],
                "part_map_digest": part_map_digest,
                "frames": [[]],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    frames_out = tmp_path / "authored"
    ledger_out = tmp_path / "ledger.json"
    result = _run_author_module(
        [
            "--base-bundle",
            str(REAL_DWARF_IDLE_BUNDLE),
            "--pose-plan",
            str(pose_plan_path),
            "--part-map",
            str(PARTS_JSON),
            "--identity-locks",
            str(IDENTITY_LOCKS_PATH),
            "--palette",
            str(PALETTE_PATH),
            "--frames-out",
            str(frames_out),
            "--ledger-out",
            str(ledger_out),
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["report"]["pose_plan_schema"] == MOTION_POSE_PLAN_SCHEMA_V1
    assert payload["frame_count"] == 1


def test_cli_still_rejects_a_base_matching_neither_raster(tmp_path: Path) -> None:
    stray = [[None for _ in range(20)] for _ in range(20)]
    base_bundle = tmp_path / "base"
    base_bundle.mkdir()
    write_cells(base_bundle / "frame-0.png", stray)

    pose_plan_path = tmp_path / "pose-plan.json"
    pose_plan_path.write_text(
        json.dumps(
            _swing_pose_plan(
                frame_ops=[
                    [
                        {
                            "op": "paint",
                            "x": 2,
                            "y": 22,
                            "palette_role": "amber-emission",
                            "color": "#F0A33A",
                        }
                    ]
                ]
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run_author_module(
        [
            "--base-bundle",
            str(base_bundle),
            "--pose-plan",
            str(pose_plan_path),
            "--identity-locks",
            str(IDENTITY_LOCKS_PATH),
            "--palette",
            str(PALETTE_PATH),
            "--frames-out",
            str(tmp_path / "authored"),
            "--ledger-out",
            str(tmp_path / "ledger.json"),
            "--json",
        ]
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["reason_code"] == "authoring_boundary_violation"
