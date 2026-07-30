"""PROTOTYPE runner — author swing Cells, score Identity Lock, emit overlays."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from pipeline.cell_raster import cells_from_rgba, write_cells
from pipeline.identity_lock import evaluate_identity_lock, identity_lock_report_payload
from pipeline.strip import Cell

from author import LOCKS, author_swing_frames, frame_to_ascii, in_lock

IDLE = REPO / "assets/first-room/dwarf/idle/polished/frame-0.png"
REF_DIR = REPO / "assets/first-room/dwarf/swing/polished"
OUT = Path(__file__).resolve().parent / "out"
SCALE = 24


def load_cells(path: Path) -> list[list[Cell]]:
    return cells_from_rgba(Image.open(path).convert("RGBA"))


def enlarge(
    frame: list[list[Cell]],
    *,
    draw_grid: bool,
    draw_locks: bool,
    label: str,
) -> Image.Image:
    h = len(frame)
    w = len(frame[0])
    img = Image.new("RGBA", (w * SCALE, h * SCALE), (30, 28, 34, 255))
    px = img.load()
    assert px is not None
    for y, row in enumerate(frame):
        for x, cell in enumerate(row):
            color = (40, 38, 48, 255) if cell is None else (*cell, 255)
            for dy in range(SCALE):
                for dx in range(SCALE):
                    px[x * SCALE + dx, y * SCALE + dy] = color
    draw = ImageDraw.Draw(img)
    if draw_grid:
        for x in range(w + 1):
            draw.line(
                (x * SCALE, 0, x * SCALE, h * SCALE),
                fill=(255, 0, 255, 90),
                width=1,
            )
        for y in range(h + 1):
            draw.line(
                (0, y * SCALE, w * SCALE, y * SCALE),
                fill=(255, 0, 255, 90),
                width=1,
            )
    if draw_locks:
        colors = {
            "helmet_face": (0, 220, 255, 255),
            "belt_core": (255, 220, 0, 255),
            "boots": (80, 255, 120, 255),
        }
        for name, x0, x1, y0, y1 in LOCKS:
            draw.rectangle(
                (
                    x0 * SCALE,
                    y0 * SCALE,
                    (x1 + 1) * SCALE - 1,
                    (y1 + 1) * SCALE - 1,
                ),
                outline=colors[name],
                width=2,
            )
    draw.text((4, 4), label, fill=(255, 255, 255, 255))
    return img


def composite_row(images: list[Image.Image], pad: int = 8) -> Image.Image:
    h = max(im.height for im in images)
    w = sum(im.width for im in images) + pad * (len(images) - 1)
    out = Image.new("RGBA", (w, h), (18, 16, 22, 255))
    x = 0
    for im in images:
        out.paste(im, (x, 0))
        x += im.width + pad
    return out


def occupancy(frame: list[list[Cell]]) -> float:
    total = sum(1 for row in frame for cell in row if cell is not None)
    return total / (16 * 24)


def lock_paint_violations(
    idle: list[list[Cell]], frame: list[list[Cell]]
) -> list[dict[str, int]]:
    bad: list[dict[str, int]] = []
    for y in range(24):
        for x in range(16):
            if not in_lock(x, y):
                continue
            if frame[y][x] != idle[y][x]:
                bad.append({"x": x, "y": y})
    return bad


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    idle = load_cells(IDLE)
    authored = author_swing_frames(idle)

    native_dir = OUT / "frames"
    native_dir.mkdir(exist_ok=True)
    overlay_imgs = []
    ref_imgs = []
    ascii_blocks = []
    violations = []

    for i, frame in enumerate(authored):
        write_cells(native_dir / f"frame-{i}.png", frame)
        ascii_blocks.append(f"--- authored frame {i} ---\n{frame_to_ascii(frame)}")
        v = lock_paint_violations(idle, frame)
        violations.append({"frame": i, "count": len(v), "cells": v[:20]})
        overlay_imgs.append(
            enlarge(frame, draw_grid=True, draw_locks=True, label=f"authored f{i}")
        )
        ref_imgs.append(
            enlarge(
                load_cells(REF_DIR / f"frame-{i}.png"),
                draw_grid=True,
                draw_locks=True,
                label=f"ref swing f{i}",
            )
        )

    idle_overlay = enlarge(idle, draw_grid=True, draw_locks=True, label="idle f0")
    idle_overlay.save(OUT / "idle-grid-locks.png")
    composite_row(overlay_imgs).save(OUT / "authored-strip-grid.png")
    composite_row(ref_imgs).save(OUT / "reference-swing-strip-grid.png")
    composite_row([idle_overlay, *overlay_imgs]).save(
        OUT / "idle-plus-authored-grid.png"
    )

    gif_frames = [
        enlarge(f, draw_grid=False, draw_locks=False, label=f"f{i}").convert("P")
        for i, f in enumerate(authored)
    ]
    gif_frames[0].save(
        OUT / "authored-swing.gif",
        save_all=True,
        append_images=gif_frames[1:],
        duration=180,
        loop=0,
    )

    lock = evaluate_identity_lock(authored, "swing")
    lock_payload = identity_lock_report_payload(lock)

    scoreboard = {
        "prototype": "swing-cell-author",
        "question": (
            "Can an agent hand-author a swing at 16x24 from idle polished "
            "frame-0 while preserving Identity Lock, without image gen?"
        ),
        "idle_source": str(IDLE.relative_to(REPO)),
        "identity_lock_outcome": lock.outcome,
        "identity_lock": lock_payload,
        "lock_region_mutations": violations,
        "occupancy": [round(occupancy(f), 4) for f in authored],
        "ascii": ascii_blocks,
        "artifacts": [
            "out/frames/frame-0.png",
            "out/frames/frame-1.png",
            "out/frames/frame-2.png",
            "out/frames/frame-3.png",
            "out/idle-grid-locks.png",
            "out/authored-strip-grid.png",
            "out/reference-swing-strip-grid.png",
            "out/idle-plus-authored-grid.png",
            "out/authored-swing.gif",
            "out/scoreboard.json",
        ],
    }
    (OUT / "scoreboard.json").write_text(
        json.dumps(scoreboard, indent=2) + "\n", encoding="utf-8"
    )

    print("prototype:swing-cell-author")
    print(f"identity_lock: {lock.outcome}")
    if lock.first_failure is not None:
        print(f"first_failure: {json.dumps(lock.first_failure)}")
    print(f"lock_region_mutations: {[v['count'] for v in violations]}")
    print(f"occupancy: {scoreboard['occupancy']}")
    print(f"wrote {OUT}")
    for block in ascii_blocks:
        print(block)
    return 0 if lock.outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
