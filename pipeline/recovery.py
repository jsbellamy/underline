"""Vendored grid-recovery primitives from Nightglass acquire.

Source: nightglass/pipeline/acquire.py
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-07-26

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit this copy in place.
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib

import numpy as np
from PIL import Image

__all__ = [
    "MAGENTA",
    "MIN_GRID_SCORE",
    "key",
    "raw_gates",
    "raw_clipping",
    "detect_pitch",
    "sample_cells",
]

ALPHA_CUT = 128
MAGENTA = (255, 0, 255)
KEY_TOLERANCE = 40
MIN_GRID_SCORE = 0.04


def _rgba_array(src: Image.Image) -> np.ndarray:
    if src.mode != "RGBA":
        src = src.convert("RGBA")
    return np.asarray(src)


def _magenta_mask(rgba: np.ndarray) -> np.ndarray:
    return (
        (np.abs(rgba[:, :, 0].astype(np.int16) - MAGENTA[0]) <= KEY_TOLERANCE)
        & (np.abs(rgba[:, :, 1].astype(np.int16) - MAGENTA[1]) <= KEY_TOLERANCE)
        & (np.abs(rgba[:, :, 2].astype(np.int16) - MAGENTA[2]) <= KEY_TOLERANCE)
    )


def _foreground_mask(
    src: Image.Image,
    *,
    ignore_stamp: bool,
) -> tuple[np.ndarray, bool, tuple[int, int, int, int]]:
    h = src.size[1]
    rgba = _rgba_array(src)
    keyed = (rgba[:, :, 3] < ALPHA_CUT) | _magenta_mask(rgba)
    fg = ~keyed
    stamp_removed = False
    if ignore_stamp:
        stamp_removed = bool(fg[h - 1, 0])
        fg[h - 1, 0] = False
    ys, xs = np.nonzero(fg)
    if xs.size == 0:
        raise ValueError(f"{src}: magenta key removed the entire image")
    return fg, stamp_removed, (
        int(xs.min()),
        int(ys.min()),
        int(xs.max()),
        int(ys.max()),
    )


def key(raw_path: pathlib.Path) -> tuple[Image.Image, np.ndarray, tuple[int, int, int, int]]:
    src = Image.open(raw_path).convert("RGBA")
    fg, _, bbox = _foreground_mask(src, ignore_stamp=False)
    return src, fg, bbox


def _candidate_gates(raw_path: pathlib.Path) -> list[str]:
    errs: list[str] = []
    try:
        with Image.open(raw_path) as opened:
            if opened.format != "PNG":
                errs.append(f"{raw_path.name}: raw must be a PNG, got {opened.format!r}")
            src = opened.convert("RGBA")
    except (OSError, ValueError) as error:
        return [f"{raw_path.name}: unreadable candidate: {error}"]
    w, h = src.size
    rgba = _rgba_array(src)
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]
    border_mask = (cols < 2) | (cols >= w - 2) | (rows < 2) | (rows >= h - 2)
    border_mask[h - 1, 0] = False
    border = int(border_mask.sum())
    keyed = int(
        ((rgba[:, :, 3] >= ALPHA_CUT) & _magenta_mask(rgba) & border_mask).sum()
    )
    if not border or keyed / border < 0.95:
        errs.append(
            f"{raw_path.name}: border is not a flat {MAGENTA!r} chroma key "
            f"({keyed}/{border} pixels within tolerance {KEY_TOLERANCE})"
        )
    return errs


def raw_gates(raw_path: pathlib.Path) -> list[str]:
    errs = _candidate_gates(raw_path)

    sidecar = raw_path.with_suffix(".source.json")
    if not sidecar.exists():
        errs.append(f"{raw_path.name}: missing provenance sidecar {sidecar.name}")
    else:
        try:
            record = json.loads(sidecar.read_text())
        except (OSError, json.JSONDecodeError) as error:
            errs.append(f"{raw_path.name}: invalid provenance sidecar: {error}")
        else:
            actual = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            if record.get("raw_sha256") != actual:
                errs.append(
                    f"{raw_path.name}: raw bytes differ from archived provider output"
                )
    return errs


def _axis_extent(fg: np.ndarray, w: int, h: int, axis: str) -> tuple[int, int]:
    occupied = np.nonzero(fg.any(axis=0 if axis == "x" else 1))[0]
    return int(occupied.min()), int(occupied.max())


def _edge_profile(src: Image.Image, fg: np.ndarray, axis: str) -> list[float]:
    rgb = _rgba_array(src)[:, :, :3].astype(np.int16)
    length = src.size[0] if axis == "x" else src.size[1]
    if axis == "x":
        delta = np.abs(rgb[:, 1:, :] - rgb[:, :-1, :]).sum(axis=2, dtype=np.int32)
        paired = fg[:, 1:] & fg[:, :-1]
        energy = np.where(paired, delta, 0).sum(axis=0)
    else:
        delta = np.abs(rgb[1:, :, :] - rgb[:-1, :, :]).sum(axis=2, dtype=np.int32)
        paired = fg[1:, :] & fg[:-1, :]
        energy = np.where(paired, delta, 0).sum(axis=1)
    profile = [0.0] * length
    profile[1:] = energy.tolist()
    return profile


def detect_pitch(
    src: Image.Image,
    fg: np.ndarray,
    axis: str,
    minimum: float,
    maximum: float,
    pitch_step: float = 0.05,
    phase_step: float = 0.5,
) -> dict:
    w, h = src.size
    length = w if axis == "x" else h
    lo, hi = _axis_extent(fg, w, h, axis)
    profile = _edge_profile(src, fg, axis)
    total = sum(profile[lo : hi + 1])
    max_energy = max(profile[lo : hi + 1], default=0)
    epsilon = max_energy * 0.15
    best = {"pitch": minimum, "phase": 0.0, "score": -1.0}
    if total <= 0:
        return best
    p = minimum
    while p <= maximum + 1e-9:
        phase = 0.0
        while phase < p:
            kmin = math.ceil((lo - phase) / p)
            kmax = math.floor((hi - phase) / p)
            teeth = hits = 0
            covered_energy = 0.0
            covered: set[int] = set()
            for k in range(kmin, kmax + 1):
                pos = phase + k * p
                if pos <= lo + 0.5 or pos >= hi - 0.5:
                    continue
                teeth += 1
                energy = 0.0
                column = -1
                nearest = round(pos)
                for candidate in (nearest - 1, nearest, nearest + 1):
                    if 0 <= candidate < length and profile[candidate] > energy:
                        energy = profile[candidate]
                        column = candidate
                if energy > epsilon:
                    hits += 1
                if column >= 0 and column not in covered:
                    covered.add(column)
                    covered_energy += profile[column]
            if teeth:
                score = (covered_energy / total) * (hits / teeth)
                if score > best["score"]:
                    best = {"pitch": p, "phase": phase, "score": score}
            phase += phase_step
        p += pitch_step
    return best


def _cell_indices(lo: int, hi: int, pitch: float, phase: float) -> list[int]:
    kmin = math.ceil((lo - phase) / pitch - 0.5)
    kmax = math.floor((hi - phase) / pitch - 0.5)
    return list(range(kmin, kmax + 1))


def sample_cells(
    src: Image.Image,
    fg: np.ndarray,
    bbox: tuple[int, int, int, int],
    pitch_x: dict,
    pitch_y: dict,
) -> list[list[tuple[int, int, int] | None]]:
    w, h = src.size
    px = src.load()
    x0, y0, x1, y1 = bbox
    xs = _cell_indices(x0, x1, pitch_x["pitch"], pitch_x["phase"])
    ys = _cell_indices(y0, y1, pitch_y["pitch"], pitch_y["phase"])
    half_x, half_y = 0.3 * pitch_x["pitch"], 0.3 * pitch_y["pitch"]
    grid = []
    for ky in ys:
        cy = pitch_y["phase"] + (ky + 0.5) * pitch_y["pitch"]
        row = []
        for kx in xs:
            cx = pitch_x["phase"] + (kx + 0.5) * pitch_x["pitch"]
            colors = []
            total = 0
            for y in range(round(cy - half_y), round(cy + half_y) + 1):
                for x in range(round(cx - half_x), round(cx + half_x) + 1):
                    if not (0 <= x < w and 0 <= y < h):
                        continue
                    total += 1
                    if fg[y, x]:
                        colors.append(px[x, y][:3])
            if not total or len(colors) / total < 0.5:
                row.append(None)
            else:
                row.append(
                    tuple(
                        sorted(channel)[(len(channel) - 1) // 2]
                        for channel in zip(*colors)
                    )
                )
        grid.append(row)
    return grid


def _clipped_sides(src: Image.Image, bbox: tuple[int, int, int, int]) -> list[str]:
    w, h = src.size
    x0, y0, x1, y1 = bbox
    return [
        side
        for side, hit in (
            ("top", y0 == 0),
            ("bottom", y1 == h - 1),
            ("left", x0 == 0),
            ("right", x1 == w - 1),
        )
        if hit
    ]


def raw_clipping(raw_path: pathlib.Path) -> list[str]:
    try:
        src, _, (x0, y0, x1, y1) = key(raw_path)
    except ValueError as error:
        return [str(error)]
    touching = _clipped_sides(src, (x0, y0, x1, y1))
    if touching:
        w, h = src.size
        return [
            f"{raw_path.name}: subject clipped by generator at "
            f"{'/'.join(touching)} of the {w}x{h} raw canvas"
        ]
    return []
