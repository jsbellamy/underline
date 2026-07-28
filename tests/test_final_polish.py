"""Behavioral proof for pipeline.final_polish (issues #95 and #101)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import adversarial
from pipeline import strip as S
from pipeline.final_polish import (
    ATTEMPT_LEDGER_SCHEMA,
    BUNDLE_SCHEMA,
    BUNDLE_SCHEMA_LEGACY_1,
    PROVENANCE_SCHEMA,
    REPORT_SCHEMA,
    BundleExistsError,
    FinalPolishError,
    InitializationRejectedError,
    InvalidBundleError,
    check_bundle,
    finalize_bundle,
    initialize_bundle,
    load_polish_brief,
)
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.identity_lock import load_canonical_cells
from pipeline.strip import DEFAULT_LAYOUT, IngestResult, StripLayout, ingest_strip_provider

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
WALK_STRIP = INBOX / "05-miner-walk.png"
SWING_STRIP = INBOX / "06-miner-swing.png"
LANTERN_STRIP = INBOX / "14-lantern-flicker.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDLE_SEED_STRIP = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
CANONICAL_IDENTITY_SHA = "db68353f559053abc4d77e8916d1db8a242f4f50eb4a1ef0d4b1f65c4bf650c9"
DWARF_IDLE_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "idle"
LOGICAL_SIZE = (DEFAULT_LAYOUT.frame_w, DEFAULT_LAYOUT.frame_h)
FRAME_COUNT = DEFAULT_LAYOUT.frame_count


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _provider_dimensions(provider_path: Path) -> list[int]:
    with Image.open(provider_path) as image:
        return [image.width, image.height]


def _item_geometry() -> dict[str, int]:
    return {
        "frame_w": DEFAULT_LAYOUT.frame_w,
        "frame_h": DEFAULT_LAYOUT.frame_h,
        "frame_count": DEFAULT_LAYOUT.frame_count,
        "gutter": DEFAULT_LAYOUT.gutter,
    }


def _write_animation_provenance(
    provider_path: Path,
    provenance_path: Path,
    *,
    motion_class: str,
    generation_mode: str = "text-to-image",
    attempt_id: str = "test--001",
    predecessor_attempt_id: str | None = None,
    reference_image_sha256: list[str] | None = None,
    edit_source_sha256: str | None = None,
    prompt_text: str = "underline test provenance prompt",
    **overrides: object,
) -> None:
    if reference_image_sha256 is None:
        reference_image_sha256 = []
    record: dict[str, object] = {
        "schema": PROVENANCE_SCHEMA,
        "specification_id": f"test/{motion_class}",
        "attempt_id": attempt_id,
        "predecessor_attempt_id": predecessor_attempt_id,
        "generator": "cursor-image-gen",
        "model": "cursor-image-gen",
        "prompt_text": prompt_text,
        "prompt_sha256": sha256_bytes(prompt_text.encode("utf-8")),
        "generation_mode": generation_mode,
        "reference_image_sha256": reference_image_sha256,
        "edit_source_sha256": edit_source_sha256,
        "generated_at": "2026-07-27T22:00:00+00:00",
        "acquiring_agent": "pytest",
        "repository_commit": "0000000000000000000000000000000000000000",
        "raw_path": str(provider_path),
        "raw_sha256": sha256_file(provider_path),
        "media_type": "image/png",
        "dimensions": _provider_dimensions(provider_path),
        "motion_class": motion_class,
        "master_palette_id": "first-room",
        "item_geometry": _item_geometry(),
    }
    record.update(overrides)
    provenance_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _provenance_for(
    provider_path: Path,
    tmp_path: Path,
    motion_class: str,
    *,
    polish_profile: str | None = None,
) -> Path:
    provenance_path = tmp_path / f"{provider_path.stem}.source.json"
    kwargs: dict[str, object] = {"motion_class": motion_class}
    if polish_profile == "dwarf-miner" and motion_class in {"walk", "swing"}:
        kwargs.update(
            {
                "generation_mode": "image-edit",
                "reference_image_sha256": [CANONICAL_IDENTITY_SHA],
                "edit_source_sha256": sha256_file(IDLE_SEED_STRIP),
            }
        )
    _write_animation_provenance(provider_path, provenance_path, **kwargs)
    return provenance_path


def _init_bundle(
    provider_path: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
    provenance_path: Path | None = None,
    identity_reference: Path | None = None,
    edit_source: Path | None = None,
) -> None:
    if provenance_path is None:
        provenance_path = _provenance_for(
            provider_path,
            tmp_path,
            motion_class,
            polish_profile=polish_profile,
        )
    if polish_profile == "dwarf-miner" and motion_class in {"walk", "swing"}:
        identity_reference = identity_reference or IDENTITY_PNG
        edit_source = edit_source or IDLE_SEED_STRIP
    initialize_bundle(
        provider_path,
        motion_class,
        bundle,
        provenance_sidecar=provenance_path,
        polish_profile=polish_profile,
        identity_reference=identity_reference,
        edit_source=edit_source,
    )


def _init_passing_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path)
    return bundle


def _load_frame_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _first_opaque_xy(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                if pixels[x, y][3] == 255:
                    return x, y
    raise AssertionError(f"no opaque cell in {path}")


def _set_opaque_rgb(path: Path, x: int, y: int, rgb: tuple[int, int, int]) -> None:
    image = _load_frame_rgba(path)
    pixels = image.load()
    assert pixels is not None
    pixels[x, y] = (*rgb, 255)
    image.save(path)


def _set_alpha(path: Path, x: int, y: int, alpha: int) -> None:
    image = _load_frame_rgba(path)
    pixels = image.load()
    assert pixels is not None
    r, g, b, _ = pixels[x, y]
    pixels[x, y] = (r, g, b, alpha)
    image.save(path)


def _bundle_tree(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def test_passing_corpus_strip_initializes_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path)

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
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")

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
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
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
    _init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
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
    _init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)

    manifest = json.loads((bundle / "manifest.json").read_text())
    profile = json.loads((bundle / "profile.json").read_text())
    assert manifest["polish_profile"] == {
        "schema": "polish-profile/0",
        "id": profile_id,
        "relative_path": "profile.json",
        "sha256": sha256_file(bundle / "profile.json"),
    }
    assert profile["id"] == profile_id


@pytest.mark.parametrize("profile_id", ["dwarf-miner", "lantern"])
def test_tampered_production_profile_is_an_invalid_bundle(
    tmp_path: Path,
    profile_id: str,
) -> None:
    strip = PASS_STRIP if profile_id == "dwarf-miner" else LANTERN_STRIP
    motion_class = "idle" if profile_id == "dwarf-miner" else "emissive"
    bundle = tmp_path / "bundle"
    _init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    profile = json.loads((bundle / "profile.json").read_text())
    profile["description"] = "tampered"
    (bundle / "profile.json").write_text(json.dumps(profile) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "profile_hash_mismatch"


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class", "motion_key", "motion_ids"),
    [
        ("dwarf-miner", WALK_STRIP, "walk", "walk", DWARF_MINER_WALK_IDS),
        ("dwarf-miner", SWING_STRIP, "swing", "swing", DWARF_MINER_SWING_IDS),
        ("lantern", LANTERN_STRIP, "emissive", "emissive", LANTERN_EMISSIVE_IDS),
    ],
)
def test_production_polish_brief_selects_motion_overrides(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
    motion_key: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)

    brief = load_polish_brief(bundle)
    assert brief["profile"]["id"] == profile_id
    assert brief["motion_class"] == motion_class
    assert [row["id"] for row in brief["motion_questions"]] == motion_ids


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class"),
    [
        ("dwarf-miner", PASS_STRIP, "idle"),
        ("lantern", LANTERN_STRIP, "emissive"),
    ],
)
def test_production_check_and_final_report_bind_embedded_profile(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    result = check_bundle(bundle)
    profile_hash = sha256_file(bundle / "profile.json")
    assert result.profile_id == profile_id
    assert result.profile_sha256 == profile_hash

    report = json.loads(finalize_bundle(bundle).read_text())
    assert report["polish_profile"] == {
        "id": profile_id,
        "sha256": profile_hash,
    }


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


def test_tampered_embedded_profile_is_an_invalid_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    profile = json.loads((bundle / "profile.json").read_text())
    profile["description"] = "tampered"
    (bundle / "profile.json").write_text(json.dumps(profile) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "profile_hash_mismatch"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("missing", "missing_profile"),
        ("malformed", "invalid_profile"),
        ("schema", "profile_identity_mismatch"),
        ("id", "profile_identity_mismatch"),
        ("content", "invalid_profile"),
    ],
)
def test_invalid_embedded_profiles_fail_closed(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    profile_path = bundle / "profile.json"
    manifest_path = bundle / "manifest.json"

    if mutation == "missing":
        profile_path.unlink()
    elif mutation == "malformed":
        profile_path.write_text("{not-json")
    else:
        profile = json.loads(profile_path.read_text())
        if mutation == "content":
            profile.pop("fixed_questions")
        else:
            profile[mutation] = "wrong"
        profile_path.write_text(json.dumps(profile) + "\n")

    if mutation != "missing":
        manifest = json.loads(manifest_path.read_text())
        manifest["polish_profile"]["sha256"] = sha256_file(profile_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == reason_code


def test_unknown_profile_creates_no_partial_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    with pytest.raises(FinalPolishError) as exc:
        _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="missing")
    assert exc.value.reason_code == "unknown_polish_profile"
    assert not bundle.exists()


def test_existing_v0_bundle_remains_check_compatible(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema"] = "final-polish-bundle/0"
    manifest.pop("polish_profile")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    assert check_bundle(bundle).outcome == "PASS"


def test_check_and_final_report_bind_embedded_profile(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    result = check_bundle(bundle)
    profile_hash = sha256_file(bundle / "profile.json")
    assert result.profile_id == "miner"
    assert result.profile_sha256 == profile_hash

    report = json.loads(finalize_bundle(bundle).read_text())
    assert report["polish_profile"] == {
        "id": "miner",
        "sha256": profile_hash,
    }


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
        _init_bundle(FAIL_STRIP, "idle", bundle, tmp_path)
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
    with patch("pipeline.final_polish.ingest_strip_provider", return_value=review):
        with pytest.raises(InitializationRejectedError):
            _init_bundle(PASS_STRIP, "idle", bundle, tmp_path)
    assert not bundle.exists()


def test_existing_destination_is_preserved(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    marker = bundle / "keep.txt"
    marker.write_text("stay", encoding="utf-8")

    with pytest.raises(BundleExistsError):
        _init_bundle(PASS_STRIP, "idle", bundle, tmp_path)

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

    assert manifest["provider"]["original_filename"] == PASS_STRIP.name
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


def test_provider_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provider = bundle / "provider" / "source.png"
    provider.write_bytes(provider.read_bytes() + b"\x00")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "provenance_hash_mismatch"


def test_draft_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    draft = bundle / "draft" / "frame-0.png"
    _set_opaque_rgb(draft, 0, 0, (1, 2, 3))

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "draft_hash_mismatch"


def test_provider_currently_review_is_reportable_without_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with patch("pipeline.final_polish.ingest_strip_provider", return_value=review):
        result = check_bundle(bundle)
        assert result.provider_outcome == "REVIEW"
        assert result.outcome == "REVIEW"

        finalize_bundle(bundle)
    assert not (bundle / "release").exists()
    assert len(list((bundle / "reports").glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("mutator", "reason_code"),
    [
        ("missing", "missing_frame"),
        ("extra", "extra_frame"),
        ("misordered", "misordered_frames"),
        ("unreadable", "unreadable_frame"),
        ("wrong_mode", "wrong_mode"),
        ("wrong_size", "wrong_size"),
        ("non_binary_alpha", "non_binary_alpha"),
    ],
)
def test_invalid_polished_frames_raise_stable_reason_codes(
    tmp_path: Path, mutator: str, reason_code: str
) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished"

    if mutator == "missing":
        (polished / "frame-3.png").unlink()
    elif mutator == "extra":
        shutil.copy(polished / "frame-0.png", polished / "frame-99.png")
    elif mutator == "misordered":
        (polished / "frame-0.png").rename(polished / "frame-9.png")
    elif mutator == "unreadable":
        (polished / "frame-1.png").write_bytes(b"not-a-png")
    elif mutator == "wrong_mode":
        with Image.open(polished / "frame-1.png") as image:
            image.convert("RGB").save(polished / "frame-1.png")
    elif mutator == "wrong_size":
        Image.new("RGBA", (15, 24), (0, 0, 0, 0)).save(polished / "frame-2.png")
    elif mutator == "non_binary_alpha":
        _set_alpha(polished / "frame-0.png", 1, 1, 128)

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == reason_code
    assert not list((bundle / "reports").glob("*.json"))


def test_alpha_mask_edit_fails_structurally(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_alpha(polished, x, y, 0)

    result = check_bundle(bundle)
    assert result.structural.pass_ is False
    assert result.structural.outcome == "FAIL"
    assert any(v.code == "alpha_mismatch" for v in result.structural.violations)


def test_new_opaque_color_fails_structurally(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = check_bundle(bundle)
    assert result.structural.pass_ is False
    assert any(v.code == "palette_violation" for v in result.structural.violations)


def test_reused_draft_palette_color_passes_structural_layer(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    draft_union: set[tuple[int, int, int]] = set()
    for index in range(FRAME_COUNT):
        with Image.open(bundle / "draft" / f"frame-{index}.png") as image:
            rgba = image.convert("RGBA")
            pixels = rgba.load()
            assert pixels is not None
            for y in range(LOGICAL_SIZE[1]):
                for x in range(LOGICAL_SIZE[0]):
                    r, g, b, a = pixels[x, y]
                    if a == 255:
                        draft_union.add((r, g, b))

    polished = bundle / "polished" / "frame-0.png"
    with Image.open(polished) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                _, _, _, a = pixels[x, y]
                if a == 0:
                    palette_color = next(iter(draft_union))
                    pixels[x, y] = (*palette_color, 255)
                    break
            else:
                continue
            break
        image.save(polished)

    result = check_bundle(bundle)
    assert result.structural.pass_ is True


def test_visible_cell_delta_order_and_counts(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished0 = bundle / "polished" / "frame-0.png"
    polished2 = bundle / "polished" / "frame-2.png"
    x0, y0 = _first_opaque_xy(polished0)
    x2, y2 = _first_opaque_xy(polished2)
    _set_opaque_rgb(polished0, x0, y0, (11, 22, 33))
    _set_opaque_rgb(polished2, x2, y2, (44, 55, 66))

    # transparent RGB-only change must not appear in delta
    with Image.open(polished0) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                _, _, _, a = pixels[x, y]
                if a == 0:
                    pixels[x, y] = (99, 88, 77, 0)
                    break
            else:
                continue
            break
        image.save(polished0)

    result = check_bundle(bundle)
    edits = result.delta.edits
    assert [(e.frame_index, e.x, e.y) for e in edits] == [(0, x0, y0), (2, x2, y2)]
    assert result.delta.per_frame_counts == (1, 0, 1, 0)
    assert result.delta.total_edits == 2


def test_zero_edit_real_bundle_passes_coherence(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    assert result.delta.total_edits == 0
    assert result.coherence["outcome"] == "PASS"
    assert result.outcome == "PASS"


def test_synthetic_recolour_reaches_coherence_split(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    frames = adversarial.real_frames("idle")
    mutated = adversarial.recolour(frames)
    polished_dir = bundle / "polished"
    for index in range(FRAME_COUNT):
        S.export_frames([mutated[index]], polished_dir, "swap", frame_w=16, frame_h=24)
        (polished_dir / "swap-f0.png").replace(polished_dir / f"frame-{index}.png")

    result = check_bundle(bundle)
    assert result.coherence["outcome"] == "FAIL"
    assert result.coherence["gate_outcomes"]["palette_drift_pass"]["outcome"] == "FAIL"
    assert result.outcome == "FAIL"


def test_check_is_read_only(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    before = _bundle_tree(bundle)
    check_bundle(bundle)
    assert _bundle_tree(bundle) == before


def test_finalize_records_immutable_report_and_pass_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    report_path = finalize_bundle(bundle)

    assert report_path.is_file()
    report = json.loads(report_path.read_text())
    assert report["schema"] == REPORT_SCHEMA
    assert report["outcome"] == "PASS"
    assert report["fingerprint"] == result.fingerprint
    assert len(report["release_frames"]) == FRAME_COUNT

    for index in range(FRAME_COUNT):
        release = bundle / "release" / f"frame-{index}.png"
        polished = bundle / "polished" / f"frame-{index}.png"
        assert release.is_file()
        assert sha256_file(release) == sha256_file(polished)


def test_finalize_fail_outcome_writes_report_without_release(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    _set_opaque_rgb(polished, 3, 5, (250, 1, 2))
    result = check_bundle(bundle)
    report_path = finalize_bundle(bundle)

    report = json.loads(report_path.read_text())
    assert report["outcome"] == "FAIL"
    assert not (bundle / "release").exists()


def test_repeat_finalize_is_idempotent(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    first = finalize_bundle(bundle)
    second = finalize_bundle(bundle)
    assert first == second
    assert json.loads(first.read_text()) == json.loads(second.read_text())


def test_conflicting_report_fails_closed(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    report_path = finalize_bundle(bundle)
    tampered = json.loads(report_path.read_text())
    tampered["outcome"] = "FAIL"
    report_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(InvalidBundleError) as exc:
        finalize_bundle(bundle)
    assert exc.value.reason_code == "report_conflict"


def test_conflicting_release_fails_closed(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    finalize_bundle(bundle)
    release = bundle / "release" / "frame-0.png"
    release.write_bytes(release.read_bytes() + b"x")

    with pytest.raises(InvalidBundleError) as exc:
        finalize_bundle(bundle)
    assert exc.value.reason_code == "release_conflict"


def test_existing_v1_idle_bundle_remains_check_compatible() -> None:
    result = check_bundle(DWARF_IDLE_BUNDLE)
    assert result.outcome == "PASS"
    manifest = json.loads((DWARF_IDLE_BUNDLE / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA_LEGACY_1


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


def test_tampered_v2_provenance_blocks_check_and_finalize(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = bundle / "provider" / "source.source.json"
    record = json.loads(provenance.read_text())
    record["attempt_id"] = "tampered"
    provenance.write_text(json.dumps(record) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "provenance_hash_mismatch"

    with pytest.raises(InvalidBundleError):
        finalize_bundle(bundle)


def _write_attempt_ledger(bundle: Path, attempts: list[dict[str, object]]) -> None:
    ledger_path = bundle / "provider" / "attempts.json"
    ledger_path.write_text(
        json.dumps({"schema": ATTEMPT_LEDGER_SCHEMA, "attempts": attempts}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempt_ledger"]["sha256"] = sha256_file(ledger_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_valid_sequential_attempt_ledger_passes_check(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance_path = bundle / "provider" / "source.source.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["attempt_id"] = "test--002"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provenance"]["sha256"] = sha256_file(provenance_path)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    first_raw = "1" * 64
    _write_attempt_ledger(
        bundle,
        [
            {
                "attempt_id": "test--001",
                "predecessor_attempt_id": None,
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "prompt_sha256": "a" * 64,
                "raw_sha256": first_raw,
                "selected": False,
            },
            {
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "outcome": "accepted",
                "rejection_reason": None,
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": provenance["raw_sha256"],
                "selected": True,
            },
        ],
    )
    assert check_bundle(bundle).outcome == "PASS"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("duplicate_id", "invalid_attempt_ledger"),
        ("two_selected", "invalid_attempt_ledger"),
        ("selected_not_final", "invalid_attempt_ledger"),
        ("missing_predecessor", "invalid_attempt_ledger"),
        ("cyclic", "invalid_attempt_ledger"),
        ("prompt_mismatch", "attempt_ledger_mismatch"),
    ],
)
def test_invalid_attempt_ledger_fails_closed(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = json.loads((bundle / "provider" / "source.source.json").read_text())
    base_row = {
        "attempt_id": provenance["attempt_id"],
        "predecessor_attempt_id": None,
        "outcome": "accepted",
        "rejection_reason": None,
        "prompt_sha256": provenance["prompt_sha256"],
        "raw_sha256": provenance["raw_sha256"],
        "selected": True,
    }
    attempts: list[dict[str, object]] = [dict(base_row)]

    if mutation == "duplicate_id":
        attempts = [dict(base_row), dict(base_row)]
        attempts[1]["selected"] = False
        attempts[1]["outcome"] = "rejected"
        attempts[1]["rejection_reason"] = "palette_drift"
    elif mutation == "two_selected":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": True,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": True,
            },
        ]
    elif mutation == "selected_not_final":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": False,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": False,
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
            },
        ]
    elif mutation == "missing_predecessor":
        attempts = [dict(base_row)]
        attempts[0]["predecessor_attempt_id"] = "missing--001"
    elif mutation == "cyclic":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "predecessor_attempt_id": "test--002",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": False,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": True,
            },
        ]
    elif mutation == "prompt_mismatch":
        attempts = [dict(base_row)]
        attempts[0]["prompt_sha256"] = "b" * 64

    _write_attempt_ledger(bundle, attempts)

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == reason_code


def test_dwarf_walk_check_exposes_identity_lock_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    result = check_bundle(bundle)
    assert result.identity_lock is not None
    assert result.identity_lock.outcome in {"PASS", "FAIL"}
    assert result.identity_lock.motion_class == "walk"
    assert len(result.identity_lock.per_frame) == FRAME_COUNT


def test_identity_lock_fail_blocks_release_despite_passing_structural_and_coherence(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    allowed_palette: set[tuple[int, int, int]] = set()
    for index in range(FRAME_COUNT):
        with Image.open(bundle / "draft" / f"frame-{index}.png") as image:
            rgba = image.convert("RGBA")
            pixels = rgba.load()
            assert pixels is not None
            for y in range(LOGICAL_SIZE[1]):
                for x in range(LOGICAL_SIZE[0]):
                    r, g, b, a = pixels[x, y]
                    if a == 255:
                        allowed_palette.add((int(r), int(g), int(b)))
    canonical = load_canonical_cells(IDENTITY_PNG, LOGICAL_SIZE)
    locked_x, locked_y = 8, 10
    canonical_rgb = canonical[locked_y][locked_x]
    replacement = next(
        rgb for rgb in allowed_palette if rgb != canonical_rgb
    )
    polished = bundle / "polished" / "frame-0.png"
    _set_opaque_rgb(polished, locked_x, locked_y, replacement)
    result = check_bundle(bundle)
    assert result.identity_lock is not None
    assert result.identity_lock.outcome == "FAIL"
    assert result.structural.pass_
    assert result.coherence.get("outcome") == "PASS"
    assert result.outcome == "FAIL"
    report_path = finalize_bundle(bundle)
    report = json.loads(report_path.read_text())
    assert report["identity_lock"]["outcome"] == "FAIL"
    assert report["outcome"] == "FAIL"
    assert "release_frames" not in report
    assert not (bundle / "release").exists()


def test_idle_bundle_has_no_identity_lock(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = check_bundle(bundle)
    assert result.identity_lock is None
