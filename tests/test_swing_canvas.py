"""Tests for the swing action canvas spike prototype."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype" / "swing-canvas"))

import canvas  # noqa: E402

SCOREBOARD_PATH = ROOT / "prototype" / "swing-canvas" / "out" / "scoreboard.json"

ISSUE_BASELINE = {
    "walk": {
        "occupancy": [0.396, 0.391, 0.367, 0.393],
        "edge_left": [0, 0, 0, 0],
        "edge_right": [0, 0, 0, 0],
    },
    "idle": {
        "occupancy": [0.698, 0.701, 0.677, 0.688],
    },
    "swing": {
        "occupancy": [0.461, 0.393, 0.401, 0.333],
        "edge_left": [0, 2, 11, 7],
        "edge_right": [0, 6, 4, 0],
        "alpha_bbox": [
            "x1-14 y1-23",
            "x0-15 y8-23",
            "x0-15 y9-23",
            "x0-14 y10-23",
        ],
    },
}


def _grid(rows: list[str]) -> canvas.CellGrid:
    return [[None if ch == "." else (1, 1, 1) for ch in row] for row in rows]


def test_static_silhouette_fraction_hand_worked() -> None:
    a = _grid(["#.", ".#"])
    b = _grid([".#", "#."])
    assert canvas.static_silhouette_fraction(a, b) == 0.0
    assert canvas.static_silhouette_fraction(a, a) == 1.0


def test_expand_canvas_preserves_body_origin() -> None:
    source = _grid(
        [
            "................",
            "......##........",
            "................",
        ]
    )
    expanded = canvas.expand_canvas(
        source,
        canvas_w=24,
        canvas_h=3,
        left_pad=4,
    )
    assert expanded[1][10:12] == [(1, 1, 1), (1, 1, 1)]
    assert expanded[1][4] is None


def test_flood_tool_mask_follows_roles_from_grip() -> None:
    roles = [
        [None, None, None],
        [None, "skin", "earth-leather-beard"],
        [None, "earth-leather-beard", "blue-metal"],
    ]
    mask = canvas.flood_tool_mask(roles, [(2, 1)])
    assert mask[1][2] is True
    assert mask[2][1] is True
    assert mask[2][2] is True
    assert mask[1][1] is False


def test_measure_frame_reports_boundary_counts() -> None:
    cells = _grid(
        [
            "#...............",
            "#...............",
            "................",
        ]
    )
    measured = canvas.measure_frame(cells)
    assert measured.boundary_left == 2
    assert measured.boundary_right == 0
    assert measured.alpha_bbox.format() == "x0-0 y0-1"


@pytest.fixture(scope="module")
def scoreboard() -> dict[str, object]:
    assert SCOREBOARD_PATH.is_file(), "run npm run prototype:swing-canvas first"
    return json.loads(SCOREBOARD_PATH.read_text(encoding="utf-8"))


def test_scoreboard_baseline_swing_matches_contract(scoreboard: dict[str, object]) -> None:
    swing = scoreboard["baseline"]["swing"]
    per_frame = swing["per_frame"]
    for index, expected_occ in enumerate(ISSUE_BASELINE["swing"]["occupancy"]):
        assert per_frame[index]["occupancy"] == expected_occ
        assert per_frame[index]["alpha_bbox"] == ISSUE_BASELINE["swing"]["alpha_bbox"][index]
    assert swing["edge_load"]["left"] == ISSUE_BASELINE["swing"]["edge_left"]
    assert swing["edge_load"]["right"] == ISSUE_BASELINE["swing"]["edge_right"]


def test_scoreboard_baseline_idle_and_walk_occupancy(scoreboard: dict[str, object]) -> None:
    for motion in ("walk", "idle"):
        per_frame = scoreboard["baseline"][motion]["per_frame"]
        for index, expected in enumerate(ISSUE_BASELINE[motion]["occupancy"]):
            assert per_frame[index]["occupancy"] == expected
    walk = scoreboard["baseline"]["walk"]
    assert walk["edge_load"]["left"] == ISSUE_BASELINE["walk"]["edge_left"]
    assert walk["edge_load"]["right"] == ISSUE_BASELINE["walk"]["edge_right"]


def test_scoreboard_variants_include_all_candidates(scoreboard: dict[str, object]) -> None:
    variants = scoreboard["variants"]
    assert set(variants) == {"24x24", "32x24", "overlay"}
    for variant in variants.values():
        assert len(variant["per_frame"]) == 4
        assert set(variant["static_silhouette_fraction"]) == {"0-1", "1-2", "2-3", "3-0"}
    overlay = variants["overlay"]
    assert len(overlay["separation"]) == 4
    assert overlay["separation"][3]["status"] == "failed"


def test_24x24_clears_boundary_columns(scoreboard: dict[str, object]) -> None:
    for frame in scoreboard["variants"]["24x24"]["per_frame"]:
        assert frame["boundary_columns"]["left"] == 0
        assert frame["boundary_columns"]["right"] == 0


def test_prototype_swing_canvas_command_writes_complete_artifacts_outside_the_checkout(
    tmp_path: Path,
) -> None:
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'prototype' / 'swing-canvas'}:{ROOT}"}
    out_dir = tmp_path / "swing-canvas"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "prototype" / "swing-canvas" / "run.py"),
            "--out-dir",
            str(out_dir),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    scoreboard_path = out_dir / "scoreboard.json"
    assert str(scoreboard_path) in result.stdout
    generated = json.loads(scoreboard_path.read_text(encoding="utf-8"))
    assert set(generated["variants"]) == {"24x24", "32x24", "overlay"}
    assert len(list((out_dir / "variants").glob("*/*.png"))) == 24
