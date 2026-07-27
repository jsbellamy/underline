"""Proof for cave Autotile edge-compat and Terraced Shaft audit (issue #108)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.cave_autotile_audit import (
    TERRACED_SHAFT_SOLID,
    build_edge_compat_report,
    neighbor_mask,
    render_terraced_shaft,
    variant_for_cell,
)
from pipeline.gate_evidence import sha256_file
from pipeline.static_asset import check_static_bundle

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "first-room" / "cave"


def test_cave_bundle_finalizes_forty_eight_mineable_blocks() -> None:
    assert BUNDLE.is_dir()
    release = list((BUNDLE / "release" / "blocks").glob("*/*.png"))
    assert len(release) == 48
    for variant in ("a", "b", "c"):
        for mask in range(16):
            path = BUNDLE / "release" / "blocks" / variant / f"mask-{mask:02d}.png"
            assert path.is_file(), path


def test_cave_structural_check_passes() -> None:
    result = check_static_bundle(BUNDLE)
    assert result.outcome == "PASS"
    assert result.structural.pass_
    assert len(result.draft_hashes) == 48
    assert len(result.polished_hashes) == 48


def test_spec_orders_autotile_masks_across_three_variants() -> None:
    spec = json.loads((BUNDLE / "spec.json").read_text(encoding="utf-8"))
    assert spec["schema"] == "static-sheet-spec/0"
    assert spec["id"] == "first-room-cave-autotile"
    assert spec["cell_w"] == 32 and spec["cell_h"] == 32
    assert spec["columns"] == 8 and spec["rows"] == 6 and spec["gutter"] == 2
    assert len(spec["items"]) == 48
    assert spec["items"][0]["release_path"] == "blocks/a/mask-00.png"
    assert spec["items"][15]["release_path"] == "blocks/a/mask-15.png"
    assert spec["items"][16]["release_path"] == "blocks/b/mask-00.png"
    assert spec["items"][47]["release_path"] == "blocks/c/mask-15.png"
    palette_path = ROOT / spec["master_palette"]["path"]
    assert sha256_file(palette_path) == spec["master_palette"]["sha256"]


def test_provenance_binds_prompt_palette_and_provider_hash() -> None:
    provenance = json.loads(
        (BUNDLE / "provider" / "source.source.json").read_text(encoding="utf-8")
    )
    provider = BUNDLE / "provider" / "source.png"
    assert provenance["raw_sha256"] == sha256_file(provider)
    assert provenance["raw_path"] == "assets/first-room/cave/provider/source.png"
    assert "MINEABLE ROCK BLOCKS" in provenance["prompt"]
    assert provenance["master_palette_id"] == "first-room"
    assert provenance["item_geometry"]["item_count"] == 48
    assert provenance["prompt_sha256"]


def test_compatible_autotile_edges_match_across_kit() -> None:
    report = build_edge_compat_report(BUNDLE)
    assert report.outcome == "PASS"
    assert report.pair_failures == 0
    assert report.geometry_failures == 0
    assert report.exposed_distinct_pass
    checked = json.loads((BUNDLE / "reports" / "edge-compat.json").read_text())
    assert checked["outcome"] == "PASS"
    assert checked["pair_failures"] == 0


def test_terraced_shaft_render_passes_machine_audit(tmp_path: Path) -> None:
    out = tmp_path / "terraced-shaft-preview.png"
    rendered = render_terraced_shaft(BUNDLE, out_path=out)
    assert rendered["overall"] == "PASS"
    assert rendered["dimensions"] == [320, 160]
    assert all(rendered["machine_checks"].values())
    assert out.is_file()

    committed = json.loads((BUNDLE / "reports" / "terraced-shaft-audit.json").read_text())
    assert committed["overall"] == "PASS"
    image = BUNDLE / "reports" / "terraced-shaft-preview.png"
    assert image.is_file()
    assert committed["image"]["sha256"] == sha256_file(image)
    assert committed["inspection"]["walking_terraces_legible"] == "PASS"
    assert committed["inspection"]["vertical_mining_space_legible"] == "PASS"
    assert committed["inspection"]["block_boundaries_legible"] == "PASS"


def test_terraced_shaft_neighbor_masks_follow_cardinal_bits() -> None:
    assert neighbor_mask(TERRACED_SHAFT_SOLID, 0, 0) == 0b0110  # E|S
    assert neighbor_mask(TERRACED_SHAFT_SOLID, 4, 2) == 0b1010  # E|W
    assert variant_for_cell(0, 0) == "a"
    assert variant_for_cell(1, 0) == "b"
    assert variant_for_cell(2, 0) == "c"
