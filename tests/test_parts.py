"""Cell part map loader and canonical dwarf partition (issues #295, #298)."""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest

from pipeline.cell_raster import read_cells
from pipeline.gate_evidence import sha256_file
from pipeline.parts import (
    ORIENTATION_IDS,
    REVIEW_SCALE,
    PartMapError,
    _REVIEW_COLORS,
    _four_connected_blobs,
    lattice_orientation,
    load_part_map,
    render_part_map,
)

ROOT = Path(__file__).resolve().parents[1]
PARTS_JSON = ROOT / "assets" / "first-room" / "dwarf" / "parts.json"
PARTS_REVIEW_PNG = ROOT / "assets" / "first-room" / "dwarf" / "parts-review.png"
IDENTITY_LOCKS_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity-locks.json"
BASE_FRAME = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "release" / "frame-0.png"
ROLES_JSON = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "polished-roles.json"
CANONICAL_BASE_SHA = "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
REDERIVED_PART_IDS = frozenset({"torso", "arm_near", "hand_near", "head_face", "beard"})
PART_DOMINANT_ROLES = {
    "torso": frozenset({"earth-leather-beard", "green-cloth"}),
    "arm_near": frozenset({"green-cloth"}),
    "hand_near": frozenset({"amber-emission", "earth-leather-beard", "skin"}),
    "head_face": frozenset({"earth-leather-beard", "skin", "amber-emission"}),
    "beard": frozenset({"earth-leather-beard"}),
}
REQUIRED_PART_IDS = frozenset(
    {
        "tool_head",
        "tool_handle",
        "helmet",
        "lamp",
        "head_face",
        "beard",
        "torso",
        "arm_near",
        "hand_near",
        "belt",
        "legs",
        "boots",
    }
)
TOOL_HEAD_CORE = frozenset(
    {(4, 3), (3, 3), (3, 4), (2, 4), (2, 5), (1, 6), (1, 7)}
)
TOOL_BBOX_RECT = {(x, y) for y in range(1, 8) for x in range(0, 6)}
TOOL_BBOX_CELL_COUNT = 21
TOOL_PART_CELL_COUNT = 26
OUTLINE_CONNECTIVITY_EXCEPTIONS = frozenset({(14, 16), (14, 17), (14, 18), (15, 17)})


def _opaque_cells(path: Path = BASE_FRAME) -> set[tuple[int, int]]:
    cells = read_cells(path)
    return {
        (x, y)
        for y in range(len(cells))
        for x in range(len(cells[0]))
        if cells[y][x] is not None
    }


def _roles_for_frame0() -> dict[str, str]:
    payload = json.loads(ROLES_JSON.read_text(encoding="utf-8"))
    return payload["frames"][0]["cells"]


