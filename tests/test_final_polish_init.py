"""Behavioral proof for pipeline.final_polish initialization (issues #95 and #101).

`initialize_bundle`: what a bundle looks like the moment it exists, which
provenance and edit-source records are accepted, and which initializations are
rejected before any bundle is written. A dwarf walk or swing case that asserts
on an initialization outcome belongs here rather than in
tests/test_final_polish_identity.py, which holds the same subjects once a bundle
exists.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.final_polish import (
    ATTEMPT_LEDGER_SCHEMA,
    BUNDLE_SCHEMA,
    BundleExistsError,
    FinalPolishError,
    InitializationRejectedError,
    PROVENANCE_SCHEMA,
    initialize_bundle,
    load_polish_brief,
)
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import build_identity_seed
from pipeline.final_polish_cli import main as final_polish_cli_main
from pipeline.strip import (
    IngestResult,
    ingest_strip_provider,
    layout_for_motion_class,
)
from tests.final_polish_harness import (
    acquisition_store_env,
    record_store_attempt,
)
from tests.support import polish_bundle as pb

from tests.support.final_polish_fixtures import (
    CANONICAL_IDENTITY_SHA,
    FRAME_COUNT,
    IDENTITY_PNG,
    INBOX,
    LANTERN_STRIP,
    LOGICAL_SIZE,
    PASS_STRIP,
    ROOT,
    SWING_POLISHED,
    SWING_STRIP,
    WALK_STRIP,
    _IDLE_STORE_ATTEMPT_KWARGS,
    _bundle_tree,
    _corpus_layout,
    _identity_doc_with_seed_pad_px,
    _init_bundle,
    _padded_edit_source_seed,
    _provenance_for,
    _provider_dimensions,
    _swing_padded_inbox_provider,
    _swing_provider_frame_cells,
    _swing_provider_on_edit_canvas,
    _swing_provider_strip,
    _walk_provider_on_edit_canvas,
    _write_animation_provenance,
)


FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
IDLE_SEED_STRIP = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"


def _init_bundle_polish(
    strip: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    """Idle/blob_idle/emissive/lantern bundle construction via the polish_bundle seam.

    Walk and swing call sites in this module still build through the interim
    `tests.support.final_polish_fixtures._init_bundle`; only idle, blob_idle,
    emissive, and lantern-Strip sites route through this seam (issue #249).
    """
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=polish_profile)
    pb.init_bundle(attempt, bundle)


def _init_passing_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)
    return bundle


def test_passing_corpus_strip_initializes_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)

    assert bundle.is_dir()
    assert (bundle / "manifest.json").is_file()
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["motion_class"] == "idle"
    assert manifest["layout"]["frame_w"] == 16
    assert manifest["layout"]["frame_h"] == 24
    assert manifest["layout"]["frame_count"] == 4


def test_profiled_bundle_embeds_hash_bound_miner_profile(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")

    manifest = json.loads((bundle / "manifest.json").read_text())
    profile = json.loads((bundle / "profile.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["polish_profile"] == {
        "schema": "polish-profile/0",
        "id": "miner",
        "relative_path": "profile.json",
        "sha256": sha256_file(bundle / "profile.json"),
    }
    assert profile["schema"] == "polish-profile/0"
    assert profile["id"] == "miner"


def test_miner_profile_declares_fixed_questions_and_motion_overrides(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    profile = json.loads((bundle / "profile.json").read_text())

    assert profile["verdicts"] == ["PASS", "EDIT", "UNCERTAIN"]
    assert [row["id"] for row in profile["fixed_questions"]] == [
        "identity_anchors",
        "semantic_separation",
        "temporal_consistency",
        "native_scale_contrast",
        "outline_continuity",
    ]
    assert [row["id"] for row in profile["motion_overrides"]["walk"]] == [
        "alternating_legs",
        "stable_belt_buckle",
    ]
    assert [row["id"] for row in profile["motion_overrides"]["swing"]] == [
        "face_hand_separation",
        "hand_tool_separation",
        "readable_tool_arc",
    ]
    assert profile["occlusion_rule"]
    assert profile["editing_rules"]
    assert profile["audit_workflow"]


DWARF_MINER_FIXED_IDS = [
    "identity_anchors",
    "identity_lock_pass",
    "black_eye_no_sclera",
    "native_scale_separation",
    "palette_lighting_outline",
    "temporal_consistency",
]
DWARF_MINER_WALK_IDS = ["alternating_legs", "stable_torso"]
DWARF_MINER_SWING_IDS = [
    "readable_anticipation",
    "continuous_pickaxe_arc",
    "hand_handle_separation",
    "planted_boots",
    "contact_readability_frame3",
]
LANTERN_FIXED_IDS = [
    "stable_housing_hang",
    "intentional_amber_core",
    "flame_core_housing_separation",
    "upper_left_metal_highlights",
    "closed_four_frame_loop",
]
LANTERN_EMISSIVE_IDS = ["emission_inside_lamp", "no_terrain_halo"]


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class", "fixed_ids", "motion_key", "motion_ids"),
    [
        (
            "dwarf-miner",
            PASS_STRIP,
            "idle",
            DWARF_MINER_FIXED_IDS,
            "walk",
            DWARF_MINER_WALK_IDS,
        ),
        (
            "lantern",
            LANTERN_STRIP,
            "emissive",
            LANTERN_FIXED_IDS,
            "emissive",
            LANTERN_EMISSIVE_IDS,
        ),
    ],
)
def test_production_profile_declares_fixed_questions_and_motion_overrides(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
    fixed_ids: list[str],
    motion_key: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    profile = json.loads((bundle / "profile.json").read_text())

    assert profile["schema"] == "polish-profile/0"
    assert profile["id"] == profile_id
    assert profile["verdicts"] == ["PASS", "EDIT", "UNCERTAIN"]
    assert [row["id"] for row in profile["fixed_questions"]] == fixed_ids
    assert [row["id"] for row in profile["motion_overrides"][motion_key]] == motion_ids
    assert profile["occlusion_rule"]
    assert profile["editing_rules"]
    assert profile["audit_workflow"]


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class"),
    [
        ("dwarf-miner", PASS_STRIP, "idle"),
        ("lantern", LANTERN_STRIP, "emissive"),
    ],
)
def test_production_profiled_bundle_embeds_hash_bound_profile(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)

    manifest = json.loads((bundle / "manifest.json").read_text())
    profile = json.loads((bundle / "profile.json").read_text())
    assert manifest["polish_profile"] == {
        "schema": "polish-profile/0",
        "id": profile_id,
        "relative_path": "profile.json",
        "sha256": sha256_file(bundle / "profile.json"),
    }
    assert profile["id"] == profile_id


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class", "motion_key", "motion_ids"),
    [
        ("dwarf-miner", WALK_STRIP, "walk", "walk", DWARF_MINER_WALK_IDS),
        ("dwarf-miner", "swing", "swing", "swing", DWARF_MINER_SWING_IDS),
        ("lantern", LANTERN_STRIP, "emissive", "emissive", LANTERN_EMISSIVE_IDS),
    ],
)
def test_production_polish_brief_selects_motion_overrides(
    tmp_path: Path,
    profile_id: str,
    strip: Path | str,
    motion_class: str,
    motion_key: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    provider_path = _swing_provider_strip(tmp_path) if strip == "swing" else strip
    _init_bundle_polish(provider_path, motion_class, bundle, tmp_path, polish_profile=profile_id)

    brief = load_polish_brief(bundle)
    assert brief["profile"]["id"] == profile_id
    assert brief["motion_class"] == motion_class
    assert [row["id"] for row in brief["motion_questions"]] == motion_ids


def test_readme_documents_production_polish_profiles() -> None:
    text = (ROOT / "README.md").read_text()
    for profile_id in ("dwarf-miner", "lantern", "miner"):
        assert profile_id in text
    assert "does not recognize the semantic questions in any profile" in text
    assert "--provenance" in text
    assert "--identity-reference" in text
    assert "--edit-source" in text
    assert "image-edit" in text
    assert "final-polish-bundle/2" in text or "schema `/2`" in text


def test_strip_contract_documents_animation_provenance_enforcement() -> None:
    text = (ROOT / "docs" / "strip-acquisition-contract.md").read_text()
    assert "animation-strip-provenance/0" in text
    assert "animation-attempt-ledger/0" in text
    assert "final-polish-bundle/2" in text
    assert "--identity-reference" in text
    assert "image-edit" in text


def test_unknown_profile_creates_no_partial_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    with pytest.raises(FinalPolishError) as exc:
        _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="missing")
    assert exc.value.reason_code == "unknown_polish_profile"
    assert not bundle.exists()


def test_polish_brief_selects_fixed_questions_and_walk_overrides(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="miner")

    brief = load_polish_brief(bundle)
    assert brief["profile"]["id"] == "miner"
    assert brief["profile"]["sha256"] == sha256_file(bundle / "profile.json")
    assert brief["motion_class"] == "walk"
    assert [row["id"] for row in brief["fixed_questions"]] == [
        "identity_anchors",
        "semantic_separation",
        "temporal_consistency",
        "native_scale_contrast",
        "outline_continuity",
    ]
    assert [row["id"] for row in brief["motion_questions"]] == [
        "alternating_legs",
        "stable_belt_buckle",
    ]
    assert brief["editing_rules"]
    assert brief["audit_workflow"]
    assert brief["verdicts"] == ["PASS", "EDIT", "UNCERTAIN"]


def test_fail_strip_creates_nothing(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError):
        _init_bundle_polish(FAIL_STRIP, "idle", bundle, tmp_path)
    assert not bundle.exists()


def test_review_strip_creates_nothing(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    base = ingest_strip_provider(PASS_STRIP, _corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    # pb.init_bundle always recomputes its own ingest result from
    # tests.support.polish_bundle's imported ingest_strip_provider before
    # re-patching pipeline.final_polish's reference (see init_bundle's
    # base_ingest branch), so the REVIEW outcome must be injected at that
    # source rather than at pipeline.final_polish.ingest_strip_provider.
    with patch("tests.support.polish_bundle.ingest_strip_provider", return_value=review):
        with pytest.raises(InitializationRejectedError):
            _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)
    assert not bundle.exists()


def test_init_materializes_swing_frames_on_the_motion_class_canvas(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(
        _swing_provider_strip(tmp_path),
        "swing",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
    )

    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["motion_class"] == "swing"
    assert manifest["layout"]["frame_w"] == 24
    assert manifest["layout"]["frame_h"] == 24
    for layer in ("draft", "polished"):
        for index in range(FRAME_COUNT):
            cells = read_cells(bundle / layer / f"frame-{index}.png")
            polished = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
            expected = _swing_provider_frame_cells(polished)
            assert (len(cells[0]), len(cells)) == (24, 24)
            assert cells == expected
            assert any(row[x] is not None for row in cells for x in range(4))


@pytest.mark.parametrize(
    "motion_class",
    ["idle", "blob_idle", "walk", "airborne", "emissive"],
)
def test_non_swing_probe_layout_matches_corpus_layout(motion_class: str) -> None:
    probe = layout_for_motion_class(motion_class, margin_cells=0)
    corpus = _corpus_layout()
    assert probe == corpus


def test_swing_probe_layout_differs_only_in_frame_geometry() -> None:
    swing = layout_for_motion_class("swing", margin_cells=0)
    corpus = _corpus_layout()
    assert swing.frame_w == 24
    assert swing.frame_h == corpus.frame_h
    assert swing.frame_count == corpus.frame_count
    assert swing.gutter == corpus.gutter
    assert swing.pitch_px == corpus.pitch_px
    assert swing.margin_cells == corpus.margin_cells


def test_swing_init_rejects_16_cell_wide_provider(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    swing_seed = _padded_edit_source_seed(tmp_path, "swing")
    swing_provider = _swing_padded_inbox_provider(tmp_path)
    provenance_path = tmp_path / "swing.source.json"
    _write_animation_provenance(
        swing_provider,
        provenance_path,
        motion_class="swing",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(swing_seed),
    )
    with pytest.raises(InitializationRejectedError) as exc:
        _init_bundle(
            SWING_STRIP,
            "swing",
            bundle,
            tmp_path,
            polish_profile="dwarf-miner",
            provenance_path=provenance_path,
            identity_reference=IDENTITY_PNG,
            edit_source=swing_seed,
        )
    assert exc.value.reason_code == "wrong_size"
    assert not bundle.exists()


def test_existing_destination_is_preserved(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    marker = bundle / "keep.txt"
    marker.write_text("stay", encoding="utf-8")

    with pytest.raises(BundleExistsError):
        _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)

    assert marker.read_text(encoding="utf-8") == "stay"


def test_bundle_tree_schema_hashes_and_seeded_polished_copies(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())

    expected_paths = {
        "manifest.json",
        "provider/attempts.json",
        "provider/source.png",
        "provider/source.source.json",
        "draft/frame-0.png",
        "draft/frame-1.png",
        "draft/frame-2.png",
        "draft/frame-3.png",
        "polished/frame-0.png",
        "polished/frame-1.png",
        "polished/frame-2.png",
        "polished/frame-3.png",
    }
    assert _bundle_tree(bundle) == expected_paths

    assert manifest["provider"]["original_filename"].endswith(".png")
    assert manifest["provider"]["relative_path"] == "provider/source.png"
    assert manifest["provider"]["sha256"] == sha256_file(bundle / "provider" / "source.png")
    assert manifest["provider"]["sha256"] == sha256_file(PASS_STRIP)

    draft_entries = manifest["draft_frames"]
    assert [row["index"] for row in draft_entries] == [0, 1, 2, 3]
    for row in draft_entries:
        rel = row["relative_path"]
        assert row["sha256"] == sha256_file(bundle / rel)
        with Image.open(bundle / rel) as image:
            assert image.mode == "RGBA"
            assert image.size == LOGICAL_SIZE

    for index in range(FRAME_COUNT):
        draft = bundle / "draft" / f"frame-{index}.png"
        polished = bundle / "polished" / f"frame-{index}.png"
        assert sha256_file(draft) == sha256_file(polished)


def test_schema_v2_bundle_binds_provenance_identity_and_edit_source_for_dwarf_walk(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["provenance"]["sha256"] == sha256_file(
        bundle / "provider" / "source.source.json"
    )
    assert manifest["attempt_ledger"]["sha256"] == sha256_file(bundle / "provider" / "attempts.json")
    assert manifest["identity_reference"]["sha256"] == sha256_file(bundle / "reference" / "identity.png")
    assert manifest["edit_source"]["sha256"] == sha256_file(bundle / "provider" / "edit-source.png")
    provenance = json.loads((bundle / "provider" / "source.source.json").read_text())
    assert provenance["schema"] == PROVENANCE_SCHEMA
    assert provenance["generation_mode"] == "image-edit"
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    assert ledger["schema"] == ATTEMPT_LEDGER_SCHEMA
    assert ledger["attempts"][-1]["selected"] is True


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("missing_field", "invalid_provenance"),
        ("bad_schema", "invalid_provenance"),
        ("prompt_sha256", "invalid_provenance"),
        ("raw_sha256", "provenance_hash_mismatch"),
        ("motion_class", "invalid_provenance"),
        ("generation_mode", "invalid_provenance"),
        ("edit_source_null_on_edit", "invalid_provenance"),
        ("edit_source_set_on_text", "invalid_provenance"),
        ("item_geometry", "invalid_provenance"),
        ("reference_identity", "reference_image_mismatch"),
    ],
)
def test_invalid_provenance_rejects_init_without_bundle(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = tmp_path / "bad.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    record = json.loads(provenance_path.read_text())

    if mutation == "missing_field":
        record.pop("model")
    elif mutation == "bad_schema":
        record["schema"] = "animation-strip-provenance/99"
    elif mutation == "prompt_sha256":
        record["prompt_sha256"] = "0" * 64
    elif mutation == "raw_sha256":
        record["raw_sha256"] = "0" * 64
    elif mutation == "motion_class":
        record["motion_class"] = "walk"
    elif mutation == "generation_mode":
        record["generation_mode"] = "invalid"
    elif mutation == "edit_source_null_on_edit":
        record["generation_mode"] = "image-edit"
        record["edit_source_sha256"] = None
        record["reference_image_sha256"] = [CANONICAL_IDENTITY_SHA]
    elif mutation == "edit_source_set_on_text":
        record["edit_source_sha256"] = sha256_file(IDLE_SEED_STRIP)
    elif mutation == "item_geometry":
        record["item_geometry"]["frame_w"] = 15
    elif mutation == "reference_identity":
        record["generation_mode"] = "image-edit"
        record["reference_image_sha256"] = ["0" * 64]
        record["edit_source_sha256"] = sha256_file(IDLE_SEED_STRIP)

    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    identity = IDENTITY_PNG if mutation in {"edit_source_null_on_edit", "reference_identity"} else None
    edit = IDLE_SEED_STRIP if mutation in {"edit_source_null_on_edit", "reference_identity"} else None

    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            PASS_STRIP,
            "idle",
            bundle,
            provenance_sidecar=provenance_path,
            identity_reference=identity,
            edit_source=edit,
        )
    assert exc.value.reason_code == reason_code
    assert not bundle.exists()


def _blank_raster(path: Path, width: int, height: int) -> Path:
    image = Image.new("RGBA", (width, height), (128, 128, 128, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def test_provenance_dimensions_mismatch_rejects_init(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = tmp_path / "bad-dimensions.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    record = json.loads(provenance_path.read_text())
    record["dimensions"] = [100, 200]
    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            PASS_STRIP,
            "idle",
            bundle,
            provenance_sidecar=provenance_path,
        )
    assert exc.value.reason_code == "provenance_dimensions_mismatch"
    assert not bundle.exists()


def test_provenance_dimensions_match_initializes(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = json.loads(
        (bundle / "provider" / "source.source.json").read_text(encoding="utf-8")
    )
    assert provenance["dimensions"] == _provider_dimensions(PASS_STRIP)


def test_edit_source_geometry_mismatch_rejects_init(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    provider = _blank_raster(tmp_path / "small-provider.png", 2308, 580)
    edit_source = _padded_edit_source_seed(tmp_path, "swing")
    provenance_path = tmp_path / "swing.source.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="swing",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(edit_source),
    )

    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            provider,
            "swing",
            bundle,
            provenance_sidecar=provenance_path,
            polish_profile="dwarf-miner",
            identity_reference=IDENTITY_PNG,
            edit_source=edit_source,
        )
    assert exc.value.reason_code == "edit_source_geometry_mismatch"
    edit_source_sha256 = sha256_file(edit_source)
    assert str(exc.value).startswith(
        "edit_source_geometry_mismatch: provider raster is 2308x580 but edit source "
        f"{edit_source_sha256} is 2432x1152"
    )
    assert not bundle.exists()


def test_edit_source_geometry_match_initializes(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    provider_dims = _provider_dimensions(bundle / "provider" / "source.png")
    edit_dims = _provider_dimensions(bundle / "provider" / "edit-source.png")
    assert provider_dims == edit_dims


def test_text_to_image_skips_edit_source_geometry_check(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    mismatched_edit = _padded_edit_source_seed(tmp_path, "swing")
    attempt = replace(pb.prepare(PASS_STRIP, "idle", tmp_path), edit_source=mismatched_edit)
    pb.init_bundle(attempt, bundle)
    assert bundle.exists()


def test_edit_source_geometry_mismatch_surfaces_reason_code_in_init_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = tmp_path / "bundle"
    provider = _blank_raster(tmp_path / "small-provider.png", 2308, 580)
    edit_source = _padded_edit_source_seed(tmp_path, "swing")
    provenance_path = tmp_path / "swing.source.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="swing",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(edit_source),
    )

    code = final_polish_cli_main(
        [
            "init",
            str(provider),
            "--motion-class",
            "swing",
            "--out",
            str(bundle),
            "--provenance",
            str(provenance_path),
            "--polish-profile",
            "dwarf-miner",
            "--identity-reference",
            str(IDENTITY_PNG),
            "--edit-source",
            str(edit_source),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert not bundle.exists()
    data = json.loads(captured.out)
    assert data["reason_code"] == "edit_source_geometry_mismatch"
    assert data["outcome"] == "FAIL"


def test_provenance_hash_mismatch_surfaces_reason_code_in_init_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = tmp_path / "bad-hash.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    record = json.loads(provenance_path.read_text())
    record["raw_sha256"] = "0" * 64
    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    code = final_polish_cli_main(
        [
            "init",
            str(PASS_STRIP),
            "--motion-class",
            "idle",
            "--out",
            str(bundle),
            "--provenance",
            str(provenance_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert not bundle.exists()
    data = json.loads(captured.out)
    assert data["reason_code"] == "provenance_hash_mismatch"
    assert data["outcome"] == "FAIL"


def test_provenance_dimensions_mismatch_surfaces_reason_code_in_init_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = tmp_path / "bad-dimensions.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    record = json.loads(provenance_path.read_text())
    record["dimensions"] = [100, 200]
    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")

    code = final_polish_cli_main(
        [
            "init",
            str(PASS_STRIP),
            "--motion-class",
            "idle",
            "--out",
            str(bundle),
            "--provenance",
            str(provenance_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert not bundle.exists()
    data = json.loads(captured.out)
    assert data["reason_code"] == "provenance_dimensions_mismatch"
    assert data["outcome"] == "FAIL"


def test_dwarf_walk_init_requires_identity_and_edit_source(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = _provenance_for(WALK_STRIP, tmp_path, "walk", polish_profile="dwarf-miner")
    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            WALK_STRIP,
            "walk",
            bundle,
            provenance_sidecar=provenance_path,
            polish_profile="dwarf-miner",
        )
    assert exc.value.reason_code == "missing_identity_reference"
    assert not bundle.exists()


def _wrong_padded_edit_source(tmp_path: Path, motion_class: str) -> Path:
    """Same canvas size as the canonical padded seed but a different digest."""
    canvas = _padded_edit_source_seed(tmp_path, motion_class)
    wrong = tmp_path / f"wrong-{motion_class}-edit-source.png"
    wrong.write_bytes(canvas.read_bytes())
    with Image.open(wrong) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        pixels[100, 100] = (0, 0, 0, 255)
        rgba.save(wrong)
    return wrong


def test_dwarf_walk_init_rejects_edit_source_that_is_not_generation_source(
    tmp_path: Path,
) -> None:
    walk_provider = _walk_provider_on_edit_canvas(tmp_path)
    wrong_seed = _wrong_padded_edit_source(tmp_path, "walk")
    provenance_path = tmp_path / "walk.source.json"
    _write_animation_provenance(
        walk_provider,
        provenance_path,
        motion_class="walk",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(wrong_seed),
    )
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            walk_provider,
            "walk",
            bundle,
            provenance_sidecar=provenance_path,
            polish_profile="dwarf-miner",
            identity_reference=IDENTITY_PNG,
            edit_source=wrong_seed,
        )
    assert exc.value.reason_code == "edit_source_not_generation_source"
    assert not bundle.exists()


def test_dwarf_walk_init_rejects_wrong_edit_source_when_seed_pad_px_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "pipeline.final_polish._load_dwarf_identity_doc",
        lambda: _identity_doc_with_seed_pad_px(),
    )
    wrong_seed = _wrong_padded_edit_source(tmp_path, "walk")
    provenance_path = tmp_path / "walk.source.json"
    _write_animation_provenance(
        _walk_provider_on_edit_canvas(tmp_path),
        provenance_path,
        motion_class="walk",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(wrong_seed),
    )
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            _walk_provider_on_edit_canvas(tmp_path),
            "walk",
            bundle,
            provenance_sidecar=provenance_path,
            polish_profile="dwarf-miner",
            identity_reference=IDENTITY_PNG,
            edit_source=wrong_seed,
        )
    assert exc.value.reason_code == "edit_source_not_generation_source"
    assert not bundle.exists()


def test_dwarf_walk_init_accepts_padded_edit_source_when_seed_pad_px_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_doc = _identity_doc_with_seed_pad_px()
    monkeypatch.setattr(
        "pipeline.final_polish._load_dwarf_identity_doc",
        lambda: identity_doc,
    )
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(identity_doc), encoding="utf-8")
    padded_seed = tmp_path / "padded-seed.png"
    build_identity_seed(declaration_path, padded_seed)
    provenance_path = tmp_path / "walk.source.json"
    walk_provider = _walk_provider_on_edit_canvas(tmp_path)
    _write_animation_provenance(
        walk_provider,
        provenance_path,
        motion_class="walk",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(padded_seed),
    )
    bundle = tmp_path / "bundle"
    _init_bundle(
        WALK_STRIP,
        "walk",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
        provenance_path=provenance_path,
        identity_reference=IDENTITY_PNG,
        edit_source=padded_seed,
    )
    assert bundle.exists()


def test_dwarf_swing_init_rejects_16_cell_pad_edit_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_doc = _identity_doc_with_seed_pad_px()
    monkeypatch.setattr(
        "pipeline.final_polish._load_dwarf_identity_doc",
        lambda: identity_doc,
    )
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(identity_doc), encoding="utf-8")
    padded_seed = tmp_path / "padded-seed.png"
    build_identity_seed(declaration_path, padded_seed)
    swing_provider = _swing_provider_on_edit_canvas(tmp_path)
    provenance_path = tmp_path / "swing.source.json"
    _write_animation_provenance(
        swing_provider,
        provenance_path,
        motion_class="swing",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(padded_seed),
    )
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError) as exc:
        initialize_bundle(
            swing_provider,
            "swing",
            bundle,
            provenance_sidecar=provenance_path,
            polish_profile="dwarf-miner",
            identity_reference=IDENTITY_PNG,
            edit_source=padded_seed,
        )
    assert exc.value.reason_code == "edit_source_not_generation_source"
    assert not bundle.exists()


def test_dwarf_walk_init_accepts_16_cell_pad_edit_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_doc = _identity_doc_with_seed_pad_px()
    monkeypatch.setattr(
        "pipeline.final_polish._load_dwarf_identity_doc",
        lambda: identity_doc,
    )
    declaration_path = tmp_path / "identity.json"
    declaration_path.write_text(json.dumps(identity_doc), encoding="utf-8")
    padded_seed = tmp_path / "padded-seed.png"
    build_identity_seed(declaration_path, padded_seed)
    provenance_path = tmp_path / "walk.source.json"
    walk_provider = _walk_provider_on_edit_canvas(tmp_path)
    _write_animation_provenance(
        walk_provider,
        provenance_path,
        motion_class="walk",
        generation_mode="image-edit",
        reference_image_sha256=[CANONICAL_IDENTITY_SHA],
        edit_source_sha256=sha256_file(padded_seed),
    )
    bundle = tmp_path / "bundle"
    _init_bundle(
        WALK_STRIP,
        "walk",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
        provenance_path=provenance_path,
        identity_reference=IDENTITY_PNG,
        edit_source=padded_seed,
    )
    assert bundle.exists()


def test_initialize_bundle_leaves_no_frame_staging_directory(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)
    staging_dirs = [
        path
        for path in bundle.rglob("*")
        if path.is_dir() and path.name == ".frame-staging"
    ]
    assert staging_dirs == []


def test_final_polish_has_no_pil_dependency() -> None:
    from pipeline import final_polish

    source = inspect.getsource(final_polish)
    assert "PIL" not in source


def test_initialize_projects_attempt_ledger_from_attested_store(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    first, _ = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="palette_drift")
    second, _ = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="identity_lock")
    third, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=third["attempt_id"],
        predecessor_attempt_id=third["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    assert len(ledger["attempts"]) == 3
    assert [row["attempt_id"] for row in ledger["attempts"]] == [
        first["attempt_id"],
        second["attempt_id"],
        third["attempt_id"],
    ]
    assert [row["raw_sha256"] for row in ledger["attempts"]] == [
        first["raw_sha256"],
        second["raw_sha256"],
        third["raw_sha256"],
    ]


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("unregistered_attempt_id", "not registered"),
        ("digest_mismatch", "raw_sha256 differs"),
        ("selected_rejected", "rejected Attempt cannot be selected"),
        ("prompt_sha256_mismatch", "prompt_sha256"),
        ("generation_mode_mismatch", "generation_mode"),
        ("motion_class_mismatch", "motion_class"),
    ],
)
def test_initialize_rejects_unregistered_attempts(
    tmp_path: Path,
    setup: str,
    message: str,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    row, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    attempt_id = row["attempt_id"]
    predecessor = row["predecessor_attempt_id"]
    motion_class = "idle"
    if setup == "selected_rejected":
        rejected, rejected_provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="palette_drift")
        attempt_id = rejected["attempt_id"]
        predecessor = rejected["predecessor_attempt_id"]
        provider = rejected_provider
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=attempt_id,
        predecessor_attempt_id=predecessor,
    )
    if setup == "unregistered_attempt_id":
        record = json.loads(provenance_path.read_text())
        record["attempt_id"] = "missing--attempt--999"
        provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    elif setup == "digest_mismatch":
        attempts_path = store_root / "attempts.jsonl"
        line = json.loads(attempts_path.read_text().strip())
        line["raw_sha256"] = "0" * 64
        attempts_path.write_text(json.dumps(line, sort_keys=True) + "\n")
        store_provenance_path = store_root / line["provenance_path"]
        store_provenance = json.loads(store_provenance_path.read_text())
        store_provenance["raw_sha256"] = "0" * 64
        store_provenance_path.write_text(
            json.dumps(store_provenance, indent=2, sort_keys=True) + "\n"
        )
    elif setup == "prompt_sha256_mismatch":
        _write_animation_provenance(
            provider,
            provenance_path,
            motion_class="idle",
            attempt_id=attempt_id,
            predecessor_attempt_id=predecessor,
            prompt_text="a different prompt than the store recorded",
        )
    elif setup == "generation_mode_mismatch":
        attempts_path = store_root / "attempts.jsonl"
        line = json.loads(attempts_path.read_text().strip())
        store_provenance_path = store_root / line["provenance_path"]
        store_provenance = json.loads(store_provenance_path.read_text())
        store_provenance["generation_mode"] = "image-edit"
        store_provenance_path.write_text(
            json.dumps(store_provenance, indent=2, sort_keys=True) + "\n"
        )
    elif setup == "motion_class_mismatch":
        attempts_path = store_root / "attempts.jsonl"
        line = json.loads(attempts_path.read_text().strip())
        store_provenance_path = store_root / line["provenance_path"]
        store_provenance = json.loads(store_provenance_path.read_text())
        store_provenance["motion_class"] = "walk"
        store_provenance_path.write_text(
            json.dumps(store_provenance, indent=2, sort_keys=True) + "\n"
        )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_bundle(provider, motion_class, bundle, provenance_sidecar=provenance_path)
    assert exc.value.reason_code == "attempt_not_registered"
    assert message in str(exc.value)


def test_initialize_projects_complete_store_chain(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    rows = [
        record_store_attempt(
            store_root,
            PASS_STRIP,
            "test/idle",
            repo_root=tmp_path,
            **_IDLE_STORE_ATTEMPT_KWARGS,
            outcome="rejected",
            rejection_reason="palette_drift",
        )[0]
        for _ in range(3)
    ]
    accepted, provider = record_store_attempt(
        store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS
    )
    rows.append(accepted)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    assert len(ledger["attempts"]) == 4


def test_initialize_rejects_when_store_chain_cannot_satisfy_ledger_rules(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="accepted")
    second, provider = record_store_attempt(
        store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS
    )
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=second["attempt_id"],
        predecessor_attempt_id=second["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    assert exc.value.reason_code == "attempt_not_registered"
