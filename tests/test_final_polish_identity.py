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
from pipeline.identity_lock import (
    build_identity_seed,
    load_canonical_cells,
)
from pipeline.strip import load_provider_frames
from tests.final_polish_harness import bundle_store_env_context

from tests.support.final_polish_fixtures import (
    FRAME_COUNT,
    IDENTITY_PNG,
    LOGICAL_SIZE,
    SWING_BUNDLE,
    SWING_POLISHED,
    WALK_STRIP,
    _check_bundle,
    _finalize_bundle,
    _identity_doc_with_seed_pad_px,
    _init_bundle,
    _init_passing_bundle,
    _provenance_for,
    _set_opaque_rgb,
    _swing_provider_strip,
    _walk_provider_on_edit_canvas,
)


SWING_24X24_ALPHA_BBOX = (
    (5, 18, 1, 23),
    (4, 19, 8, 23),
    (4, 19, 9, 23),
    (4, 18, 10, 23),
)
SWING_OPAQUE_COUNTS = (177, 151, 154, 128)
SWING_PRE_SLICE_RGB_MULTISSETS = (
    {
        (17, 16, 24): 18,
        (25, 58, 50): 16,
        (29, 23, 32): 21,
        (29, 59, 80): 7,
        (40, 91, 67): 5,
        (43, 34, 48): 8,
        (59, 34, 27): 25,
        (59, 47, 58): 27,
        (66, 128, 90): 2,
        (74, 59, 72): 5,
        (78, 141, 160): 1,
        (98, 55, 34): 14,
        (108, 61, 49): 3,
        (120, 58, 24): 10,
        (120, 166, 99): 1,
        (128, 106, 115): 1,
        (147, 86, 49): 7,
        (165, 140, 145): 1,
        (200, 123, 67): 5,
    },
    {
        (17, 16, 24): 20,
        (25, 58, 50): 20,
        (29, 23, 32): 11,
        (29, 59, 80): 3,
        (40, 91, 67): 6,
        (43, 34, 48): 7,
        (47, 96, 117): 2,
        (59, 34, 27): 18,
        (59, 47, 58): 20,
        (66, 128, 90): 2,
        (74, 59, 72): 2,
        (78, 141, 160): 3,
        (98, 55, 34): 17,
        (108, 61, 49): 2,
        (120, 58, 24): 5,
        (120, 166, 99): 1,
        (128, 106, 115): 2,
        (147, 86, 49): 6,
        (164, 95, 70): 1,
        (190, 98, 34): 1,
        (200, 123, 67): 2,
    },
    {
        (17, 16, 24): 25,
        (25, 58, 50): 20,
        (29, 23, 32): 3,
        (29, 59, 80): 1,
        (40, 91, 67): 4,
        (43, 34, 48): 5,
        (47, 96, 117): 1,
        (59, 34, 27): 28,
        (59, 47, 58): 23,
        (66, 128, 90): 3,
        (74, 59, 72): 1,
        (78, 141, 160): 3,
        (98, 55, 34): 12,
        (108, 61, 49): 2,
        (120, 58, 24): 7,
        (120, 166, 99): 4,
        (147, 86, 49): 8,
        (164, 95, 70): 1,
        (165, 140, 145): 2,
        (200, 123, 67): 1,
    },
    {
        (17, 16, 24): 16,
        (25, 58, 50): 14,
        (29, 23, 32): 9,
        (29, 59, 80): 2,
        (40, 91, 67): 7,
        (43, 34, 48): 1,
        (59, 34, 27): 25,
        (59, 47, 58): 22,
        (66, 128, 90): 1,
        (98, 55, 34): 13,
        (108, 61, 49): 2,
        (120, 58, 24): 5,
        (120, 166, 99): 2,
        (147, 86, 49): 5,
        (164, 95, 70): 1,
        (200, 123, 67): 3,
    },
)


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
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
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
        _check_bundle(bundle)
    assert exc.value.reason_code == "edit_source_not_generation_source"


def test_dwarf_walk_check_accepts_correct_padded_edit_source_when_seed_pad_px_set(
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

    bundle = tmp_path / "bundle"
    walk_provider = _walk_provider_on_edit_canvas(tmp_path)
    provenance_path = _provenance_for(
        walk_provider,
        tmp_path,
        "walk",
        polish_profile="dwarf-miner",
    )
    record = json.loads(provenance_path.read_text())
    record["edit_source_sha256"] = sha256_file(padded_seed)
    provenance_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
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
    _check_bundle_slicing_from(bundle, WALK_STRIP)


def test_dwarf_walk_check_exposes_identity_lock_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
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


def test_production_swing_polished_frames_preserve_pre_slice_subject_pixels() -> None:
    for index in range(FRAME_COUNT):
        cells = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
        assert sum(1 for row in cells for cell in row if cell is not None) == SWING_OPAQUE_COUNTS[index]
        assert dict(_swing_opaque_rgb_multiset(cells)) == SWING_PRE_SLICE_RGB_MULTISSETS[index]


def test_production_swing_audit_records_interim_re_canvas_status() -> None:
    audit = json.loads((SWING_BUNDLE / "reports" / "audit.json").read_text(encoding="utf-8"))
    summary = audit["machine_check"]["edit_summary"]
    assert "interim" in summary.lower()
    assert "re-canvas" in summary.lower()
    assert "re-author" in summary.lower()
    assert audit["uncertain_count"] == 0
    assert audit["overall"] == "PASS"
    assert all(answer["verdict"] != "UNCERTAIN" for answer in audit["answers"])


def test_dwarf_swing_check_exposes_identity_lock_report(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(
        _swing_provider_strip(tmp_path),
        "swing",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
    )
    swing_strip = _swing_provider_strip(tmp_path)
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
    _init_bundle(
        _swing_provider_strip(tmp_path),
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

    swing_strip = _swing_provider_strip(tmp_path)
    result = _check_bundle_slicing_from(bundle, swing_strip)
    assert result.outcome == "FAIL"
    assert result.provider_post_edit is not None
    assert result.provider_post_edit["magenta_wipe"]["outcome"] == "PASS"


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
    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(WALK_STRIP, layout),
    ):
        result = _check_bundle(bundle)
        assert result.identity_lock is not None
        assert result.identity_lock.outcome == "FAIL"
        assert result.structural.pass_
        assert result.coherence.get("outcome") == "PASS"
        assert result.outcome == "FAIL"
        report_path = _finalize_bundle(bundle)
    report = json.loads(report_path.read_text())
    assert report["identity_lock"]["outcome"] == "FAIL"
    assert report["outcome"] == "FAIL"
    assert "release_frames" not in report
    assert not (bundle / "release").exists()


def test_idle_bundle_has_no_identity_lock(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    assert result.identity_lock is None
