"""Motion Author declarative pose execution (issue #277)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.canonical import packet_bytes
from pipeline.cell_delta import SCHEMA as LEDGER_SCHEMA
from pipeline.cell_raster import read_cells, write_cells
from pipeline.final_polish import _load_base_release_frames
from pipeline.motion_author import (
    MOTION_POSE_PLAN_SCHEMA,
    AuthoredMotion,
    MotionAuthorError,
    author_motion,
)
from pipeline.palette_quantize import load_master_palette
from tests.support import polish_bundle as pb

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
IDENTITY_LOCKS_PATH = ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
STONE = (74, 59, 72)
OUTLINE = (17, 16, 24)


def _blank_frame(width: int, height: int) -> list[list[tuple[int, int, int] | None]]:
    return [[None for _ in range(width)] for _ in range(height)]


def _frame_with_rect(
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    rgb: tuple[int, int, int],
) -> list[list[tuple[int, int, int] | None]]:
    frame = _blank_frame(width, height)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            frame[y][x] = rgb
    return frame


def _alpha_bbox(cells: list[list[tuple[int, int, int] | None]]) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _opaque_column_loads(cells: list[list[tuple[int, int, int] | None]]) -> list[int]:
    width = len(cells[0])
    return [sum(1 for row in cells if row[x] is not None) for x in range(width)]


def _changed_cell_count(
    base: list[list[tuple[int, int, int] | None]],
    target: list[list[tuple[int, int, int] | None]],
) -> int:
    return sum(
        1
        for y in range(len(base))
        for x in range(len(base[0]))
        if base[y][x] != target[y][x]
    )


def _walk_pose_plan(*, frame_ops: list[list[dict[str, object]]]) -> dict[str, object]:
    return {
        "schema": MOTION_POSE_PLAN_SCHEMA,
        "motion_class": "walk",
        "frame_size": [16, 24],
        "frame_count": len(frame_ops),
        "canonical_origin": [0, 0],
        "base_specification_id": "first-room/dwarf/idle",
        "base_frame_mapping": [0] * len(frame_ops),
        "frames": frame_ops,
    }


def _load_identity_lock_spec() -> dict[str, object]:
    return json.loads(IDENTITY_LOCKS_PATH.read_text(encoding="utf-8"))


def test_author_motion_executes_a_declarative_four_frame_plan(tmp_path: Path) -> None:
    width, height = 16, 24
    base = _frame_with_rect(width, height, 4, 6, 11, 17, STONE)
    pose_plan = _walk_pose_plan(
        frame_ops=[
            [{"op": "paint", "x": 2, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}],
            [{"op": "relocate_lock", "lock_id": "upper_body", "dx": 0, "dy": 1}],
            [{"op": "paint", "x": 3, "y": 20, "palette_role": "dark-outline", "color": "#111018"}],
            [
                {
                    "op": "stroke",
                    "x0": 2,
                    "y0": 20,
                    "x1": 6,
                    "y1": 23,
                    "palette_role": "dark-outline",
                    "color": "#1D1720",
                }
            ],
        ]
    )
    palette = load_master_palette(PALETTE_PATH)
    result = author_motion(
        [base],
        pose_plan,
        _load_identity_lock_spec(),
        palette,
    )

    assert isinstance(result, AuthoredMotion)
    assert len(result.frames) == 4
    assert result.ledger["schema"] == LEDGER_SCHEMA
    assert result.ledger["base_specification_id"] == "first-room/dwarf/idle"
    assert result.ledger["base_frame_mapping"] == [0, 0, 0, 0]
    assert result.ledger["target_frame_count"] == 4
    assert result.report["schema"] == "motion-author-report/0"
    assert result.report["motion_class"] == "walk"
    assert result.report["pose_plan_schema"] == MOTION_POSE_PLAN_SCHEMA
    assert result.frames[0][22][2] == (240, 163, 58)
    assert result.frames[1][7][4] == STONE
    assert result.frames[2][20][3] == OUTLINE


def _swing_pose_plan(*, frame_ops: list[list[dict[str, object]]]) -> dict[str, object]:
    return {
        "schema": MOTION_POSE_PLAN_SCHEMA,
        "motion_class": "swing",
        "frame_size": [24, 24],
        "frame_count": len(frame_ops),
        "canonical_origin": [4, 0],
        "base_specification_id": "first-room/dwarf/swing",
        "base_frame_mapping": [0] * len(frame_ops),
        "frames": frame_ops,
    }


def _swing_base_frame() -> list[list[tuple[int, int, int] | None]]:
    frame = _blank_frame(24, 24)
    for y in range(1, 11):
        for x in range(9, 17):
            frame[y][x] = STONE
    for y in range(15, 19):
        for x in range(8, 17):
            frame[y][x] = OUTLINE
    for y in range(21, 24):
        for x in range(7, 19):
            frame[y][x] = (98, 81, 93)
    return frame


def test_embedded_idle_base_authors_a_cross_dimension_swing_plan(tmp_path: Path) -> None:
    """C2: a 16x24 idle base embeds onto the 24x24 swing canvas before authoring."""
    prepared = pb.prepare_cell_author("idle", tmp_path)
    base_frames = _load_base_release_frames(prepared.base_bundle, "swing")
    assert len(base_frames) == 4
    for frame in base_frames:
        assert len(frame) == 24
        assert len(frame[0]) == 24

    pose_plan = _swing_pose_plan(
        frame_ops=[
            [{"op": "paint", "x": 2, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}],
            [{"op": "paint", "x": 2, "y": 23, "palette_role": "amber-emission", "color": "#F0A33A"}],
            [{"op": "paint", "x": 21, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}],
            [{"op": "paint", "x": 21, "y": 23, "palette_role": "amber-emission", "color": "#F0A33A"}],
        ]
    )
    palette = load_master_palette(PALETTE_PATH)
    result = author_motion(base_frames, pose_plan, _load_identity_lock_spec(), palette)

    assert len(result.frames) == 4
    for frame in result.frames:
        assert len(frame) == 24
        assert len(frame[0]) == 24
    assert result.frames[0][22][2] == (240, 163, 58)


def test_direct_locked_write_rejects_with_identity_lock_write() -> None:
    base = _swing_base_frame()
    pose_plan = _swing_pose_plan(
        frame_ops=[[{"op": "clear", "x": 12, "y": 5}]],
    )
    palette = load_master_palette(PALETTE_PATH)
    with pytest.raises(MotionAuthorError) as exc:
        author_motion([base], pose_plan, _load_identity_lock_spec(), palette)
    assert exc.value.reason_code == "identity_lock_write"


def test_permitted_lock_relocation_preserves_exact_cells() -> None:
    base = _swing_base_frame()
    before = {(x, y): base[y][x] for y in range(24) for x in range(24) if base[y][x] is not None}
    pose_plan = _swing_pose_plan(
        frame_ops=[[{"op": "relocate_lock", "lock_id": "helmet_face", "dx": 1, "dy": 0}]],
    )
    palette = load_master_palette(PALETTE_PATH)
    result = author_motion([base], pose_plan, _load_identity_lock_spec(), palette)
    after = {
        (x, y): result.frames[0][y][x]
        for y in range(24)
        for x in range(24)
        if result.frames[0][y][x] is not None
    }
    shifted = {
        (x + 1, y): color
        for (x, y), color in before.items()
        if 9 <= x <= 16 and 1 <= y <= 10
    }
    remaining = {
        (x, y): color
        for (x, y), color in before.items()
        if not (9 <= x <= 16 and 1 <= y <= 10)
    }
    assert after == {**remaining, **shifted}


def test_boot_relocation_rejects() -> None:
    base = _swing_base_frame()
    pose_plan = _swing_pose_plan(
        frame_ops=[[{"op": "relocate_lock", "lock_id": "boots", "dx": 0, "dy": 1}]],
    )
    palette = load_master_palette(PALETTE_PATH)
    with pytest.raises(MotionAuthorError) as exc:
        author_motion([base], pose_plan, _load_identity_lock_spec(), palette)
    assert exc.value.reason_code == "authoring_boundary_violation"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("unknown_role", "invalid_palette_role"),
        ("off_palette_color", "invalid_palette_role"),
        ("out_of_bounds_paint", "authoring_boundary_violation"),
        ("geometry_mismatch", "authoring_boundary_violation"),
    ],
)
def test_palette_and_geometry_fail_closed(mutation: str, reason_code: str) -> None:
    base = _frame_with_rect(16, 24, 4, 6, 11, 17, STONE)
    pose_plan = _walk_pose_plan(
        frame_ops=[[{"op": "paint", "x": 2, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}]],
    )
    if mutation == "unknown_role":
        pose_plan["frames"][0][0]["palette_role"] = "missing-role"
    elif mutation == "off_palette_color":
        pose_plan["frames"][0][0]["color"] = "#FFFFFF"
    elif mutation == "out_of_bounds_paint":
        pose_plan["frames"][0][0]["x"] = 20
    elif mutation == "geometry_mismatch":
        pose_plan["frame_size"] = [24, 24]
    palette = load_master_palette(PALETTE_PATH)
    with pytest.raises(MotionAuthorError) as exc:
        author_motion([base], pose_plan, _load_identity_lock_spec(), palette)
    assert exc.value.reason_code == reason_code


def test_author_motion_is_byte_deterministic_and_reports_geometry() -> None:
    width, height = 16, 24
    base = _frame_with_rect(width, height, 4, 6, 11, 17, STONE)
    pose_plan = _walk_pose_plan(
        frame_ops=[
            [{"op": "paint", "x": 2, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}],
            [{"op": "relocate_lock", "lock_id": "upper_body", "dx": 0, "dy": 1}],
            [{"op": "paint", "x": 3, "y": 20, "palette_role": "dark-outline", "color": "#111018"}],
            [
                {
                    "op": "stroke",
                    "x0": 2,
                    "y0": 20,
                    "x1": 6,
                    "y1": 23,
                    "palette_role": "dark-outline",
                    "color": "#1D1720",
                }
            ],
        ]
    )
    palette = load_master_palette(PALETTE_PATH)
    identity = _load_identity_lock_spec()
    first = author_motion([base], pose_plan, identity, palette)
    second = author_motion([base], pose_plan, identity, palette)

    assert packet_bytes(first.ledger) == packet_bytes(second.ledger)
    assert first.report == second.report
    assert first.frames == second.frames
    assert first.report["ledger_digest"] == hashlib.sha256(packet_bytes(first.ledger)).hexdigest()

    for index, frame in enumerate(first.frames):
        row = first.report["frames"][index]
        assert row["opaque_bbox"] == {
            "x0": _alpha_bbox(frame)[0],
            "y0": _alpha_bbox(frame)[1],
            "x1": _alpha_bbox(frame)[2],
            "y1": _alpha_bbox(frame)[3],
        }
        column_loads = _opaque_column_loads(frame)
        assert row["opaque_column_loads"] == column_loads
        assert row["changed_cell_count"] == _changed_cell_count(base, frame)


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


def test_cli_calls_author_motion_and_writes_only_declared_outputs(tmp_path: Path) -> None:
    width, height = 16, 24
    base = _frame_with_rect(width, height, 4, 6, 11, 17, STONE)
    base_bundle = tmp_path / "base"
    base_bundle.mkdir()
    write_cells(base_bundle / "frame-0.png", base)

    pose_plan_path = tmp_path / "pose-plan.json"
    pose_plan_path.write_text(
        json.dumps(
            _walk_pose_plan(
                frame_ops=[
                    [{"op": "paint", "x": 2, "y": 22, "palette_role": "amber-emission", "color": "#F0A33A"}],
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
            str(base_bundle),
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
    assert payload["frame_count"] == 1
    assert (frames_out / "frame-0.png").is_file()
    assert ledger_out.is_file()
    authored = read_cells(frames_out / "frame-0.png", size=(width, height))
    assert authored[22][2] == (240, 163, 58)
    assert not (tmp_path / "manifest.json").exists()


def test_package_json_declares_strip_author_script() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["strip:author"] == "PYTHONPATH=. python3 -m pipeline.motion_author_cli"
