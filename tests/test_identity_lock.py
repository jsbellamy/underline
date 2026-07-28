"""Behavioral proof for pipeline.identity_lock (issue #125)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import (
    DEFAULT_IDENTITY_LOCKS_PATH,
    DEFAULT_IDENTITY_PATH,
    IDENTITY_LOCK_SCHEMA,
    SEED_HEIGHT,
    SEED_WIDTH,
    build_identity_seed,
    evaluate_identity_lock,
    identity_lock_applies,
    identity_lock_report_payload,
    load_canonical_cells,
    load_identity_lock_spec,
    validate_identity_lock_spec,
)
from pipeline.recovery import MAGENTA

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
CANONICAL_IDENTITY_SHA = "db68353f559053abc4d77e8916d1db8a242f4f50eb4a1ef0d4b1f65c4bf650c9"


def _canonical_frames() -> list[list[list[tuple[int, int, int] | None]]]:
    cells = load_canonical_cells(IDENTITY_PNG, (16, 24))
    return [copy.deepcopy(cells) for _ in range(4)]


def _set_cell(
    frames: list[list[list[tuple[int, int, int] | None]]],
    frame_index: int,
    x: int,
    y: int,
    value: tuple[int, int, int] | None,
) -> None:
    frames[frame_index][y][x] = value


def test_schema_validates_canonical_hash_geometry_offsets_and_exact_rgba() -> None:
    spec = load_identity_lock_spec(DEFAULT_IDENTITY_LOCKS_PATH)
    assert spec["schema"] == IDENTITY_LOCK_SCHEMA
    assert spec["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert spec["frame_size"] == [16, 24]
    assert spec["comparison"] == "exact-rgba"
    walk = spec["motion_classes"]["walk"]["locks"][0]
    assert walk["rectangle"] == {"x0": 0, "x1": 15, "y0": 1, "y1": 18}
    assert walk["permitted_offsets"] == [[0, -1], [0, 0], [0, 1]]
    swing = spec["motion_classes"]["swing"]
    assert swing["locks"][0]["id"] == "helmet_face"
    assert swing["locks"][2]["permitted_offsets"] == [[0, 0]]


def test_context_md_defines_identity_lock() -> None:
    text = (ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    assert "**Identity Lock**" in text
    assert "external canonical identity" in text
    assert "coherence Gates" in text
    assert "Identity Lock compares every Frame to an external canonical identity" in text


@pytest.mark.parametrize("offset", [(0, -1), (0, 0), (0, 1)])
def test_walk_permitted_offsets_pass(offset: tuple[int, int]) -> None:
    canonical = load_canonical_cells(IDENTITY_PNG, (16, 24))
    frames: list[list[list[tuple[int, int, int] | None]]] = []
    dx, dy = offset
    for _ in range(4):
        shifted = copy.deepcopy(canonical)
        for y in range(1, 19):
            for x in range(16):
                target_y = y + dy
                if 0 <= target_y < 24:
                    shifted[target_y][x] = canonical[y][x]
        frames.append(shifted)
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "PASS"
    assert result.first_mismatch is None


def test_walk_locked_opaque_cell_change_fails() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 0, 8, 5, (1, 2, 3))
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "FAIL"
    assert result.first_mismatch is not None
    assert result.first_mismatch.anchor == "upper_body"


def test_walk_locked_transparent_cell_change_fails() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 1, 10, 8, (40, 41, 42))
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "FAIL"


def test_walk_locked_rgba_change_fails() -> None:
    frames = _canonical_frames()
    original = frames[2][12][6]
    assert original is not None
    _set_cell(frames, 2, 6, 12, (original[0] + 1, original[1], original[2]))
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "FAIL"


def test_swing_permitted_anchor_motion_passes() -> None:
    canonical = load_canonical_cells(IDENTITY_PNG, (16, 24))
    frames: list[list[list[tuple[int, int, int] | None]]] = []
    for _ in range(4):
        shifted = copy.deepcopy(canonical)
        for y in range(1, 11):
            for x in range(5, 13):
                shifted[y - 1][x] = canonical[y][x]
        frames.append(shifted)
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "PASS"


def test_swing_anchor_tamper_fails() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 0, 7, 4, (9, 9, 9))
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"
    assert result.first_mismatch is not None
    assert result.first_mismatch.anchor == "helmet_face"


def test_swing_boot_movement_fails() -> None:
    canonical = load_canonical_cells(IDENTITY_PNG, (16, 24))
    frames = _canonical_frames()
    for y in range(21, 24):
        for x in range(3, 15):
            cell = canonical[y][x]
            if cell is not None:
                _set_cell(frames, 0, x, y, (cell[0] ^ 1, cell[1], cell[2]))
                break
        else:
            continue
        break
    else:
        raise AssertionError("no opaque boot cell in canonical identity")
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"
    assert result.first_mismatch is not None
    assert result.first_mismatch.anchor == "boots"


def test_swing_excess_offset_fails() -> None:
    frames = _canonical_frames()
    for frame_index in range(4):
        for y in range(1, 11):
            for x in range(5, 13):
                frames[frame_index][y][x] = frames[frame_index][y - 2][x]
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"


def test_swing_scale_relation_change_fails() -> None:
    frames = _canonical_frames()
    for frame_index in range(4):
        for y in range(1, 11):
            for x in range(5, 13):
                frames[frame_index][y][x] = frames[frame_index][y - 1][x]
        for y in range(15, 19):
            for x in range(4, 13):
                frames[frame_index][y][x] = frames[frame_index][y + 2][x]
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"


def test_identity_lock_report_payload_shape() -> None:
    frames = _canonical_frames()
    result = evaluate_identity_lock(frames, "walk")
    payload = identity_lock_report_payload(result)
    assert payload["outcome"] == "PASS"
    assert payload["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert payload["lock_spec_sha256"] == sha256_file(DEFAULT_IDENTITY_LOCKS_PATH)
    assert payload["motion_class"] == "walk"
    assert len(payload["per_frame"]) == 4
    assert payload["per_frame"][0]["anchor_results"]["upper_body"] == "PASS"
    assert payload["per_frame"][0]["first_mismatch"] is None


def test_seed_dimensions_frame_equality_magenta_gutters_no_margins(tmp_path: Path) -> None:
    out_path = tmp_path / "seed.png"
    meta = build_identity_seed(IDENTITY_PNG, out_path)
    assert meta["dimensions"] == [SEED_WIDTH, SEED_HEIGHT]
    assert out_path.is_file()

    with Image.open(out_path) as canvas:
        assert canvas.size == (SEED_WIDTH, SEED_HEIGHT)
        pixels = canvas.load()
        assert pixels is not None
        scaled_w = 16 * 16
        gutter_px = 2 * 16
        for frame_index in range(4):
            frame_x = frame_index * (scaled_w + gutter_px)
            with Image.open(IDENTITY_PNG) as identity:
                identity_rgba = identity.convert("RGBA")
                expected = identity_rgba.resize((scaled_w, SEED_HEIGHT), Image.Resampling.NEAREST)
                expected_pixels = expected.load()
                for y in range(SEED_HEIGHT):
                    for x in range(scaled_w):
                        assert pixels[frame_x + x, y] == expected_pixels[x, y]
        gutter_start = scaled_w
        for y in range(SEED_HEIGHT):
            for x in range(gutter_start, gutter_start + gutter_px):
                assert pixels[x, y][:3] == MAGENTA
        trailing_start = 4 * scaled_w + 3 * gutter_px
        for y in range(SEED_HEIGHT):
            for x in range(trailing_start, SEED_WIDTH):
                assert pixels[x, y][:3] == MAGENTA


def test_seed_rerun_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "seed-a.png"
    second = tmp_path / "seed-b.png"
    build_identity_seed(IDENTITY_PNG, first)
    build_identity_seed(IDENTITY_PNG, second)
    assert first.read_bytes() == second.read_bytes()


def test_identity_lock_applies_only_to_dwarf_walk_swing() -> None:
    assert identity_lock_applies("dwarf-miner", "walk")
    assert identity_lock_applies("dwarf-miner", "swing")
    assert not identity_lock_applies("dwarf-miner", "idle")
    assert not identity_lock_applies("miner", "walk")


def test_invalid_spec_rejects_bad_hash(tmp_path: Path) -> None:
    bad = json.loads(DEFAULT_IDENTITY_LOCKS_PATH.read_text())
    bad["identity_sha256"] = "0" * 64
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad))
    with pytest.raises(Exception):
        validate_identity_lock_spec(bad, spec_path=bad_path)
