"""Interim shared fixtures for the split final-polish test modules (#263).

This module exists only so the lifecycle split could land before the Polish
Bundle fixture migration. It is a way station, not a seam: `tests/support/
polish_bundle.py` is the permanent fixture seam, and #252 deletes this module
once every test builds through it. Do not add to it and do not improve it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.cell_raster import read_cells
from pipeline.final_polish import (
    PROVENANCE_SCHEMA,
    check_bundle as polish_check_bundle,
    finalize_bundle as polish_finalize_bundle,
)
from pipeline.final_polish_cli import main as final_polish_cli_main
from pipeline.gate_evidence import (
    sha256_bytes,
    sha256_file,
)
from pipeline.identity_lock import (
    build_identity_seed,
    magenta_pad_generation_source_png,
)
from pipeline.strip import (
    DEFAULT_LAYOUT,
    StripLayout,
    layout_for_motion_class,
)
from tests.final_polish_harness import (
    bundle_store_env_context,
)


ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
_IDLE_STORE_ATTEMPT_KWARGS = {
    "motion_class": "idle",
    "generation_mode": "text-to-image",
    "acquiring_agent": "pytest",
    "prompt_text": "underline test provenance prompt",
}
WALK_STRIP = INBOX / "05-miner-walk.png"
SWING_STRIP = INBOX / "06-miner-swing.png"
LANTERN_STRIP = INBOX / "14-lantern-flicker.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
CANONICAL_IDENTITY_SHA = "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
SWING_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "swing"
SWING_POLISHED = SWING_BUNDLE / "polished"
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


def _item_geometry(*, motion_class: str) -> dict[str, int]:
    layout = layout_for_motion_class(motion_class, margin_cells=0)
    return {
        "frame_w": layout.frame_w,
        "frame_h": layout.frame_h,
        "frame_count": layout.frame_count,
        "gutter": layout.gutter,
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
        "item_geometry": _item_geometry(motion_class=motion_class),
    }
    record.update(overrides)
    provenance_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _padded_edit_source_seed(tmp_path: Path, motion_class: str) -> Path:
    out = tmp_path / (
        "swing-edit-source.png" if motion_class == "swing" else "padded-edit-source.png"
    )
    kwargs: dict[str, str] = {}
    if motion_class == "swing":
        kwargs["motion_class"] = "swing"
    build_identity_seed(IDENTITY_JSON, out, **kwargs)
    return out


@dataclass
class _CliResult:
    """Captured `main()` exit code and streams for a `strip:polish` invocation."""

    returncode: int
    stdout: str
    stderr: str


def _run_cli(
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> _CliResult:
    if env is None:
        returncode = final_polish_cli_main(args)
    else:
        with patch.dict("os.environ", env):
            returncode = final_polish_cli_main(args)
    captured = capsys.readouterr()
    return _CliResult(returncode=returncode, stdout=captured.out, stderr=captured.err)


def _first_opaque_xy(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(DEFAULT_LAYOUT.frame_h):
            for x in range(DEFAULT_LAYOUT.frame_w):
                if pixels[x, y][3] == 255:
                    return x, y
    raise AssertionError(f"no opaque cell in {path}")


def _item_geometry_for(motion_class: str) -> dict[str, int]:
    try:
        layout = layout_for_motion_class(motion_class, margin_cells=0)
    except ValueError:
        layout = _corpus_layout()
    return {
        "frame_w": layout.frame_w,
        "frame_h": layout.frame_h,
        "frame_count": layout.frame_count,
        "gutter": layout.gutter,
    }


def _write_cli_animation_provenance(
    provider_path: Path,
    provenance_path: Path,
    *,
    motion_class: str,
    generation_mode: str = "text-to-image",
    attempt_id: str = "cli-test--001",
    predecessor_attempt_id: str | None = None,
    reference_image_sha256: list[str] | None = None,
    edit_source_sha256: str | None = None,
    **overrides: object,
) -> None:
    if reference_image_sha256 is None:
        reference_image_sha256 = []
    prompt_text = "underline cli test provenance prompt"
    record: dict[str, object] = {
        "schema": "animation-strip-provenance/0",
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
        "item_geometry": _item_geometry_for(motion_class),
    }
    record.update(overrides)
    provenance_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _identity_seed_pad_px() -> int:
    doc = json.loads(IDENTITY_JSON.read_text(encoding="utf-8"))
    return int(doc["seed_pad_px"])


def _padded_inbox_provider(
    inbox_strip: Path,
    tmp_path: Path,
    *,
    motion_class: str | None = None,
) -> Path:
    seed_pad_px = _identity_seed_pad_px()
    kwargs: dict[str, str] = {}
    if motion_class is not None:
        kwargs["motion_class"] = motion_class
    out = tmp_path / f"{inbox_strip.stem}-padded-provider.png"
    out.write_bytes(
        magenta_pad_generation_source_png(
            inbox_strip.read_bytes(),
            seed_pad_px,
            **kwargs,
        )
    )
    return out


def _walk_provider_on_edit_canvas(tmp_path: Path) -> Path:
    seed = _padded_edit_source_seed(tmp_path, "walk")
    out = tmp_path / "walk-on-edit-canvas.png"
    pad = _identity_seed_pad_px()
    with Image.open(seed) as canvas:
        base = canvas.copy()
        with Image.open(WALK_STRIP) as walk:
            base.paste(walk.convert("RGBA"), (pad, pad))
        base.save(out)
    return out


def _swing_padded_inbox_provider(tmp_path: Path) -> Path:
    return _padded_inbox_provider(SWING_STRIP, tmp_path, motion_class="swing")


def _swing_provider_on_edit_canvas(tmp_path: Path) -> Path:
    """Rasterize polished swing Frames on the swing image-edit canvas size."""
    seed = _padded_edit_source_seed(tmp_path, "swing")
    inner = _swing_provider_strip(tmp_path)
    out = tmp_path / "swing-on-edit-canvas.png"
    pad = _identity_seed_pad_px()
    with Image.open(seed) as seed_image:
        canvas = seed_image.copy()
        with Image.open(inner) as inner_image:
            canvas.paste(inner_image.convert("RGBA"), (pad, pad))
        canvas.save(out)
    return out


def _effective_dwarf_miner_provider(
    provider_path: Path,
    tmp_path: Path,
    motion_class: str,
) -> Path:
    if motion_class == "walk" and provider_path == WALK_STRIP:
        return _walk_provider_on_edit_canvas(tmp_path)
    if motion_class == "swing" and provider_path == SWING_STRIP:
        return _swing_padded_inbox_provider(tmp_path)
    if motion_class == "swing" and provider_path.parent == tmp_path:
        stem = provider_path.stem
        if stem in {"swing-24-provider", "swing-on-edit-canvas"}:
            return _swing_provider_on_edit_canvas(tmp_path)
    return provider_path


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
        padded_seed = _padded_edit_source_seed(tmp_path, motion_class)
        kwargs.update(
            {
                "generation_mode": "image-edit",
                "reference_image_sha256": [CANONICAL_IDENTITY_SHA],
                "edit_source_sha256": sha256_file(padded_seed),
            }
        )
    _write_animation_provenance(provider_path, provenance_path, **kwargs)
    return provenance_path


def _check_bundle(bundle: Path) -> FinalPolishCheckResult:
    with bundle_store_env_context(bundle):
        return polish_check_bundle(bundle)


def _finalize_bundle(bundle: Path) -> Path:
    with bundle_store_env_context(bundle):
        return polish_finalize_bundle(bundle)


def _load_frame_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGBA")


def _set_opaque_rgb(path: Path, x: int, y: int, rgb: tuple[int, int, int]) -> None:
    image = _load_frame_rgba(path)
    pixels = image.load()
    assert pixels is not None
    pixels[x, y] = (*rgb, 255)
    image.save(path)


def _bundle_tree(root: Path) -> set[str]:
    if not root.exists():
        return set()
    immutable_layers = frozenset({"provider", "draft", "polished", "release"})
    paths: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == "manifest.json" or rel.parts[0] in immutable_layers:
            paths.add(str(rel))
    return paths


def _swing_provider_frame_cells(cells: list[list[object]]) -> list[list[object]]:
    """Left-shift polished Frames to simulate native 24-wide provider art."""
    shifted: list[list[object]] = [[None for _ in range(24)] for _ in range(24)]
    for y in range(24):
        for x in range(20):
            shifted[y][x] = cells[y][x + 4]
    return shifted


def _write_swing_provider_strip(path: Path) -> Path:
    """Rasterize production swing polished Frames into a 24-wide provider strip."""
    layout = layout_for_motion_class("swing", margin_cells=0)
    pitch = layout.pitch_px
    # Abut frames at class width so pitch-slice yields 24-cell blocks (gutter=2 is metadata).
    strip_w = layout.frame_count * layout.frame_w
    strip_h = layout.frame_h
    border_px = 2
    magenta = (255, 0, 255, 255)
    content_w = strip_w * pitch
    content_h = strip_h * pitch
    strip = Image.new(
        "RGBA",
        (content_w + border_px * 2, content_h + border_px * 2),
        magenta,
    )
    for index in range(FRAME_COUNT):
        polished = read_cells(SWING_POLISHED / f"frame-{index}.png", size=(24, 24))
        cells = _swing_provider_frame_cells(polished)
        origin_gx = index * layout.frame_w
        for gy in range(layout.frame_h):
            for gx in range(layout.frame_w):
                rgb = cells[gy][gx]
                if rgb is None:
                    continue
                block = Image.new("RGBA", (pitch, pitch), (*rgb, 255))
                strip.paste(
                    block,
                    (border_px + (origin_gx + gx) * pitch, border_px + gy * pitch),
                )
    path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(path)
    return path


def _swing_provider_strip(tmp_path: Path) -> Path:
    return _write_swing_provider_strip(tmp_path / "swing-24-provider.png")


def _identity_doc_with_seed_pad_px(seed_pad_px: int = 64) -> dict[str, object]:
    doc = json.loads(IDENTITY_JSON.read_text(encoding="utf-8"))
    doc["seed_pad_px"] = seed_pad_px
    return doc
