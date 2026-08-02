"""Behavioral proof for pipeline.asset_pack (issue #106)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from pipeline.asset_pack import (
    FIRST_ROOM_ANIMATION_POLICY,
    PACK_SCHEMA,
    TERRACED_SHAFT_PREVIEW_SCENE,
    AssetPackError,
    InvalidAssetPackError,
    check_asset_pack,
    load_asset_pack,
    parse_asset_pack,
    render_pack_preview,
    serialize_preview_scene,
)
from pipeline.cell_raster import cells_from_rgba
from pipeline.gate_evidence import sha256_bytes, sha256_file
from tests.support.asset_pack import (
    DWARF,
    _animation_report,
    _path_prefix,
    _repo_file,
    _rel,
    _write_report,
    ensure_repo_palette,
    pack_doc,
    write_pack,
)

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
PALETTE_SHA = sha256_file(PALETTE_PATH)
BAD_RGB = (17, 23, 32)


DWARF_RELEASE_FRAMES: tuple[tuple[str, str, int, int, int], ...] = (
    ("dwarf-idle", "idle", 268, 24, 268),
    ("dwarf-walk", "walk", 152, 20, 152),
    ("dwarf-swing", "swing", 177, 19, 177),
)


def _copy_repo_release(root: Path, anim: str, frame: str) -> str:
    rel = f"assets/first-room/dwarf/{anim}/release/{frame}.png"
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copy2(ROOT / rel, dest)
    return rel


def _master_palette_rgb_set() -> frozenset[tuple[int, int, int]]:
    doc = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    colors: set[tuple[int, int, int]] = set()
    for group in doc["role_groups"]:
        for hex_color in group["colors"]:
            colors.add(tuple(int(hex_color[index : index + 2], 16) for index in (1, 3, 5)))
    return frozenset(colors)


def _frame_palette_stats(rel_path: str) -> tuple[int, int, int]:
    allowed = _master_palette_rgb_set()
    with Image.open(ROOT / rel_path) as image:
        cells = cells_from_rgba(image)
    opaque = 0
    colors: set[tuple[int, int, int]] = set()
    in_palette = 0
    for row in cells:
        for cell in row:
            if cell is None:
                continue
            opaque += 1
            colors.add(cell)
            if cell in allowed:
                in_palette += 1
    return opaque, len(colors), in_palette


def _write_dwarf_palette_violation_pack(root: Path) -> Path:
    """Minimal asset-pack/0 manifest binding real dwarf release frame-0 PNGs."""
    ensure_repo_palette(root)
    assets: list[dict[str, object]] = []
    for asset_id, anim, _opaque, _unique, _in_palette in DWARF_RELEASE_FRAMES:
        report_digest = _write_report(root, f"reports/{asset_id}.json", _animation_report())
        rel = _copy_repo_release(root, anim, "frame-0")
        digest = sha256_file(root / rel)
        row: dict[str, object] = {
            "id": asset_id,
            "kind": "animation",
            "bundle_path": f"assets/first-room/dwarf/{anim}",
            "final_report": {"path": f"reports/{asset_id}.json", "sha256": report_digest},
            "releases": [{"path": rel, "sha256": digest}],
            "facing": "right",
            "runtime_mirror": True,
        }
        policy = FIRST_ROOM_ANIMATION_POLICY[asset_id]
        row["loop"] = policy["loop"]
        row["durations_ms"] = list(policy["durations_ms"])
        if policy["contact_frame"] is not None:
            row["contact_frame"] = policy["contact_frame"]
        assets.append(row)
    doc = {
        "schema": PACK_SCHEMA,
        "id": "first-room",
        "master_palette": {
            "path": "assets/palettes/first-room.json",
            "sha256": PALETTE_SHA,
        },
        "viewport": [320, 180],
        "assets": assets,
        "preview_scene": TERRACED_SHAFT_PREVIEW_SCENE,
    }
    return write_pack(root, doc)


# --- C1 schema ---


def test_schema_requires_every_field(tmp_path: Path) -> None:
    path = write_pack(tmp_path, {"schema": PACK_SCHEMA})
    with pytest.raises(InvalidAssetPackError, match="id"):
        parse_asset_pack(json.loads(path.read_text()), repo_root=tmp_path)


def test_schema_rejects_wrong_schema(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["schema"] = "asset-pack/1"
    with pytest.raises(InvalidAssetPackError, match="schema"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_rejects_path_traversal(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["path"] = "../escape.png"
    with pytest.raises(InvalidAssetPackError, match="relative"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_rejects_duplicate_asset_ids(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["assets"].append(dict(doc["assets"][0]))
    with pytest.raises(InvalidAssetPackError, match="duplicate"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_preserves_release_order(tmp_path: Path) -> None:
    pack = load_asset_pack(write_pack(tmp_path), repo_root=tmp_path)
    idle = next(asset for asset in pack.assets if asset.id == "dwarf-idle")
    prefix = _path_prefix(tmp_path)
    assert [release.path for release in idle.releases] == [
        f"{prefix}releases/dwarf-idle/frame-0.png",
        f"{prefix}releases/dwarf-idle/frame-1.png",
        f"{prefix}releases/dwarf-idle/frame-2.png",
        f"{prefix}releases/dwarf-idle/frame-3.png",
    ]


def test_animation_row_requires_metadata(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    del doc["assets"][0]["durations_ms"]
    with pytest.raises(InvalidAssetPackError, match="durations_ms"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_static_row_requires_item_ids(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    del doc["assets"][4]["item_ids"]
    with pytest.raises(InvalidAssetPackError, match="item_ids"):
        parse_asset_pack(doc, repo_root=tmp_path)


def _assert_check_fails(tmp_path: Path, doc: dict[str, object], match: str) -> None:
    result = check_asset_pack(write_pack(tmp_path, doc), repo_root=tmp_path)
    assert not result.valid
    assert any(match in error for error in result.errors)


# --- C2 metadata policy ---


@pytest.mark.parametrize(
    ("asset_id", "field", "value", "match"),
    [
        ("dwarf-idle", "durations_ms", [100, 200, 200, 200], "idle durations"),
        ("dwarf-walk", "loop", False, "walk loop"),
        ("dwarf-swing", "durations_ms", [150, 80, 60, 100], "swing durations"),
        ("dwarf-swing", "contact_frame", 2, "contact_frame"),
        ("lantern", "durations_ms", [160, 160, 160, 100], "lantern durations"),
    ],
)
def test_metadata_policy_rejects_wrong_timing(
    tmp_path: Path,
    asset_id: str,
    field: str,
    value: object,
    match: str,
) -> None:
    doc = pack_doc(tmp_path)
    row = next(asset for asset in doc["assets"] if asset["id"] == asset_id)
    row[field] = value
    _assert_check_fails(tmp_path, doc, match)


def test_metadata_policy_rejects_wrong_facing(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["assets"][0]["facing"] = "left"
    with pytest.raises(InvalidAssetPackError, match="facing"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_metadata_policy_rejects_fail_report(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    report_rel = _rel(tmp_path, "reports/dwarf-idle.json")
    report_path = _repo_file(tmp_path, report_rel)
    report_path.write_text(
        json.dumps(_animation_report(outcome="FAIL"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    doc["assets"][0]["final_report"]["sha256"] = sha256_file(report_path)
    _assert_check_fails(tmp_path, doc, "PASS")


def test_metadata_policy_rejects_release_hash_mismatch(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["sha256"] = "0" * 64
    _assert_check_fails(tmp_path, doc, "release hash")


def test_dwarf_release_frames_violate_master_palette(tmp_path: Path) -> None:
    """Characterization of dwarf release frame-0 palette membership (#171, #176–#179).

    The defect this test was written to pin — dwarf Release Frames carrying colours
    outside the Master Palette — is repaired. #176, #177, and #178 requantized the
    idle, walk, and swing bundles, and #179 retired the off-palette identity that
    seeded them, so a pack binding the real Release Frames now verifies clean.
    """
    for asset_id, anim, expected_opaque, expected_unique, expected_in_palette in DWARF_RELEASE_FRAMES:
        rel = f"assets/first-room/dwarf/{anim}/release/frame-0.png"
        opaque, unique, in_palette = _frame_palette_stats(rel)
        assert opaque == expected_opaque, asset_id
        assert unique == expected_unique, asset_id
        assert in_palette == expected_in_palette, asset_id

    result = check_asset_pack(_write_dwarf_palette_violation_pack(tmp_path), repo_root=tmp_path)
    assert result.valid
    assert result.outcome == "PASS"


def test_metadata_policy_rejects_palette_violation(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    bad_rel = doc["assets"][0]["releases"][0]["path"]
    bad_path = _repo_file(tmp_path, bad_rel)
    image = Image.new("RGBA", (16, 24), (*BAD_RGB, 255))
    image.save(bad_path)
    doc["assets"][0]["releases"][0]["sha256"] = sha256_file(bad_path)
    _assert_check_fails(tmp_path, doc, "palette")


def test_check_passes_valid_pack(tmp_path: Path) -> None:
    result = check_asset_pack(write_pack(tmp_path), repo_root=tmp_path)
    assert result.valid is True
    assert result.outcome == "PASS"


# --- C3 preview scene ---


def test_terraced_shaft_preview_round_trips(tmp_path: Path) -> None:
    pack = load_asset_pack(write_pack(tmp_path), repo_root=tmp_path)
    assert serialize_preview_scene(pack.preview_scene) == TERRACED_SHAFT_PREVIEW_SCENE


def test_preview_scene_requires_ten_columns(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["preview_scene"] = dict(TERRACED_SHAFT_PREVIEW_SCENE)
    doc["preview_scene"]["grid_columns"] = 9
    with pytest.raises(InvalidAssetPackError, match="grid_columns"):
        parse_asset_pack(doc, repo_root=tmp_path)


# --- C4 deterministic previews ---


def test_render_preview_dimensions(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    out = tmp_path / "preview"
    result = render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        assert native.size == (320, 180)
    with Image.open(out / "4x.png") as enlarged:
        assert enlarged.size == (1280, 720)


def test_render_preview_4x_is_nearest_neighbor(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    out = tmp_path / "preview"
    render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        expected = native.resize((1280, 720), Image.NEAREST)
    with Image.open(out / "4x.png") as enlarged:
        assert list(enlarged.get_flattened_data()) == list(expected.get_flattened_data())


def test_render_preview_respects_layer_order(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    out = tmp_path / "preview"
    render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        rgba = native.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        dwarf_anchor = TERRACED_SHAFT_PREVIEW_SCENE["entities"][0]
        assert pixels[dwarf_anchor["x"], dwarf_anchor["y"]][:3] == DWARF


def test_render_preview_is_byte_deterministic(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    first = tmp_path / "preview-a"
    second = tmp_path / "preview-b"
    render_pack_preview(pack_path, first, repo_root=tmp_path)
    render_pack_preview(pack_path, second, repo_root=tmp_path)
    assert sha256_file(first / "native.png") == sha256_file(second / "native.png")
    assert sha256_file(first / "4x.png") == sha256_file(second / "4x.png")


def test_render_preview_hashes_bind_output(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    out = tmp_path / "preview"
    result = render_pack_preview(pack_path, out, repo_root=tmp_path)
    assert result.native_sha256 == sha256_file(out / "native.png")
    assert result.scale4x_sha256 == sha256_file(out / "4x.png")
    assert len(result.release_hashes) > 0


def test_invalid_pack_render_raises(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["sha256"] = "0" * 64
    pack_path = write_pack(tmp_path, doc)
    with pytest.raises(AssetPackError):
        render_pack_preview(pack_path, tmp_path / "preview", repo_root=tmp_path)


def test_final_report_binding_rejects_path_escape(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(_animation_report(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    doc["assets"][0]["final_report"] = {
        "path": "../outside.json",
        "sha256": sha256_file(outside),
    }
    result = check_asset_pack(write_pack(tmp_path, doc), repo_root=tmp_path)
    assert not result.valid
    assert result.reason_codes == ("report_path_escape",)
