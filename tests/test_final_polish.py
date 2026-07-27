"""Behavioral proof for pipeline.final_polish (issue #95 C1–C8)."""

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
    BUNDLE_SCHEMA,
    REPORT_SCHEMA,
    BundleExistsError,
    InitializationRejectedError,
    InvalidBundleError,
    check_bundle,
    finalize_bundle,
    initialize_bundle,
)
from pipeline.gate_evidence import sha256_file
from pipeline.strip import DEFAULT_LAYOUT, IngestResult, StripLayout, ingest_strip_provider

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
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


def _init_passing_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    initialize_bundle(PASS_STRIP, "idle", bundle)
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
    initialize_bundle(PASS_STRIP, "idle", bundle)

    assert bundle.is_dir()
    assert (bundle / "manifest.json").is_file()
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["motion_class"] == "idle"
    assert manifest["layout"]["frame_w"] == 16
    assert manifest["layout"]["frame_h"] == 24
    assert manifest["layout"]["frame_count"] == 4


def test_fail_strip_creates_nothing(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    with pytest.raises(InitializationRejectedError):
        initialize_bundle(FAIL_STRIP, "idle", bundle)
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
            initialize_bundle(PASS_STRIP, "idle", bundle)
    assert not bundle.exists()


def test_existing_destination_is_preserved(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    marker = bundle / "keep.txt"
    marker.write_text("stay", encoding="utf-8")

    with pytest.raises(BundleExistsError):
        initialize_bundle(PASS_STRIP, "idle", bundle)

    assert marker.read_text(encoding="utf-8") == "stay"


def test_bundle_tree_schema_hashes_and_seeded_polished_copies(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())

    expected_paths = {
        "manifest.json",
        "provider/source.png",
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
    assert exc.value.reason_code == "provider_hash_mismatch"


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