def _dominant_non_outline_role(cells: set[tuple[int, int]]) -> str | None:
    roles = _roles_for_frame0()
    counts: dict[str, int] = {}
    for cell in cells:
        role = roles[f"{cell[0]},{cell[1]}"]
        if role == "dark-outline":
            continue
        counts[role] = counts.get(role, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _landmark_cells_from_identity_locks() -> dict[str, tuple[int, int]]:
    payload = json.loads(IDENTITY_LOCKS_JSON.read_text(encoding="utf-8"))
    return {
        row["id"]: tuple(row["canonical"])
        for row in payload["motion_classes"]["walk"]["landmarks"]
    }


@pytest.fixture
def part_map():
    return load_part_map(PARTS_JSON)


def test_c1_partitions_every_opaque_base_cell_exactly_once(part_map) -> None:
    assigned: set[tuple[int, int]] = set()
    for part in part_map.parts.values():
        for cell in part.cells:
            assert cell not in assigned, f"duplicate assignment at {cell}"
            assigned.add(cell)
    assert len(assigned) == 268
    assert assigned == _opaque_cells()


def test_c1_base_digest_is_pinned(part_map) -> None:
    assert part_map.base_raster_sha256 == CANONICAL_BASE_SHA
    assert part_map.base_raster_sha256 == sha256_file(BASE_FRAME)


def test_c2_required_part_ids_and_outline_cells_assigned(part_map) -> None:
    assert set(part_map.parts) == REQUIRED_PART_IDS
    roles = _roles_for_frame0()
    outline_cells = {
        tuple(map(int, key.split(",")))
        for key, role in roles.items()
        if role == "dark-outline"
    }
    assigned_outline = {
        cell
        for part in part_map.parts.values()
        for cell in part.cells
        if roles[f"{cell[0]},{cell[1]}"] == "dark-outline"
    }
    assert len(outline_cells) == 86
    assert assigned_outline == outline_cells


def test_c2_outline_cells_follow_nearest_core_chebyshev_rule(part_map) -> None:
    roles = _roles_for_frame0()
    core_cells = {
        tuple(map(int, key.split(",")))
        for key, role in roles.items()
        if role != "dark-outline"
    }
    part_lookup = {
        cell: part_id
        for part_id, part in part_map.parts.items()
        for cell in part.cells
    }
    for key, role in roles.items():
        if role != "dark-outline":
            continue
        x, y = map(int, key.split(","))
        if (x, y) in OUTLINE_CONNECTIVITY_EXCEPTIONS:
            continue
        nearest = min(core_cells, key=lambda cell: (_chebyshev(cell, (x, y)), cell))
        assert part_lookup[(x, y)] == part_lookup[nearest]


def _chebyshev(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def test_c1_rederived_parts_are_single_blobs_with_expected_roles(part_map) -> None:
    roles = _roles_for_frame0()
    for part_id in REDERIVED_PART_IDS:
        part = part_map.parts[part_id]
        assert len(_four_connected_blobs(part.cells)) == 1
        dominant = _dominant_non_outline_role(set(part.cells))
        assert dominant in PART_DOMINANT_ROLES[part_id], (
            f"{part_id} dominant role {dominant!r} not in {PART_DOMINANT_ROLES[part_id]!r}"
        )
    assigned: set[tuple[int, int]] = set()
    for part in part_map.parts.values():
        for cell in part.cells:
            assert cell not in assigned
            assigned.add(cell)
    assert len(assigned) == 268
    assert assigned == _opaque_cells()


def test_c2_checked_in_map_is_connected_and_fixture_splits_blob(tmp_path: Path, part_map) -> None:
    for part in part_map.parts.values():
        assert len(_four_connected_blobs(part.cells)) == 1

    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    bridge = "8,12"
    payload["parts"]["torso"]["cells"].remove(bridge)
    payload["parts"]["arm_near"]["cells"].append(bridge)
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="4-connected") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "part_not_connected"


def test_c3_landmarks_match_identity_locks_and_fixture_moves_eye(
    tmp_path: Path,
    part_map,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    landmarks = _landmark_cells_from_identity_locks()
    assert landmarks["eye"] == (10, 7)
    assert landmarks["lamp"] == (12, 4)
    assert landmarks["buckle"] == (11, 16)
    assert landmarks["eye"] in part_map.parts["head_face"].cells
    assert landmarks["lamp"] in part_map.parts["lamp"].cells
    assert landmarks["buckle"] in part_map.parts["belt"].cells

    monkeypatch.setattr(
        "pipeline.parts._load_identity_landmarks",
        lambda: {
            "lamp": landmarks["lamp"],
            "eye": (11, 12),
            "buckle": landmarks["buckle"],
        },
    )
    with pytest.raises(PartMapError, match="landmark") as exc_info:
        load_part_map(PARTS_JSON)
    assert exc_info.value.reason_code == "landmark_part_mismatch"


def test_c4_checked_in_grip_is_held_and_fixture_moves_grip(tmp_path: Path, part_map) -> None:
    handle = part_map.parts["tool_handle"]
    hand = part_map.parts["hand_near"]
    assert handle.grip is not None
    assert any(_chebyshev(handle.grip, cell) <= 1 for cell in hand.cells)

    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    payload["parts"]["tool_handle"]["grip"] = [0, 1]
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="grip") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "grip_not_held"


def test_c5_render_part_map_declares_review_colors_and_panels(part_map) -> None:
    image = render_part_map(part_map, BASE_FRAME)
    part_ids = sorted(part_map.parts)
    assert set(_REVIEW_COLORS) == set(part_ids)
    assert len(_REVIEW_COLORS) == len(set(_REVIEW_COLORS.values()))
    width, height = part_map.frame_size
    expected_panel_count = 2 + len(part_ids)
    panel1_h = height + 4 + height * REVIEW_SCALE
    panel2_h = height * REVIEW_SCALE + 8
    tile_h = height * REVIEW_SCALE
    label_h = 16
    tile_rows = (len(part_ids) + 3) // 4
    expected_h = 8 + panel1_h + 8 + panel2_h + 8 + tile_rows * (tile_h + label_h + 4) + 8
    assert image.size[1] == expected_h
    assert expected_panel_count == 14


def test_c6_parts_review_png_matches_render(part_map) -> None:
    rendered = render_part_map(part_map, BASE_FRAME)
    buffer = io.BytesIO()
    rendered.save(buffer, format="PNG", compress_level=6)
    assert PARTS_REVIEW_PNG.read_bytes() == buffer.getvalue()


def test_c3_rigid_orientations_match_lattice_transform(part_map) -> None:
    for part_id, part in part_map.parts.items():
        if not part.rigid:
            assert part.orientations is None
            continue
        assert part.orientations is not None
        assert set(part.orientations) == set(ORIENTATION_IDS)
        rot0 = part.orientations["rot0"]
        for orientation_id in ORIENTATION_IDS:
            expected = lattice_orientation(rot0, orientation_id)
            assert part.orientations[orientation_id] == expected


def test_c3_tool_footprint_matches_measured_bbox(part_map) -> None:
    tool_cells = (
        set(part_map.parts["tool_head"].cells)
        | set(part_map.parts["tool_handle"].cells)
    )
    assert len(tool_cells) == TOOL_PART_CELL_COUNT
    tool_in_bbox = {cell for cell in tool_cells if cell in TOOL_BBOX_RECT}
    assert len(tool_in_bbox) == TOOL_BBOX_CELL_COUNT
    xs = [x for x, y in tool_in_bbox]
    ys = [y for x, y in tool_in_bbox]
    assert min(xs) == 0 and max(xs) == 5 and max(ys) == 7
    assert all(1 <= y <= 7 for y in ys)
    assert TOOL_HEAD_CORE <= part_map.parts["tool_head"].cells


def test_c4_parent_chain_reaches_torso_without_cycle(part_map) -> None:
    seen: set[str] = set()

    def walk(part_id: str) -> None:
        assert part_id not in seen
        seen.add(part_id)
        part = part_map.parts[part_id]
        if part.parent is None:
            return
        assert part.pivot is not None
        assert part.parent in part_map.parts
        walk(part.parent)

    walk("tool_head")
    assert part_map.parts["tool_head"].parent == "tool_handle"
    assert part_map.parts["tool_handle"].parent == "hand_near"
    assert part_map.parts["hand_near"].parent == "arm_near"
    assert part_map.parts["arm_near"].parent == "torso"
    assert part_map.parts["torso"].parent is None
    for child in ("helmet", "beard", "belt", "legs", "boots", "head_face", "lamp"):
        assert part_map.parts[child].parent == "torso"


def test_c5_tool_handle_grip_is_authored_and_inside_part(part_map) -> None:
    handle = part_map.parts["tool_handle"]
    assert handle.grip == (5, 7)
    assert handle.grip in handle.cells
    document = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    assert "grip_rationale" in document
    assert "occluded" in document["grip_rationale"].lower()


def test_c6_rejects_base_digest_mismatch(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    payload["base_raster_sha256"] = "0" * 64
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="digest") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "base_raster_digest_mismatch"


def test_c6_rejects_unassigned_opaque_cell(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    torso_cells = payload["parts"]["torso"]["cells"]
    payload["parts"]["torso"]["cells"] = torso_cells[:-1]
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="unassigned") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "unassigned_opaque_cell"


def test_c6_rejects_duplicate_cell_claim(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    stolen = payload["parts"]["torso"]["cells"][0]
    payload["parts"]["helmet"]["cells"].append(stolen)
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="duplicate") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "duplicate_cell_assignment"


def test_c6_rejects_missing_required_part(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    beard_cells = payload["parts"].pop("beard")["cells"]
    payload["parts"]["torso"]["cells"].extend(beard_cells)
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="missing required part") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "missing_required_part"


def test_c6_rejects_rigid_part_missing_orientation(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    payload["parts"]["tool_head"]["orientations"].pop("rot270+mirror")
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="orientation") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "invalid_part_map_orientation"


def test_c6_rejects_invalid_orientation_footprint(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    rot0 = copy.deepcopy(payload["parts"]["tool_head"]["orientations"]["rot0"])
    rot0["cells"]["0,0"] = [1, 2, 3]
    payload["parts"]["tool_head"]["orientations"]["rot90"] = rot0
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="orientation") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "invalid_part_map_orientation"


def test_c6_rejects_unknown_parent(tmp_path: Path) -> None:
    payload = json.loads(PARTS_JSON.read_text(encoding="utf-8"))
    payload["parts"]["lamp"]["parent"] = "missing_parent"
    path = tmp_path / "parts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PartMapError, match="parent") as exc_info:
        load_part_map(path)
    assert exc_info.value.reason_code == "unknown_parent"
