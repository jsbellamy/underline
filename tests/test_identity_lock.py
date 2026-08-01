"""Behavioral proof for pipeline.identity_lock (issues #125 and #133)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pipeline.cell_raster import read_cells, write_cells
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import (
    DEFAULT_IDENTITY_LOCKS_PATH,
    IDENTITY_LOCK_NEAR_MISS_SCHEMA,
    IDENTITY_LOCK_SCHEMA,
    IDENTITY_LOCK_SCHEMA_V2,
    FrameIdentityLockResult,
    IdentityLockError,
    IdentityLockMismatch,
    IdentityLockResult,
    build_identity_seed,
    evaluate_identity_lock,
    expected_image_edit_source_sha256,
    identity_lock_applies,
    identity_lock_rejection_detail,
    identity_lock_report_payload,
    load_canonical_cells,
    load_identity_lock_spec,
    nearest_palette_role,
    validate_identity_lock_spec,
)

from pipeline.palette_quantize import load_master_palette, quantize_cells

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDENTITY_ROLES_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity-roles.json"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
IDLE_PROVIDER_SOURCE = (
    ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
)
# The retired soft-shaded identity survives untouched as the idle draft Frame 0;
# it is the quantization input the committed role map was authored against (#179).
SOFT_SHADED_SOURCE_PNG = (
    ROOT / "assets" / "first-room" / "dwarf" / "idle" / "draft" / "frame-0.png"
)
CANONICAL_IDENTITY_SHA = "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
PRE_CLEANUP_IDENTITY_CELL_SHA = (
    "cabcc1ff3725dcb3370d0e699ef7ac1af1db5ea1a3e9e6dbee03cc08806ff2f9"
)
BEARD_CHEST_RECT = {"x0": 10, "x1": 13, "y0": 6, "y1": 14}
LANDMARK_COORDS = {
    "lamp": (12, 4),
    "eye": (10, 7),
    "buckle": (11, 16),
}
LANDMARK_ROLES = {
    "lamp": "amber-emission",
    "eye": "dark-outline",
    "buckle": "amber-emission",
}
MASTER_PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
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
    assert spec["schema"] == IDENTITY_LOCK_SCHEMA_V2 == "identity-lock/2"
    assert spec["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert spec["frame_size"] == [16, 24]
    palette_exact = spec["palette_exact_identity"]
    assert palette_exact["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert palette_exact["relative_path"] == "assets/first-room/dwarf/identity.png"
    assert (
        palette_exact["role_map_relative_path"]
        == "assets/first-room/dwarf/identity-roles.json"
    )
    assert palette_exact["frame_size"] == [16, 24]
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
    # Re-baselined by #179: the mutation is scored against the canonical raster,
    # whose role composition changed when it became palette-exact. The alpha mask
    # did not change, so occupancy_difference is unchanged.
    assert check["palette_role_distance"] == pytest.approx(
        2840 / 25320,
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
    # Re-baselined by #179 with the palette-exact canonical raster; see above.
    assert check["palette_role_distance"] == pytest.approx(
        80 / 211,
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
    # Re-baselined by #179 with the palette-exact canonical raster; see above.
    assert failure["palette_role_distance"] == pytest.approx(
        80 / 211,
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
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration.pop("seed_pad_px", None)
    declaration_path = tmp_path / "identity-unpadded.json"
    declaration_path.write_text(json.dumps(declaration))
    out_path = tmp_path / "seed.png"
    meta = build_identity_seed(declaration_path, out_path)
    assert meta["dimensions"] == [1536, 1024]
    assert out_path.is_file()
    assert out_path.read_bytes() == IDLE_PROVIDER_SOURCE.read_bytes()
    assert meta["generation_source_path"] == str(IDLE_PROVIDER_SOURCE.resolve())
    assert meta["identity_anchor_path"] == str(IDENTITY_PNG.resolve())
    assert meta["generation_source_sha256"] == sha256_file(IDLE_PROVIDER_SOURCE)
    assert meta["identity_anchor_sha256"] == CANONICAL_IDENTITY_SHA


def test_checked_in_identity_seed_rerun_is_deterministic(tmp_path: Path) -> None:
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


def test_seed_with_seed_pad_px_adds_magenta_border_and_preserves_interior(
    tmp_path: Path,
) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration["seed_pad_px"] = 64
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))
    out_path = tmp_path / "seed.png"
    meta = build_identity_seed(declaration_path, out_path)

    with Image.open(IDLE_PROVIDER_SOURCE) as source:
        gen_w, gen_h = source.size
    assert meta["seed_pad_px"] == 64
    assert meta["dimensions"] == [gen_w + 128, gen_h + 128]
    assert meta["generation_source_sha256"] == sha256_file(IDLE_PROVIDER_SOURCE)
    assert meta["sha256"] != meta["generation_source_sha256"]

    with Image.open(out_path) as padded:
        rgba = np.asarray(padded.convert("RGBA"))
    pad = 64
    magenta = np.array([255, 0, 255, 255], dtype=np.uint8)
    assert np.all(rgba[:pad, :, :] == magenta)
    assert np.all(rgba[-pad:, :, :] == magenta)
    assert np.all(rgba[:, :pad, :] == magenta)
    assert np.all(rgba[:, -pad:, :] == magenta)
    with Image.open(IDLE_PROVIDER_SOURCE) as source:
        interior = np.asarray(source.convert("RGBA"))
    assert np.array_equal(rgba[pad:-pad, pad:-pad, :], interior)


def test_seed_with_seed_pad_px_rerun_is_deterministic(tmp_path: Path) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration["seed_pad_px"] = 64
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))
    first = tmp_path / "seed-a.png"
    second = tmp_path / "seed-b.png"
    first_meta = build_identity_seed(declaration_path, first)
    second_meta = build_identity_seed(declaration_path, second)
    assert first.read_bytes() == second.read_bytes()
    assert first_meta["sha256"] == second_meta["sha256"]


def test_seed_rejects_invalid_seed_pad_px(tmp_path: Path) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration["seed_pad_px"] = 0
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))

    with pytest.raises(IdentityLockError, match="seed_pad_px"):
        build_identity_seed(declaration_path, tmp_path / "seed.png")


def test_pad_seed_digest_matches_expected_image_edit_source_sha256(tmp_path: Path) -> None:
    declaration = json.loads(IDENTITY_JSON.read_text())
    declaration["seed_pad_px"] = 64
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(declaration))
    out_path = tmp_path / "seed.png"
    meta = build_identity_seed(declaration_path, out_path)
    assert expected_image_edit_source_sha256(
        declaration,
        root=ROOT,
    ) == meta["sha256"]
    checked_in = json.loads(IDENTITY_JSON.read_text())
    assert checked_in["seed_pad_px"] == 64
    assert expected_image_edit_source_sha256(
        checked_in,
        root=ROOT,
    ) != sha256_file(IDLE_PROVIDER_SOURCE)


def test_identity_lock_applies_only_to_dwarf_walk_swing() -> None:
    assert identity_lock_applies("dwarf-miner", "walk")
    assert identity_lock_applies("dwarf-miner", "swing")
    assert not identity_lock_applies("dwarf-miner", "idle")
    assert not identity_lock_applies("miner", "walk")


def _synthetic_fail_result(
    *,
    frame_index: int,
    first_failure: dict[str, object],
    selected_offsets: dict[str, tuple[int, int]],
    first_mismatch: IdentityLockMismatch | None = None,
) -> IdentityLockResult:
    frame = FrameIdentityLockResult(
        selected_offsets=selected_offsets,
        anchor_results={"upper_body": "FAIL"},
        check_results={
            "upper_body": {
                "outcome": "FAIL",
                "comparison": "registered-structure",
                "occupancy_difference": first_failure.get("occupancy_difference", 0.0),
                "palette_role_distance": first_failure.get("palette_role_distance"),
                "max_occupancy_difference": first_failure.get("max_occupancy_difference"),
                "max_palette_role_distance": first_failure.get("max_palette_role_distance"),
            }
        },
        landmark_results={},
        first_failure=dict(first_failure),
        first_mismatch=first_mismatch,
    )
    empty_frame = FrameIdentityLockResult(
        selected_offsets={"upper_body": (0, 0)},
        anchor_results={"upper_body": "PASS"},
        check_results={},
        landmark_results={},
        first_failure=None,
        first_mismatch=None,
    )
    per_frame = [empty_frame] * 4
    per_frame[frame_index] = frame
    overall_failure = {"frame_index": frame_index, **dict(first_failure)}
    return IdentityLockResult(
        outcome="FAIL",
        identity_sha256=CANONICAL_IDENTITY_SHA,
        lock_spec_sha256="a" * 64,
        motion_class="walk",
        per_frame=tuple(per_frame),
        first_failure=overall_failure,
        first_mismatch=first_mismatch,
    )


def test_identity_lock_rejection_detail_pass_returns_none() -> None:
    result = evaluate_identity_lock(_canonical_frames(), "walk")
    assert result.outcome == "PASS"
    assert identity_lock_rejection_detail(result) is None


def test_identity_lock_rejection_detail_near_miss_check_failure() -> None:
    selected_offsets = {"upper_body": (0, 1)}
    mismatch = IdentityLockMismatch(
        anchor="upper_body",
        x=3,
        y=5,
        expected_rgba=(17, 16, 24, 255),
        actual_rgba=(0, 0, 0, 0),
    )
    first_failure = {
        "kind": "check",
        "id": "upper_body",
        "outcome": "FAIL",
        "comparison": "registered-structure",
        "occupancy_difference": 0.22,
        "max_occupancy_difference": 0.20,
        "palette_role_distance": 0.05,
        "max_palette_role_distance": 0.20,
    }
    result = _synthetic_fail_result(
        frame_index=2,
        first_failure=first_failure,
        selected_offsets=selected_offsets,
        first_mismatch=mismatch,
    )
    detail = identity_lock_rejection_detail(result)
    assert detail is not None
    assert detail["schema"] == IDENTITY_LOCK_NEAR_MISS_SCHEMA
    assert detail["primary_reason_code"] == "identity_lock_near_miss"
    assert detail["frame_index"] == 2
    assert detail["kind"] == "check"
    assert detail["id"] == "upper_body"
    assert detail["occupancy_difference"] == 0.22
    assert detail["max_occupancy_difference"] == 0.20
    assert detail["occupancy_margin"] == pytest.approx(-0.02)
    assert detail["palette_role_distance"] == 0.05
    assert detail["max_palette_role_distance"] == 0.20
    assert detail["selected_offsets"] == {"upper_body": [0, 1]}
    assert detail["first_mismatch"] == {
        "anchor": "upper_body",
        "x": 3,
        "y": 5,
        "expected_rgba": [17, 16, 24, 255],
        "actual_rgba": [0, 0, 0, 0],
    }


def test_identity_lock_rejection_detail_large_occupancy_uses_identity_lock() -> None:
    first_failure = {
        "kind": "check",
        "id": "upper_body",
        "outcome": "FAIL",
        "comparison": "registered-structure",
        "occupancy_difference": 0.40,
        "max_occupancy_difference": 0.20,
        "palette_role_distance": 0.0,
        "max_palette_role_distance": 0.20,
    }
    result = _synthetic_fail_result(
        frame_index=1,
        first_failure=first_failure,
        selected_offsets={"upper_body": (0, 0)},
    )
    detail = identity_lock_rejection_detail(result)
    assert detail is not None
    assert detail["primary_reason_code"] == "identity_lock"
    assert detail["occupancy_margin"] == pytest.approx(-0.20)
    assert detail["frame_index"] == 1


def test_identity_lock_rejection_detail_landmark_failure() -> None:
    frame = FrameIdentityLockResult(
        selected_offsets={"upper_body": (0, 0)},
        anchor_results={"upper_body": "PASS"},
        check_results={
            "upper_body": {
                "outcome": "PASS",
                "comparison": "registered-structure",
                "occupancy_difference": 0.0,
                "palette_role_distance": 0.0,
                "max_occupancy_difference": 0.20,
                "max_palette_role_distance": 0.20,
            }
        },
        landmark_results={
            "eye": {
                "outcome": "FAIL",
                "expected_role": "dark-outline",
                "actual_role": "amber-emission",
                "expected_position": [10, 7],
                "actual_position": None,
                "max_distance": 1,
                "anchor": "upper_body",
            }
        },
        first_failure={
            "kind": "landmark",
            "id": "eye",
            "outcome": "FAIL",
            "expected_role": "dark-outline",
            "actual_role": "amber-emission",
            "expected_position": [10, 7],
            "actual_position": None,
            "max_distance": 1,
            "anchor": "upper_body",
        },
        first_mismatch=None,
    )
    result = IdentityLockResult(
        outcome="FAIL",
        identity_sha256=CANONICAL_IDENTITY_SHA,
        lock_spec_sha256="b" * 64,
        motion_class="swing",
        per_frame=(frame,),
        first_failure={"frame_index": 0, **frame.first_failure},
        first_mismatch=None,
    )
    detail = identity_lock_rejection_detail(result)
    assert detail == {
        "schema": IDENTITY_LOCK_NEAR_MISS_SCHEMA,
        "primary_reason_code": "identity_lock",
        "frame_index": 0,
        "kind": "landmark",
        "id": "eye",
        "selected_offsets": {"upper_body": [0, 0]},
    }


def test_invalid_spec_rejects_bad_hash(tmp_path: Path) -> None:
    bad = json.loads(DEFAULT_IDENTITY_LOCKS_PATH.read_text())
    bad["identity_sha256"] = "0" * 64
    bad_path = tmp_path / "bad.json"
    bad_path.write_text(json.dumps(bad))
    with pytest.raises(Exception):
        validate_identity_lock_spec(bad, spec_path=bad_path)


def _load_identity_role_assignment() -> dict[tuple[int, int], str]:
    doc = json.loads(IDENTITY_ROLES_JSON.read_text(encoding="utf-8"))
    cells = doc.get("cells")
    assert isinstance(cells, dict)
    return {
        (int(x_text), int(y_text)): role
        for key, role in cells.items()
        for x_text, y_text in [key.split(",", maxsplit=1)]
    }


def _palette_color_set() -> set[tuple[int, int, int]]:
    palette = load_master_palette(MASTER_PALETTE_PATH)
    colors: set[tuple[int, int, int]] = set()
    for role_colors in palette.role_colors.values():
        colors.update(role_colors)
    return colors


def _cell_content_sha256(cells: list[list[tuple[int, int, int] | None]]) -> str:
    payload = json.dumps(cells, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def test_canonical_identity_is_palette_exact_and_keeps_the_retired_alpha_mask() -> None:
    assert sha256_file(IDENTITY_PNG) == CANONICAL_IDENTITY_SHA
    allowed = _palette_color_set()
    canonical_cells = read_cells(IDENTITY_PNG)
    for row in canonical_cells:
        for cell in row:
            if cell is not None:
                assert cell in allowed
    with (
        Image.open(SOFT_SHADED_SOURCE_PNG) as retired_image,
        Image.open(IDENTITY_PNG) as canonical_image,
    ):
        retired_alpha = np.asarray(retired_image.convert("RGBA"))[:, :, 3]
        canonical_alpha = np.asarray(canonical_image.convert("RGBA"))[:, :, 3]
    assert np.array_equal(retired_alpha, canonical_alpha)


def test_canonical_identity_landmark_roles_match_lock_spec() -> None:
    canonical_cells = read_cells(IDENTITY_PNG)
    palette = load_master_palette(MASTER_PALETTE_PATH)
    for landmark_id, (x, y) in LANDMARK_COORDS.items():
        cell = canonical_cells[y][x]
        assert cell is not None
        assert nearest_palette_role(cell, palette.entries) == LANDMARK_ROLES[landmark_id]


def test_canonical_identity_beard_cluster_excludes_amber_except_landmarks() -> None:
    canonical_cells = read_cells(IDENTITY_PNG)
    palette = load_master_palette(MASTER_PALETTE_PATH)
    landmark_cells = set(LANDMARK_COORDS.values())
    for x in range(BEARD_CHEST_RECT["x0"], BEARD_CHEST_RECT["x1"] + 1):
        for y in range(BEARD_CHEST_RECT["y0"], BEARD_CHEST_RECT["y1"] + 1):
            cell = canonical_cells[y][x]
            if cell is None:
                continue
            role = nearest_palette_role(cell, palette.entries)
            if (x, y) not in landmark_cells:
                assert role != "amber-emission"


def test_identity_roles_reproduce_precleanup_raster(tmp_path: Path) -> None:
    role_assignment = _load_identity_role_assignment()
    source_cells = read_cells(SOFT_SHADED_SOURCE_PNG)
    palette = load_master_palette(MASTER_PALETTE_PATH)
    precleanup = quantize_cells(source_cells, palette, role_assignment)
    out_path = tmp_path / "precleanup.png"
    write_cells(out_path, precleanup)
    assert _cell_content_sha256(read_cells(out_path)) == PRE_CLEANUP_IDENTITY_CELL_SHA
    committed_identity = read_cells(IDENTITY_PNG)
    diff_count = sum(
        1
        for y in range(24)
        for x in range(16)
        if precleanup[y][x] != committed_identity[y][x]
    )
    # Hand cleanup: (5,4) cyan helmet island, (12,7) and (8,12) isolated skin in beard.
    assert diff_count == 3


def test_evaluate_identity_lock_resolves_the_single_canonical_identity() -> None:
    frames = _canonical_frames()
    walk = evaluate_identity_lock(frames, "walk")
    swing = evaluate_identity_lock(frames, "swing")
    assert walk.outcome == "PASS"
    assert swing.outcome == "PASS"
    assert walk.identity_sha256 == CANONICAL_IDENTITY_SHA
    assert swing.identity_sha256 == CANONICAL_IDENTITY_SHA
    walk_payload = identity_lock_report_payload(walk)
    swing_payload = identity_lock_report_payload(swing)
    assert walk_payload["outcome"] == "PASS"
    assert swing_payload["outcome"] == "PASS"
    assert walk_payload["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert swing_payload["identity_sha256"] == CANONICAL_IDENTITY_SHA
    assert walk_payload["per_frame"][0]["anchor_results"]["upper_body"] == "PASS"
    assert swing_payload["per_frame"][0]["anchor_results"]["helmet_face"] == "PASS"
    assert swing_payload["per_frame"][0]["anchor_results"]["boots"] == "PASS"
    assert walk_payload["per_frame"][0]["landmark_results"]["lamp"]["outcome"] == "PASS"
    assert walk_payload["per_frame"][0]["landmark_results"]["eye"]["outcome"] == "PASS"
    assert walk_payload["per_frame"][0]["landmark_results"]["buckle"]["outcome"] == "PASS"


def test_identity_lock_schema_v1_still_validates() -> None:
    v1_doc = {
        "schema": IDENTITY_LOCK_SCHEMA,
        "identity_sha256": CANONICAL_IDENTITY_SHA,
        "frame_size": [16, 24],
        "master_palette": {
            "relative_path": "assets/palettes/first-room.json",
            "sha256": "b21e2a2a85cf8e25c1cbdc69f8f0ffc4cfda7dc7f1f0a451ef7ed9d1fa7d6041",
        },
        "motion_classes": {
            "walk": {
                "locks": [
                    {
                        "id": "upper_body",
                        "rectangle": {"x0": 0, "x1": 15, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "registered-structure",
                        "max_occupancy_difference": 0.20,
                        "max_palette_role_distance": 0.20,
                    }
                ],
                "landmarks": [
                    {
                        "id": "lamp",
                        "canonical": [12, 4],
                        "palette_role": "amber-emission",
                        "max_distance": 2,
                    }
                ],
            }
        },
    }
    validate_identity_lock_spec(v1_doc)


def _minimal_v2_spec(*, motion_classes: dict[str, object]) -> dict[str, object]:
    return {
        "schema": IDENTITY_LOCK_SCHEMA_V2,
        "identity_sha256": CANONICAL_IDENTITY_SHA,
        "frame_size": [16, 24],
        "master_palette": {
            "relative_path": "assets/palettes/first-room.json",
            "sha256": "b21e2a2a85cf8e25c1cbdc69f8f0ffc4cfda7dc7f1f0a451ef7ed9d1fa7d6041",
        },
        "palette_exact_identity": {
            "relative_path": "assets/first-room/dwarf/identity.png",
            "identity_sha256": CANONICAL_IDENTITY_SHA,
            "role_map_relative_path": "assets/first-room/dwarf/identity-roles.json",
            "frame_size": [16, 24],
        },
        "motion_classes": motion_classes,
    }


def test_validate_identity_lock_spec_accepts_class_frame_size_override() -> None:
    spec = _minimal_v2_spec(
        motion_classes={
            "wide_walk": {
                "frame_size": [24, 24],
                "locks": [
                    {
                        "id": "upper_body",
                        "rectangle": {"x0": 4, "x1": 19, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "registered-structure",
                        "max_occupancy_difference": 0.20,
                        "max_palette_role_distance": 0.20,
                    }
                ],
            }
        }
    )
    validate_identity_lock_spec(spec)


def test_validate_identity_lock_spec_rejects_lock_outside_class_frame() -> None:
    spec = _minimal_v2_spec(
        motion_classes={
            "wide_walk": {
                "frame_size": [24, 24],
                "locks": [
                    {
                        "id": "upper_body",
                        "rectangle": {"x0": 0, "x1": 24, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "registered-structure",
                        "max_occupancy_difference": 0.20,
                        "max_palette_role_distance": 0.20,
                    }
                ],
            }
        }
    )
    with pytest.raises(IdentityLockError, match="rectangle exceeds frame_size"):
        validate_identity_lock_spec(spec)


def test_palette_exact_identity_rejects_anchor_size_mismatch() -> None:
    spec = _minimal_v2_spec(
        motion_classes={
            "wide_walk": {
                "frame_size": [24, 24],
                "locks": [
                    {
                        "id": "upper_body",
                        "rectangle": {"x0": 4, "x1": 19, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "registered-structure",
                        "max_occupancy_difference": 0.20,
                        "max_palette_role_distance": 0.20,
                    }
                ],
            }
        }
    )
    palette_exact = spec["palette_exact_identity"]
    assert isinstance(palette_exact, dict)
    palette_exact["frame_size"] = [24, 24]
    with pytest.raises(IdentityLockError, match="anchor frame_size"):
        validate_identity_lock_spec(spec)


def test_evaluate_identity_lock_with_canonical_origin_embeds_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pipeline.strip as strip_module

    monkeypatch.setitem(
        strip_module._CLASS_META,
        "synthetic_wide",
        {
            "grounded": True,
            "loops": True,
            "facing": "fixed",
            "min_alignment_sharpness": None,
            "frame_w": 24,
            "frame_h": 24,
            "canonical_origin": (4, 0),
        },
    )
    spec = _minimal_v2_spec(
        motion_classes={
            "synthetic_wide": {
                "locks": [
                    {
                        "id": "upper_body",
                        "rectangle": {"x0": 4, "x1": 19, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "exact-occupancy",
                    }
                ],
            }
        }
    )
    spec_path = tmp_path / "locks.json"
    spec_path.write_text(json.dumps(spec))
    anchor = load_canonical_cells(IDENTITY_PNG, (16, 24))
    wide_frame: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(24)] for _ in range(24)
    ]
    for y in range(24):
        for x in range(16):
            wide_frame[y][x + 4] = anchor[y][x]
    result = evaluate_identity_lock(
        [wide_frame],
        "synthetic_wide",
        spec_path=spec_path,
    )
    assert result.outcome == "PASS"


def test_canonical_read_outside_anchor_raises_identity_lock_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pipeline.strip as strip_module

    monkeypatch.setitem(
        strip_module._CLASS_META,
        "synthetic_wide",
        {
            "grounded": True,
            "loops": True,
            "facing": "fixed",
            "min_alignment_sharpness": None,
            "frame_w": 24,
            "frame_h": 24,
            "canonical_origin": (4, 0),
        },
    )
    spec = _minimal_v2_spec(
        motion_classes={
            "synthetic_wide": {
                "locks": [
                    {
                        "id": "left_edge",
                        "rectangle": {"x0": 0, "x1": 3, "y0": 1, "y1": 18},
                        "permitted_offsets": [[0, 0]],
                        "comparison": "exact-occupancy",
                    }
                ],
            }
        }
    )
    spec_path = tmp_path / "locks.json"
    spec_path.write_text(json.dumps(spec))
    wide_frame: list[list[tuple[int, int, int] | None]] = [
        [None for _ in range(24)] for _ in range(24)
    ]
    with pytest.raises(IdentityLockError, match="canonical read outside anchor"):
        evaluate_identity_lock(
            [wide_frame],
            "synthetic_wide",
            spec_path=spec_path,
        )


def test_adr_0002_indexed_with_required_sections() -> None:
    adr_path = ROOT / "docs" / "adr" / "0002-palette-exact-canonical-identity.md"
    readme = (ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    text = adr_path.read_text(encoding="utf-8")
    assert adr_path.is_file()
    assert "0002-palette-exact-canonical-identity.md" in readme
    for section in ("## Status", "## Context", "## Decision", "## Consequences"):
        assert section in text
    assert "expand–contract" in text
    assert "Contracted" in text
    assert "amber-emission" in text
    assert "mirroring" in text
