"""Proof for cave Autotile edge-compat and Terraced Shaft audit (issue #108)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pipeline.cave_autotile_audit import (
    TERRACED_SHAFT_SOLID,
    build_edge_compat_report,
    edge_compat_payload,
    neighbor_mask,
    render_terraced_shaft,
    variant_for_cell,
)
from pipeline.gate_evidence import sha256_file
from pipeline.static_asset import check_static_bundle

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "assets" / "first-room" / "cave"

C1_PROMPT = """TRUE chunky pixel art static tile sheet only. Forty-eight 32×32 logical MINEABLE ROCK BLOCKS in an exact 8-column × 6-row grid, rendered large as crisp square Cells. Two full magenta #FF00FF logical gutter Cells between every item. Flat magenta keyed background. No labels, numbers, margins, anti-aliasing, blur, gradients, or dithering.

Warm rugged storybook cave rock using only the first-room Master Palette dark/outline and stone ramps. Neutral upper-left local light. Each block is a solid 32×32 mining target with selective warm-dark outer outline, readable chipped exposed faces, and quieter connected faces.

The sheet contains every north/east/south/west cardinal neighbor mask 0–15, repeated for three interior texture variants A, B, C. Within each 16-item run, row-major mask order is numeric 0 through 15. A set neighbor bit means that side connects seamlessly to solid rock; a missing bit means that side has a visibly exposed cave edge. Connected sides must tile without a seam. Exposed upper/left edges receive restrained highlights; exposed lower/right edges receive warm shadow.

Variants A/B/C change only interior crack and speck placement. They preserve identical edge geometry for the same mask. Avoid face-like patterns, large unique landmarks, ore, moss, roots, timber, lantern light, or cyan/amber emission. Texture stays subordinate to the dwarf and ore.

Intended read: substantial mineable stone blocks with clear boundaries at native scale, enough variation for a Terraced Shaft without wallpaper repetition."""


def _canonical_json(value: object) -> object:
    return json.loads(json.dumps(value, sort_keys=True))


def test_cave_bundle_finalizes_forty_eight_mineable_blocks() -> None:
    assert BUNDLE.is_dir()
    release = list((BUNDLE / "release" / "blocks").glob("*/*.png"))
    assert len(release) == 48
    for variant in ("a", "b", "c"):
        for mask in range(16):
            path = BUNDLE / "release" / "blocks" / variant / f"mask-{mask:02d}.png"
            assert path.is_file(), path


def test_cave_finalize_report_verifies_forty_eight_release_items() -> None:
    reports = list((BUNDLE / "reports").glob("*.json"))
    finalize_reports = [
        path
        for path in reports
        if path.name != "edge-compat.json"
        and path.name != "terraced-shaft-audit.json"
        and path.name != "visual-audit.json"
    ]
    assert len(finalize_reports) == 1
    report = json.loads(finalize_reports[0].read_text(encoding="utf-8"))
    assert report["schema"] == "static-asset-report/0"
    assert report["outcome"] == "PASS"
    assert len(report["release_items"]) == 48


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


def test_provenance_binds_exact_c1_prompt_palette_and_provider_hash() -> None:
    provenance = json.loads(
        (BUNDLE / "provider" / "source.source.json").read_text(encoding="utf-8")
    )
    provider = BUNDLE / "provider" / "source.png"
    assert provenance["prompt"] == C1_PROMPT
    assert provenance["prompt_text"] == C1_PROMPT
    assert provenance["prompt_sha256"] == hashlib.sha256(C1_PROMPT.encode("utf-8")).hexdigest()
    assert provenance["raw_sha256"] == sha256_file(provider)
    assert provenance["raw_path"] == "assets/first-room/cave/provider/source.png"
    assert provenance["master_palette_id"] == "first-room"
    assert provenance["item_geometry"]["item_count"] == 48


def test_compatible_autotile_edges_match_across_kit() -> None:
    report = build_edge_compat_report(BUNDLE)
    assert report.outcome == "PASS"
    assert report.pair_failures == 0
    assert report.geometry_failures == 0
    assert report.exposed_distinct_pass
    payload = edge_compat_payload(report, BUNDLE)
    checked = json.loads((BUNDLE / "reports" / "edge-compat.json").read_text())
    assert _canonical_json(payload) == _canonical_json(checked)


def test_terraced_shaft_render_matches_committed_audit(tmp_path: Path) -> None:
    committed_preview = BUNDLE / "reports" / "terraced-shaft-preview.png"
    preview = tmp_path / "terraced-shaft-preview.png"
    rendered = render_terraced_shaft(BUNDLE, out_path=preview)
    assert rendered["overall"] == "PASS"
    assert rendered["dimensions"] == [320, 160]
    assert all(rendered["machine_checks"].values())
    assert preview.is_file()

    committed = json.loads((BUNDLE / "reports" / "terraced-shaft-audit.json").read_text())
    # image.relative_path in the payload names the committed artifact, not the
    # tmp_path copy this test rendered into; the digest is compared explicitly
    # against the committed file's own sha256 rather than folded into the
    # blanket equality below.
    assert rendered["image"]["relative_path"] == (
        "assets/first-room/cave/reports/terraced-shaft-preview.png"
    )
    assert rendered["image"]["sha256"] == sha256_file(committed_preview)
    rendered_without_image = {k: v for k, v in rendered.items() if k != "image"}
    committed_without_image = {k: v for k, v in committed.items() if k != "image"}
    assert _canonical_json(rendered_without_image) == _canonical_json(committed_without_image)
    assert committed["inspection"]["walking_terraces_legible"] == "PASS"
    assert committed["inspection"]["vertical_mining_space_legible"] == "PASS"
    assert committed["inspection"]["block_boundaries_legible"] == "PASS"


def test_terraced_shaft_neighbor_masks_follow_cardinal_bits() -> None:
    assert neighbor_mask(TERRACED_SHAFT_SOLID, 0, 0) == 0b0110  # E|S
    assert neighbor_mask(TERRACED_SHAFT_SOLID, 4, 2) == 0b1010  # E|W
    assert variant_for_cell(0, 0) == "a"
    assert variant_for_cell(1, 0) == "b"
    assert variant_for_cell(2, 0) == "c"
