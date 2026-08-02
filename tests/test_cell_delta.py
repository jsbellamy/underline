"""Cell-delta ledger build, validate, and replay (issue #276)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from pipeline.canonical import packet_bytes
from pipeline.cell_delta import (
    CellDeltaError,
    assert_cell_delta_replay,
    build_cell_delta_ledger,
    replay_cell_delta_ledger,
    validate_cell_delta_ledger,
)
from pipeline.cell_raster import write_cells
from pipeline.gate_evidence import sha256_file

SCHEMA = "cell-delta-ledger/0"
SPEC_ID = "first-room/dwarf/idle"


def _blank_frame(width: int, height: int) -> list[list[tuple[int, int, int] | None]]:
    return [[None for _ in range(width)] for _ in range(height)]


def _frame_with_cell(
    width: int,
    height: int,
    x: int,
    y: int,
    rgb: tuple[int, int, int],
) -> list[list[tuple[int, int, int] | None]]:
    frame = _blank_frame(width, height)
    frame[y][x] = rgb
    return frame


def test_build_ledger_binds_base_frames_mapping_and_rgba_deltas(tmp_path: Path) -> None:
    width, height = 16, 24
    base = _blank_frame(width, height)
    target_changed = copy.deepcopy(base)
    target_changed[11][5] = (140, 96, 64)
    mapping = [0, 0, 0, 0]
    targets = [
        target_changed,
        copy.deepcopy(base),
        copy.deepcopy(base),
        copy.deepcopy(base),
    ]
    base_path = tmp_path / "base.png"
    write_cells(base_path, base)

    ledger = build_cell_delta_ledger(
        [base],
        targets,
        base_specification_id=SPEC_ID,
        base_frame_mapping=mapping,
    )

    assert ledger["schema"] == SCHEMA
    assert ledger["base_specification_id"] == SPEC_ID
    assert ledger["base_frames_sha256"] == [sha256_file(base_path)]
    assert ledger["base_frame_mapping"] == mapping
    assert ledger["target_frame_count"] == 4
    assert ledger["deltas"] == [
        {
            "frame": 0,
            "x": 5,
            "y": 11,
            "from": [0, 0, 0, 0],
            "to": [140, 96, 64, 255],
        }
    ]


def test_build_ledger_is_canonical_and_coordinate_sorted() -> None:
    width, height = 8, 8
    base = _blank_frame(width, height)
    target0 = copy.deepcopy(base)
    target0[1][2] = (10, 20, 30)
    target0[3][1] = (40, 50, 60)
    target1 = copy.deepcopy(base)
    target1[0][0] = (1, 2, 3)
    targets = [target0, target1]
    mapping = [0, 0]

    first = build_cell_delta_ledger(
        [base],
        targets,
        base_specification_id=SPEC_ID,
        base_frame_mapping=mapping,
    )
    second = build_cell_delta_ledger(
        [base],
        targets,
        base_specification_id=SPEC_ID,
        base_frame_mapping=mapping,
    )
    assert packet_bytes(first) == packet_bytes(second)
    coords = [(row["frame"], row["y"], row["x"]) for row in first["deltas"]]
    assert coords == sorted(coords)


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("unknown_schema", "invalid_cell_delta_ledger_schema"),
        ("malformed_digest", "invalid_cell_delta_ledger_digest"),
        ("invalid_mapping_index", "invalid_cell_delta_ledger_mapping"),
        ("inconsistent_target_count", "invalid_cell_delta_ledger_target_count"),
        ("non_binary_alpha", "invalid_cell_delta_ledger_alpha"),
        ("duplicate_row", "invalid_cell_delta_ledger_duplicate"),
        ("unsorted_row", "invalid_cell_delta_ledger_order"),
        ("out_of_bounds", "invalid_cell_delta_ledger_bounds"),
        ("wrong_from", "invalid_cell_delta_ledger_from"),
        ("noop_row", "invalid_cell_delta_ledger_noop"),
        ("base_hash_mismatch", "base_frame_hash_mismatch"),
    ],
)
def test_validate_rejects_malformed_ledger(mutation: str, reason_code: str) -> None:
    width, height = 4, 4
    base = _blank_frame(width, height)
    target = copy.deepcopy(base)
    target[1][1] = (1, 2, 3)
    ledger = build_cell_delta_ledger(
        [base],
        [target],
        base_specification_id=SPEC_ID,
        base_frame_mapping=[0],
    )

    if mutation == "unknown_schema":
        ledger["schema"] = "cell-delta-ledger/1"
    elif mutation == "malformed_digest":
        ledger["base_frames_sha256"] = ["not-a-hex-digest"]
    elif mutation == "invalid_mapping_index":
        ledger = build_cell_delta_ledger(
            [base],
            [base],
            base_specification_id=SPEC_ID,
            base_frame_mapping=[0],
        )
        ledger["base_frame_mapping"] = [99]
    elif mutation == "inconsistent_target_count":
        ledger["target_frame_count"] = 99
    elif mutation == "non_binary_alpha":
        ledger["deltas"][0]["to"] = [1, 2, 3, 128]
    elif mutation == "duplicate_row":
        ledger["deltas"] = ledger["deltas"] + [ledger["deltas"][0]]
    elif mutation == "unsorted_row":
        target2 = copy.deepcopy(base)
        target2[2][2] = (4, 5, 6)
        ledger = build_cell_delta_ledger(
            [base],
            [target, target2],
            base_specification_id=SPEC_ID,
            base_frame_mapping=[0, 0],
        )
        ledger["deltas"] = list(reversed(ledger["deltas"]))
    elif mutation == "out_of_bounds":
        ledger["deltas"][0]["x"] = 99
    elif mutation == "wrong_from":
        ledger["deltas"][0]["from"] = [255, 255, 255, 255]
    elif mutation == "noop_row":
        ledger["deltas"][0]["to"] = list(ledger["deltas"][0]["from"])
    elif mutation == "base_hash_mismatch":
        ledger["base_frames_sha256"] = ["0000000000000000000000000000000000000000000000000000000000000000"]

    with pytest.raises(CellDeltaError) as exc:
        validate_cell_delta_ledger([base], ledger)
    assert exc.value.reason_code == reason_code


def test_ledger_round_trips_exact_frames() -> None:
    width, height = 6, 6
    base0 = _frame_with_cell(width, height, 1, 1, (10, 20, 30))
    base1 = _blank_frame(width, height)
    target0 = copy.deepcopy(base0)
    target0[2][2] = (40, 50, 60)
    target1 = _frame_with_cell(width, height, 3, 3, (70, 80, 90))
    targets = [target0, target1]
    mapping = [0, 1]
    ledger = build_cell_delta_ledger(
        [base0, base1],
        targets,
        base_specification_id=SPEC_ID,
        base_frame_mapping=mapping,
    )
    replayed = replay_cell_delta_ledger([base0, base1], ledger)
    assert replayed == targets
    assert_cell_delta_replay([base0, base1], targets, ledger)


def test_replay_reports_first_divergent_coordinate() -> None:
    width, height = 4, 4
    base = _blank_frame(width, height)
    target = copy.deepcopy(base)
    target[1][2] = (5, 6, 7)
    wrong = copy.deepcopy(target)
    wrong[2][1] = (8, 9, 10)
    ledger = build_cell_delta_ledger(
        [base],
        [target],
        base_specification_id=SPEC_ID,
        base_frame_mapping=[0],
    )
    with pytest.raises(CellDeltaError) as exc:
        assert_cell_delta_replay([base], [wrong], ledger)
    assert exc.value.reason_code == "cell_delta_replay_mismatch"
    assert exc.value.frame == 0
    assert exc.value.x == 1
    assert exc.value.y == 2


def test_build_does_not_mutate_input_frames() -> None:
    width, height = 4, 4
    base = _blank_frame(width, height)
    target = copy.deepcopy(base)
    target[0][0] = (1, 2, 3)
    base_snapshot = copy.deepcopy(base)
    target_snapshot = copy.deepcopy(target)
    build_cell_delta_ledger(
        [base],
        [target],
        base_specification_id=SPEC_ID,
        base_frame_mapping=[0],
    )
    assert base == base_snapshot
    assert target == target_snapshot


def test_base_frame_hash_matches_write_cells_png(tmp_path: Path) -> None:
    width, height = 4, 4
    base = _frame_with_cell(width, height, 1, 1, (12, 34, 56))
    path = tmp_path / "frame.png"
    write_cells(path, base)
    ledger = build_cell_delta_ledger(
        [base],
        [base],
        base_specification_id=SPEC_ID,
        base_frame_mapping=[0],
    )
    assert ledger["base_frames_sha256"] == [sha256_file(path)]
