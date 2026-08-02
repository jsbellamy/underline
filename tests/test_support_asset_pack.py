"""Behavioral proof for tests.support.asset_pack (issue #253)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.asset_pack import PACK_SCHEMA, parse_asset_pack
from tests.support.asset_pack import pack_doc, write_pack


def test_writing_a_pack_produces_a_tree_parse_asset_pack_accepts(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)

    pack = parse_asset_pack(
        json.loads(pack_path.read_text(encoding="utf-8")),
        repo_root=tmp_path,
    )

    assert pack.id == "first-room"
    assert len(pack.assets) > 0


def test_pack_manifest_defaults_include_every_base_asset(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path)

    assert doc["schema"] == PACK_SCHEMA
    asset_ids = {asset["id"] for asset in doc["assets"]}
    assert asset_ids == {"dwarf-idle", "dwarf-walk", "dwarf-swing", "lantern", "cave", "mining"}


def test_pack_manifest_assets_override_applies(tmp_path: Path) -> None:
    doc = pack_doc(tmp_path, assets=[])

    assert doc["assets"] == []


def test_pack_manifest_preview_scene_override_applies(tmp_path: Path) -> None:
    custom_scene = {"kind": "custom"}

    doc = pack_doc(tmp_path, preview_scene=custom_scene)

    assert doc["preview_scene"] == custom_scene


def test_writing_a_pack_uses_a_document_override_verbatim(tmp_path: Path) -> None:
    doc = {"schema": PACK_SCHEMA, "id": "override-id"}

    pack_path = write_pack(tmp_path, doc)

    assert json.loads(pack_path.read_text(encoding="utf-8"))["id"] == "override-id"
