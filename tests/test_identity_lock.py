"""Behavioral proof for pipeline.identity_lock (issues #125 and #133)."""

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
    IdentityLockError,
    build_identity_seed,
    evaluate_identity_lock,
    identity_lock_applies,
    identity_lock_report_payload,
    load_canonical_cells,
    load_identity_lock_spec,
    nearest_palette_role,
    validate_identity_lock_spec,
)

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
IDLE_PROVIDER_SOURCE = (
    ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
)
CANONICAL_IDENTITY_SHA = "db68353f559053abc4d77e8916d1db8a242f4f50eb4a1ef0d4b1f65c4bf650c9"
METRIC_ABS_TOLERANCE = 1e-12


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


def test_schema_validates_structural_policy_palette_landmarks_and_grounded_anchor() -> None:
    spec = load_identity_lock_spec(DEFAULT_IDENTITY_LOCKS_PATH)
    assert spec["schema"] == IDENTITY_LOCK_SCHEMA == "identity-lock/1"
    assert spec["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert spec["frame_size"] == [16, 24]
    assert spec["master_palette"]["relative_path"] == "assets/palettes/first-room.json"
    assert len(spec["master_palette"]["sha256"]) == 64
    walk = spec["motion_classes"]["walk"]["locks"][0]
    assert walk["rectangle"] == {"x0": 0, "x1": 15, "y0": 1, "y1": 18}
    assert walk["permitted_offsets"] == [[0, -1], [0, 0], [0, 1]]
    assert walk["comparison"] == "registered-structure"
    assert walk["max_occupancy_difference"] == 0.20
    assert walk["max_palette_role_distance"] == 0.20
    expected_landmarks = [
        {
            "id": "lamp",
            "canonical": [12, 4],
            "palette_role": "amber-emission",
            "max_distance": 2,
        },
        {
            "id": "eye",
            "canonical": [10, 7],
            "palette_role": "dark-outline",
            "max_distance": 1,
        },
        {
            "id": "buckle",
            "canonical": [11, 16],
            "palette_role": "amber-emission",
            "max_distance": 2,
        },
    ]
    assert spec["motion_classes"]["walk"]["landmarks"] == expected_landmarks
    swing = spec["motion_classes"]["swing"]
    assert swing["locks"][0]["id"] == "helmet_face"
    assert swing["locks"][0]["comparison"] == "registered-structure"
    assert swing["locks"][2]["comparison"] == "exact-occupancy"
    assert swing["locks"][2]["permitted_offsets"] == [[0, 0]]
    assert swing["landmarks"] == expected_landmarks


def test_palette_role_ties_resolve_by_palette_file_order() -> None:
    equidistant = (1, 0, 0)
    assert nearest_palette_role(
        equidistant,
        [("first", (0, 0, 0)), ("second", (2, 0, 0))],
    ) == "first"
    assert nearest_palette_role(
        equidistant,
        [("second", (2, 0, 0)), ("first", (0, 0, 0))],
    ) == "second"


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


def test_walk_registered_structure_allows_same_role_rgb_variation() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 0, 3, 12, (120, 166, 99))
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "PASS"
    check = result.per_frame[0].check_results["upper_body"]
    assert check["occupancy_difference"] == 0.0
    assert check["palette_role_distance"] == 0.0


def test_walk_registered_structure_allows_limited_occupancy_change() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 1, 15, 1, (17, 16, 24))
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "PASS"
    check = result.per_frame[1].check_results["upper_body"]
    assert check["outcome"] == "PASS"
    assert check["occupancy_difference"] == 1 / 212
    assert check["palette_role_distance"] == pytest.approx(
        38 / 11183,
        abs=METRIC_ABS_TOLERANCE,
    )


def test_walk_large_occupancy_change_fails_registered_structure() -> None:
    frames = _canonical_frames()
    for y in range(1, 19):
        for x in range(8):
            _set_cell(frames, 2, x, y, None)
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "FAIL"
    check = result.per_frame[2].check_results["upper_body"]
    assert check["outcome"] == "FAIL"
    assert check["occupancy_difference"] == 105 / 218
    assert check["palette_role_distance"] == pytest.approx(
        2663 / 25320,
        abs=METRIC_ABS_TOLERANCE,
    )


def test_walk_palette_role_drift_fails_registered_structure() -> None:
    frames = _canonical_frames()
    changed = 0
    for y in range(1, 19):
        for x in range(16):
            if frames[3][y][x] is not None and changed < 80:
                _set_cell(frames, 3, x, y, (114, 226, 210))
                changed += 1
    result = evaluate_identity_lock(frames, "walk")
    assert result.outcome == "FAIL"
    check = result.per_frame[3].check_results["upper_body"]
    assert check["outcome"] == "FAIL"
    assert check["occupancy_difference"] == 0.0
    assert check["palette_role_distance"] == pytest.approx(
        79 / 211,
        abs=METRIC_ABS_TOLERANCE,
    )


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


def test_swing_registered_anchor_allows_non_identical_rgb() -> None:
    frames = _canonical_frames()
    _set_cell(frames, 0, 7, 4, (47, 96, 117))
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "PASS"
    assert result.per_frame[0].check_results["helmet_face"]["palette_role_distance"] == 0.0


def test_swing_boot_rgb_change_passes_exact_occupancy() -> None:
    frames = _canonical_frames()
    original = frames[0][23][4]
    assert original is not None
    _set_cell(frames, 0, 4, 23, (original[0] ^ 1, original[1], original[2]))
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "PASS"
    boots = result.per_frame[0].check_results["boots"]
    assert boots["comparison"] == "exact-occupancy"
    assert boots["palette_role_distance"] is None


