"""Behavioral proof for the dwarf walk and swing final-polish cases (issues #95 and #101).

Identity Lock, the edit-source-to-generation-source binding, padded seed
geometry, and the swing action canvas, as an existing bundle proves them. A walk
or swing case that asserts on `check_bundle`'s Identity Lock report is an
identity case rather than a check case; one that asserts on an initialization
outcome is an initialization case and lives in
tests/test_final_polish_init.py.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.final_polish import (
    InvalidBundleError,
    check_bundle as polish_check_bundle,
)
from pipeline.gate_evidence import sha256_file
from pipeline.identity_lock import load_canonical_cells
from pipeline.strip import load_provider_frames
from tests.support import polish_bundle as pb
from tests.support.final_polish_testkit import (
    FRAME_COUNT,
    IDENTITY_PNG,
    LOGICAL_SIZE,
    PASS_STRIP,
    SWING_BUNDLE,
    SWING_POLISHED,
    WALK_STRIP,
    check_bundle,
    finalize_bundle,
    identity_doc_with_seed_pad_px,
    set_opaque_rgb,
    swing_provider_strip,
)
from tests.support.polish_bundle import bundle_store_env_context
from tests.support.polish_review_fixture import write_passing_reviews


def _init_bundle_polish(
    strip: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    """Bundle construction via the polish_bundle seam (issues #249, #250)."""
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=polish_profile)
    pb.init_bundle(attempt, bundle)


def _init_passing_bundle(tmp_path: Path) -> Path:
    """Idle bundle construction via the polish_bundle seam (issue #249)."""
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    pb.init_bundle(attempt, bundle)
    return bundle


SWING_24X24_ALPHA_BBOX = (
    (1, 16, 0, 23),
    (1, 16, 0, 23),
    (1, 16, 1, 23),
    (2, 16, 0, 23),
)
SWING_OPAQUE_COUNT = 268
SWING_CELL_AUTHORED_RGB_MULTISSET = {
    (74, 59, 72): 22,
    (43, 34, 48): 2,
    (47, 96, 117): 9,
    (143, 196, 197): 1,
    (17, 16, 24): 53,
    (98, 81, 93): 2,
    (29, 59, 80): 8,
    (78, 141, 160): 7,
    (190, 98, 34): 2,
    (128, 106, 115): 2,
    (40, 91, 67): 12,
    (255, 214, 107): 1,
    (25, 58, 50): 19,
    (240, 163, 58): 4,
    (165, 140, 145): 2,
    (29, 23, 32): 18,
    (120, 58, 24): 4,
    (147, 86, 49): 15,
    (200, 123, 67): 4,
    (59, 34, 27): 37,
    (243, 188, 130): 1,
    (98, 55, 34): 18,
    (66, 128, 90): 13,
    (108, 61, 49): 12,
}


def _check_bundle_slicing_from(
    bundle: Path,
    ingest_source: Path,
) -> FinalPolishCheckResult:
    with (
        bundle_store_env_context(bundle),
        patch(
            "pipeline.final_polish.load_provider_frames",
            side_effect=lambda path, layout: load_provider_frames(ingest_source, layout),
        ),
    ):
        return polish_check_bundle(bundle)


