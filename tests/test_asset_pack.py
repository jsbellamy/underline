"""Behavioral proof for pipeline.asset_pack (issue #106)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from pipeline.asset_pack import (
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
from pipeline.gate_evidence import sha256_bytes, sha256_file

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
PALETTE_SHA = sha256_file(PALETTE_PATH)
STONE = (74, 59, 72)
STONE_LIGHT = (98, 81, 93)
STONE_MID = (128, 106, 115)
CYAN = (39, 166, 163)
DWARF = (66, 128, 90)
LANTERN = (240, 163, 58)
BAD_RGB = (17, 23, 32)


def _path_prefix(root: Path) -> str:
    try:
        rel = root.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return ""
    return f"{rel}/" if rel else ""


def _rel(root: Path, suffix: str) -> str:
    return f"{_path_prefix(root)}{suffix}"


def _repo_file(root: Path, rel_path: str) -> Path:
    if _path_prefix(root):
        return ROOT / rel_path
    return root / rel_path


def _write_rgba(root: Path, rel_path: str, size: tuple[int, int], rgb: tuple[int, int, int]) -> str:
    path = _repo_file(root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (*rgb, 255))
    image.save(path)
    return sha256_file(path)


def _animation_report(*, outcome: str = "PASS") -> dict[str, object]:
    return {
        "schema": "final-polish-report/0",
        "outcome": outcome,
        "fingerprint": "abc",
    }


def _static_report(*, outcome: str = "PASS") -> dict[str, object]:
    return {
        "schema": "static-asset-report/0",
        "outcome": outcome,
        "fingerprint": "def",
    }


def _animation_releases(root: Path, prefix: str, rgb: tuple[int, int, int]) -> list[dict[str, str]]:
    releases: list[dict[str, str]] = []
    for index in range(4):
        rel = f"{prefix}/frame-{index}.png"
        digest = _write_rgba(root, rel, (16, 24), rgb)
        releases.append({"path": rel, "sha256": digest})
    return releases


def _static_releases(
    root: Path,
    prefix: str,
    items: dict[str, tuple[int, int, int]],
) -> list[dict[str, str]]:
    releases: list[dict[str, str]] = []
    for item_id, rgb in items.items():
        rel = f"{prefix}/{item_id}.png"
        digest = _write_rgba(root, rel, (32, 32), rgb)
        releases.append({"path": rel, "sha256": digest})
    return releases


def _write_report(root: Path, rel_path: str, payload: dict[str, object]) -> str:
    path = _repo_file(root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def _base_assets(root: Path) -> list[dict[str, object]]:
    dwarf_idle_report = _write_report(root, _rel(root, "reports/dwarf-idle.json"), _animation_report())
    dwarf_walk_report = _write_report(root, _rel(root, "reports/dwarf-walk.json"), _animation_report())
    dwarf_swing_report = _write_report(
        root,
        _rel(root, "reports/dwarf-swing.json"),
        _animation_report(),
    )
    lantern_report = _write_report(root, _rel(root, "reports/lantern.json"), _animation_report())
    cave_report = _write_report(root, _rel(root, "reports/cave.json"), _static_report())
    mining_report = _write_report(root, _rel(root, "reports/mining.json"), _static_report())

    return [
        {
            "id": "dwarf-idle",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-idle"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-idle.json"),
                "sha256": dwarf_idle_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-idle"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [200, 200, 200, 200],
        },
        {
            "id": "dwarf-walk",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-walk"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-walk.json"),
                "sha256": dwarf_walk_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-walk"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [125, 125, 125, 125],
        },
        {
            "id": "dwarf-swing",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-swing"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-swing.json"),
                "sha256": dwarf_swing_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-swing"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": False,
            "durations_ms": [150, 80, 60, 180],
            "contact_frame": 3,
        },
        {
            "id": "lantern",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/lantern"),
            "final_report": {
                "path": _rel(root, "reports/lantern.json"),
                "sha256": lantern_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/lantern"), LANTERN),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [160, 160, 160, 160],
        },
        {
            "id": "cave",
            "kind": "static",
            "bundle_path": _rel(root, "bundles/cave"),
            "final_report": {"path": _rel(root, "reports/cave.json"), "sha256": cave_report},
            "releases": _static_releases(
                root,
                _rel(root, "releases/cave"),
                {
                    "cave-v0": STONE,
                    "cave-v1": STONE_LIGHT,
                    "cave-v2": STONE_MID,
                },
            ),
            "item_ids": ["cave-v0", "cave-v1", "cave-v2"],
        },
        {
            "id": "mining",
            "kind": "static",
            "bundle_path": _rel(root, "bundles/mining"),
            "final_report": {"path": _rel(root, "reports/mining.json"), "sha256": mining_report},
            "releases": _static_releases(
                root,
                _rel(root, "releases/mining"),
                {"ore-cyan-seam": CYAN},
            ),
            "item_ids": ["ore-cyan-seam"],
        },
    ]


def _pack_doc(
    root: Path,
    *,
    assets: list[dict[str, object]] | None = None,
    preview_scene: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema": PACK_SCHEMA,
        "id": "first-room",
        "master_palette": {
            "path": "assets/palettes/first-room.json",
            "sha256": PALETTE_SHA,
        },
        "viewport": [320, 180],
        "assets": assets if assets is not None else _base_assets(root),
        "preview_scene": preview_scene if preview_scene is not None else TERRACED_SHAFT_PREVIEW_SCENE,
    }


def _ensure_repo_palette(root: Path) -> None:
    dest = root / "assets" / "palettes" / "first-room.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(PALETTE_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _write_pack(root: Path, doc: dict[str, object] | None = None) -> Path:
    _ensure_repo_palette(root)
    payload = doc if doc is not None else _pack_doc(root)
    path = root / "pack.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# --- C1 schema ---


def test_schema_requires_every_field(tmp_path: Path) -> None:
    path = _write_pack(tmp_path, {"schema": PACK_SCHEMA})
    with pytest.raises(InvalidAssetPackError, match="id"):
        parse_asset_pack(json.loads(path.read_text()), repo_root=tmp_path)


def test_schema_rejects_wrong_schema(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["schema"] = "asset-pack/1"
    with pytest.raises(InvalidAssetPackError, match="schema"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_rejects_path_traversal(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["path"] = "../escape.png"
    with pytest.raises(InvalidAssetPackError, match="relative"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_rejects_duplicate_asset_ids(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["assets"].append(dict(doc["assets"][0]))
    with pytest.raises(InvalidAssetPackError, match="duplicate"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_schema_preserves_release_order(tmp_path: Path) -> None:
    pack = load_asset_pack(_write_pack(tmp_path), repo_root=tmp_path)
    idle = next(asset for asset in pack.assets if asset.id == "dwarf-idle")
    prefix = _path_prefix(tmp_path)
    assert [release.path for release in idle.releases] == [
        f"{prefix}releases/dwarf-idle/frame-0.png",
        f"{prefix}releases/dwarf-idle/frame-1.png",
        f"{prefix}releases/dwarf-idle/frame-2.png",
        f"{prefix}releases/dwarf-idle/frame-3.png",
    ]


def test_animation_row_requires_metadata(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    del doc["assets"][0]["durations_ms"]
    with pytest.raises(InvalidAssetPackError, match="durations_ms"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_static_row_requires_item_ids(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    del doc["assets"][4]["item_ids"]
    with pytest.raises(InvalidAssetPackError, match="item_ids"):
        parse_asset_pack(doc, repo_root=tmp_path)


def _assert_check_fails(tmp_path: Path, doc: dict[str, object], match: str) -> None:
    result = check_asset_pack(_write_pack(tmp_path, doc), repo_root=tmp_path)
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
    doc = _pack_doc(tmp_path)
    row = next(asset for asset in doc["assets"] if asset["id"] == asset_id)
    row[field] = value
    _assert_check_fails(tmp_path, doc, match)


def test_metadata_policy_rejects_wrong_facing(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["assets"][0]["facing"] = "left"
    with pytest.raises(InvalidAssetPackError, match="facing"):
        parse_asset_pack(doc, repo_root=tmp_path)


def test_metadata_policy_rejects_fail_report(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    report_rel = _rel(tmp_path, "reports/dwarf-idle.json")
    report_path = _repo_file(tmp_path, report_rel)
    report_path.write_text(
        json.dumps(_animation_report(outcome="FAIL"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    doc["assets"][0]["final_report"]["sha256"] = sha256_file(report_path)
    _assert_check_fails(tmp_path, doc, "PASS")


def test_metadata_policy_rejects_release_hash_mismatch(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["sha256"] = "0" * 64
    _assert_check_fails(tmp_path, doc, "release hash")


def test_metadata_policy_rejects_palette_violation(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    bad_rel = doc["assets"][0]["releases"][0]["path"]
    bad_path = _repo_file(tmp_path, bad_rel)
    image = Image.new("RGBA", (16, 24), (*BAD_RGB, 255))
    image.save(bad_path)
    doc["assets"][0]["releases"][0]["sha256"] = sha256_file(bad_path)
    _assert_check_fails(tmp_path, doc, "palette")


def test_check_passes_valid_pack(tmp_path: Path) -> None:
    result = check_asset_pack(_write_pack(tmp_path), repo_root=tmp_path)
    assert result.valid is True
    assert result.outcome == "PASS"


# --- C3 preview scene ---


def test_terraced_shaft_preview_round_trips(tmp_path: Path) -> None:
    pack = load_asset_pack(_write_pack(tmp_path), repo_root=tmp_path)
    assert serialize_preview_scene(pack.preview_scene) == TERRACED_SHAFT_PREVIEW_SCENE


def test_preview_scene_requires_ten_columns(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["preview_scene"] = dict(TERRACED_SHAFT_PREVIEW_SCENE)
    doc["preview_scene"]["grid_columns"] = 9
    with pytest.raises(InvalidAssetPackError, match="grid_columns"):
        parse_asset_pack(doc, repo_root=tmp_path)


# --- C4 deterministic previews ---


def test_render_preview_dimensions(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    out = tmp_path / "preview"
    result = render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        assert native.size == (320, 180)
    with Image.open(out / "4x.png") as enlarged:
        assert enlarged.size == (1280, 720)


def test_render_preview_4x_is_nearest_neighbor(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    out = tmp_path / "preview"
    render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        expected = native.resize((1280, 720), Image.NEAREST)
    with Image.open(out / "4x.png") as enlarged:
        assert list(enlarged.get_flattened_data()) == list(expected.get_flattened_data())


def test_render_preview_respects_layer_order(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    out = tmp_path / "preview"
    render_pack_preview(pack_path, out, repo_root=tmp_path)
    with Image.open(out / "native.png") as native:
        rgba = native.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        dwarf_anchor = TERRACED_SHAFT_PREVIEW_SCENE["entities"][0]
        assert pixels[dwarf_anchor["x"], dwarf_anchor["y"]][:3] == DWARF


def test_render_preview_is_byte_deterministic(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    first = tmp_path / "preview-a"
    second = tmp_path / "preview-b"
    render_pack_preview(pack_path, first, repo_root=tmp_path)
    render_pack_preview(pack_path, second, repo_root=tmp_path)
    assert sha256_file(first / "native.png") == sha256_file(second / "native.png")
    assert sha256_file(first / "4x.png") == sha256_file(second / "4x.png")


def test_render_preview_hashes_bind_output(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path)
    out = tmp_path / "preview"
    result = render_pack_preview(pack_path, out, repo_root=tmp_path)
    assert result.native_sha256 == sha256_file(out / "native.png")
    assert result.scale4x_sha256 == sha256_file(out / "4x.png")
    assert len(result.release_hashes) > 0


def test_invalid_pack_render_raises(tmp_path: Path) -> None:
    doc = _pack_doc(tmp_path)
    doc["assets"][0]["releases"][0]["sha256"] = "0" * 64
    pack_path = _write_pack(tmp_path, doc)
    with pytest.raises(AssetPackError):
        render_pack_preview(pack_path, tmp_path / "preview", repo_root=tmp_path)