def test_swing_boot_occupancy_change_fails() -> None:
    canonical = load_canonical_cells(IDENTITY_PNG, (16, 24))
    frames = _canonical_frames()
    for y in range(21, 24):
        for x in range(3, 15):
            cell = canonical[y][x]
            if cell is not None:
                _set_cell(frames, 0, x, y, None)
                break
        else:
            continue
        break
    else:
        raise AssertionError("no opaque boot cell in canonical identity")
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"
    assert result.per_frame[0].check_results["boots"]["outcome"] == "FAIL"


def test_missing_eye_landmark_fails() -> None:
    frames = _canonical_frames()
    for y in range(6, 9):
        for x in range(9, 12):
            if frames[0][y][x] is not None:
                _set_cell(frames, 0, x, y, (240, 163, 58))
    result = evaluate_identity_lock(frames, "swing")
    assert result.outcome == "FAIL"
    landmark = result.per_frame[0].landmark_results["eye"]
    assert landmark["outcome"] == "FAIL"
    assert landmark["actual_position"] is None
    assert landmark["expected_role"] == "dark-outline"
    assert landmark["actual_role"] == "amber-emission"
    assert result.per_frame[0].first_failure["kind"] == "landmark"


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
    upper_body = payload["per_frame"][0]["check_results"]["upper_body"]
    assert upper_body["comparison"] == "registered-structure"
    assert upper_body["occupancy_difference"] == 0.0
    assert upper_body["palette_role_distance"] == 0.0
    lamp = payload["per_frame"][0]["landmark_results"]["lamp"]
    assert lamp["outcome"] == "PASS"
    assert lamp["expected_role"] == lamp["actual_role"] == "amber-emission"
    assert payload["per_frame"][0]["first_failure"] is None
    assert payload["per_frame"][0]["first_mismatch"] is None
    assert payload["first_failure"] is None


def test_palette_failure_report_names_truthful_first_failure() -> None:
    frames = _canonical_frames()
    changed = 0
    for y in range(1, 19):
        for x in range(16):
            near_landmark = (
                max(abs(x - 12), abs(y - 4)) <= 2
                or max(abs(x - 10), abs(y - 7)) <= 1
                or max(abs(x - 11), abs(y - 16)) <= 2
            )
            if near_landmark:
                continue
            if frames[0][y][x] is not None and changed < 80:
                _set_cell(frames, 0, x, y, (114, 226, 210))
                changed += 1
    payload = identity_lock_report_payload(evaluate_identity_lock(frames, "walk"))
    failure = payload["per_frame"][0]["first_failure"]
    assert failure["kind"] == "check"
    assert failure["id"] == "upper_body"
    assert failure["occupancy_difference"] == 0.0
    assert failure["palette_role_distance"] == pytest.approx(
        79 / 211,
        abs=METRIC_ABS_TOLERANCE,
    )
    assert payload["per_frame"][0]["first_mismatch"] is None
    assert payload["first_failure"]["frame_index"] == 0


def test_evaluation_rejects_unbound_identity_image(tmp_path: Path) -> None:
    altered_identity = tmp_path / "identity.png"
    with Image.open(IDENTITY_PNG) as source:
        altered = source.convert("RGBA")
    altered.putpixel((0, 0), (1, 2, 3, 255))
    altered.save(altered_identity)

    with pytest.raises(IdentityLockError, match="bound identity_sha256"):
        evaluate_identity_lock(
            _canonical_frames(),
            "walk",
            identity_path=altered_identity,
        )


def test_seed_is_byte_identical_copy_of_bound_generation_source(tmp_path: Path) -> None:
    out_path = tmp_path / "seed.png"
    meta = build_identity_seed(IDENTITY_JSON, out_path)
    assert meta["dimensions"] == [1536, 1024]
    assert out_path.is_file()
    assert out_path.read_bytes() == IDLE_PROVIDER_SOURCE.read_bytes()
    assert meta["generation_source_path"] == str(IDLE_PROVIDER_SOURCE.resolve())
    assert meta["identity_anchor_path"] == str(IDENTITY_PNG.resolve())
    assert meta["generation_source_sha256"] == sha256_file(IDLE_PROVIDER_SOURCE)
    assert meta["identity_anchor_sha256"] == CANONICAL_IDENTITY_SHA


def test_seed_rerun_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "seed-a.png"
    second = tmp_path / "seed-b.png"
    build_identity_seed(IDENTITY_JSON, first)
    build_identity_seed(IDENTITY_JSON, second)
    assert first.read_bytes() == second.read_bytes()


def test_seed_rejects_release_identity_as_generation_source(tmp_path: Path) -> None:
    with pytest.raises(IdentityLockError, match="identity declaration"):
        build_identity_seed(IDENTITY_PNG, tmp_path / "seed.png")


def test_seed_rejects_generation_source_hash_mismatch(tmp_path: Path) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration["generation_source"]["sha256"] = "0" * 64
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))

    with pytest.raises(IdentityLockError, match="generation source hash"):
        build_identity_seed(declaration_path, tmp_path / "seed.png")


def test_seed_rejects_missing_generation_source_binding(tmp_path: Path) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration.pop("generation_source")
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))

    with pytest.raises(IdentityLockError, match="generation_source"):
        build_identity_seed(declaration_path, tmp_path / "seed.png")


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