def _write_tiled_identity_seed(path: Path) -> Path:
    """Mechanical four-copy of identity.png — the #127/#155 failure mode."""
    with Image.open(IDENTITY_PNG) as identity:
        cell = identity.convert("RGBA")
    frame_w, frame_h = cell.size
    gutter = 2
    magenta = (255, 0, 255, 255)
    strip = Image.new("RGBA", (frame_w * 4 + gutter * 3, frame_h), magenta)
    for index in range(4):
        strip.paste(cell, (index * (frame_w + gutter), 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(path)
    return path


def test_dwarf_walk_check_rejects_edit_source_that_is_not_generation_source(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    wrong_seed = _write_tiled_identity_seed(tmp_path / "tiled-identity-seed.png")
    edit_dest = bundle / "provider" / "edit-source.png"
    shutil.copy2(wrong_seed, edit_dest)
    provenance_path = bundle / "provider" / "source.source.json"
    record = json.loads(provenance_path.read_text())
    record["edit_source_sha256"] = sha256_file(edit_dest)
    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["edit_source"]["sha256"] = sha256_file(edit_dest)
    manifest["provenance"]["sha256"] = sha256_file(provenance_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "edit_source_not_generation_source"


def test_dwarf_walk_check_accepts_correct_padded_edit_source_when_seed_pad_px_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # identity.json's production seed_pad_px is already 64 (this monkeypatch's
    # value), so the default polish_bundle seam already exercises this case
    # with no override needed.
    monkeypatch.setattr(
        "pipeline.final_polish._load_dwarf_identity_doc",
        lambda: identity_doc_with_seed_pad_px(),
    )
    bundle = tmp_path / "bundle"
    _init_bundle_polish(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    _check_bundle_slicing_from(bundle, WALK_STRIP)


def test_dwarf_walk_check_exposes_identity_lock_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
    result = _check_bundle_slicing_from(bundle, WALK_STRIP)
    assert result.identity_lock is not None
    assert result.identity_lock.motion_class == "walk"
    assert len(result.identity_lock.per_frame) == FRAME_COUNT


def _swing_opaque_rgb_multiset(cells: list[list[tuple[int, int, int] | None]]) -> Counter[tuple[int, int, int]]:
    return Counter(cell for row in cells for cell in row if cell is not None)


def _swing_alpha_bbox(cells: list[list[tuple[int, int, int] | None]]) -> tuple[int, int, int, int]:
    xs: list[int] = []
    ys: list[int] = []
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                xs.append(x)
                ys.append(y)
    return min(xs), max(xs), min(ys), max(ys)


def _swing_boundary_column_load(cells: list[list[tuple[int, int, int] | None]]) -> tuple[int, int]:
    width = len(cells[0])
    left = sum(1 for row in cells if row[0] is not None)
    right = sum(1 for row in cells if row[width - 1] is not None)
    return left, right


def test_production_swing_polished_frames_are_24x24_with_zero_boundary_load() -> None:
    for index in range(FRAME_COUNT):
        path = SWING_POLISHED / f"frame-{index}.png"
        cells = read_cells(path, size=(24, 24))
        assert _swing_alpha_bbox(cells) == SWING_24X24_ALPHA_BBOX[index]
        assert _swing_boundary_column_load(cells) == (0, 0)


def test_production_swing_polished_frames_preserve_cell_authored_subject_pixels() -> None:
    for index in range(FRAME_COUNT):
        cells = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
        assert sum(1 for row in cells for cell in row if cell is not None) == SWING_OPAQUE_COUNT
        assert dict(_swing_opaque_rgb_multiset(cells)) == SWING_CELL_AUTHORED_RGB_MULTISSET


def test_production_swing_audit_records_cell_author_pose_plan_status() -> None:
    audit = json.loads((SWING_BUNDLE / "reports" / "audit.json").read_text(encoding="utf-8"))
    summary = audit["machine_check"]["edit_summary"]
    assert "motion-pose-plan/1" in summary
    assert audit["superseded_evidence"]["provider_swing_acquisition"]["immutable_report"].startswith(
        "reports/"
    )
    assert audit["uncertain_count"] == 0
    assert audit["overall"] == "PASS"
    assert all(answer["verdict"] != "UNCERTAIN" for answer in audit["answers"])


def test_dwarf_swing_check_exposes_identity_lock_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(
        swing_provider_strip(tmp_path),
        "swing",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
    )
    swing_strip = swing_provider_strip(tmp_path)
    result = _check_bundle_slicing_from(bundle, swing_strip)
    assert result.identity_lock is not None
    assert result.identity_lock.motion_class == "swing"
    assert len(result.identity_lock.per_frame) == FRAME_COUNT
    assert result.provider_post_edit is not None
    assert result.provider_post_edit["magenta_wipe"]["outcome"] == "PASS"
    # Corpus swing is not an idle-seed edit — continuity must FAIL at check_bundle.
    assert result.provider_post_edit["outcome"] == "FAIL"
    assert result.provider_post_edit["reason_code"] == "edit_source_continuity_fail"
    assert result.outcome == "FAIL"


def test_dwarf_swing_check_does_not_trip_magenta_wipe_with_padded_edit_source(
    tmp_path: Path,
) -> None:
    import numpy as np

    bundle = tmp_path / "bundle"
    _init_bundle_polish(
        swing_provider_strip(tmp_path),
        "swing",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
    )
    provider_path = bundle / "provider" / "source.png"
    image = Image.open(provider_path).convert("RGBA")
    arr = np.asarray(image).copy()
    near = (
        (np.abs(arr[:, :, 0].astype(np.int16) - 255) <= 40)
        & (np.abs(arr[:, :, 1].astype(np.int16) - 0) <= 40)
        & (np.abs(arr[:, :, 2].astype(np.int16) - 255) <= 40)
    )
    arr[near] = (255, 0, 255, 255)
    Image.fromarray(arr).save(provider_path)

    new_sha = sha256_file(provider_path)
    provenance_path = bundle / "provider" / "source.source.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["raw_sha256"] = new_sha
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    ledger_path = bundle / "provider" / "attempts.json"
    ledger = json.loads(ledger_path.read_text())
    for row in ledger["attempts"]:
        if row.get("selected"):
            row["raw_sha256"] = new_sha
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provider"]["sha256"] = new_sha
    manifest["provenance"]["sha256"] = sha256_file(provenance_path)
    manifest["attempt_ledger"]["sha256"] = sha256_file(ledger_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    store_root = tmp_path / "acquisition-controls"
    raw_path = store_root / "raw" / f"{provenance['attempt_id']}.png"
    shutil.copy2(provider_path, raw_path)
    attempts_path = store_root / "attempts.jsonl"
    lines = attempts_path.read_text().splitlines()
    updated: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("attempt_id") == provenance["attempt_id"]:
            row["raw_sha256"] = new_sha
        updated.append(json.dumps(row, sort_keys=True))
    attempts_path.write_text("\n".join(updated) + "\n")

    swing_strip = swing_provider_strip(tmp_path)
    result = _check_bundle_slicing_from(bundle, swing_strip)
    assert result.outcome == "FAIL"
    assert result.provider_post_edit is not None
    assert result.provider_post_edit["magenta_wipe"]["outcome"] == "PASS"


def test_identity_lock_fail_blocks_release_despite_passing_structural_and_coherence(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
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
    set_opaque_rgb(polished, locked_x, locked_y, replacement)
    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(WALK_STRIP, layout),
    ):
        result = check_bundle(bundle)
        assert result.identity_lock is not None
        assert result.identity_lock.outcome == "FAIL"
        assert result.structural.pass_
        assert result.coherence.get("outcome") == "PASS"
        assert result.outcome == "FAIL"
        write_passing_reviews(bundle)
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
