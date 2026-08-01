#!/usr/bin/env python3
"""Render swing canvas variants and write the measured scoreboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.cell_raster import write_cells

from canvas import (
    BASELINE_MOTIONS,
    VARIANTS,
    load_motion_frames,
    load_palette_entries,
    measure_motion_baseline,
    measure_variant,
    render_variant_frames,
    silhouette_render,
)

ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = Path(__file__).resolve().parent
OUT_DIR = PROTOTYPE_DIR / "out"
ASSETS_ROOT = ROOT / "assets"
PALETTE_PATH = ASSETS_ROOT / "palettes" / "first-room.json"


def build_scoreboard() -> tuple[dict[str, object], dict[str, list]]:
    palette_entries = load_palette_entries(PALETTE_PATH)
    baseline: dict[str, object] = {}
    for motion in BASELINE_MOTIONS:
        frames = load_motion_frames(ASSETS_ROOT, motion)
        baseline[motion] = measure_motion_baseline(frames)

    swing_frames = load_motion_frames(ASSETS_ROOT, "swing")
    variants: dict[str, object] = {}
    rendered_by_variant: dict[str, list] = {}
    overlay_body_identity: list[bool] = []
    for variant in VARIANTS:
        rendered, separations, body_identity = render_variant_frames(
            swing_frames,
            variant,
            palette_entries,
        )
        rendered_by_variant[variant] = rendered
        variants[variant] = measure_variant(
            rendered,
            separations=separations if variant == "overlay" else None,
        )
        if variant == "overlay":
            overlay_body_identity = body_identity

    scoreboard = {
        "schema": "swing-canvas-scoreboard/0",
        "baseline": baseline,
        "variants": variants,
        "overlay_body_byte_identical": overlay_body_identity,
    }
    return scoreboard, rendered_by_variant


def write_artifacts(
    scoreboard: dict[str, object],
    rendered_by_variant: dict[str, list],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    scoreboard_path = OUT_DIR / "scoreboard.json"
    scoreboard_path.write_text(
        json.dumps(scoreboard, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for variant, rendered in rendered_by_variant.items():
        variant_dir = OUT_DIR / "variants" / variant
        variant_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(rendered):
            write_cells(variant_dir / f"frame-{index}.png", frame)
            silhouette_render(frame).save(variant_dir / f"frame-{index}-silhouette.png")


def main() -> int:
    scoreboard, rendered_by_variant = build_scoreboard()
    write_artifacts(scoreboard, rendered_by_variant)
    print(f"wrote {OUT_DIR / 'scoreboard.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
