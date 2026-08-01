"""Cell-grid ↔ raster PNG conversion for the asset pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

from pipeline.recovery import MAGENTA
from pipeline.strip import Cell, canonicalize_frame, StripLayout

__all__ = [
    "RasterError",
    "cells_from_rgba",
    "read_cells",
    "read_rgba",
    "write_cells",
    "write_silhouette_gif",
    "write_silhouette_strip",
]


class RasterError(ValueError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def cells_from_rgba(image: Image.Image) -> list[list[Cell]]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    assert pixels is not None
    cells: list[list[Cell]] = []
    for y in range(height):
        row: list[Cell] = []
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                row.append(None)
            else:
                row.append((int(r), int(g), int(b)))
        cells.append(row)
    return cells


def read_cells(
    path: Path,
    *,
    size: tuple[int, int] | None = None,
    require_binary_alpha: bool = True,
    label: str = "image",
) -> list[list[Cell]]:
    if not path.is_file():
        raise RasterError(
            f"missing logical {label}: {path.name}",
            reason_code=f"missing_{label}",
        )
    try:
        with Image.open(path) as image:
            if image.mode != "RGBA":
                raise RasterError(
                    f"{label} must be RGBA: {path.name}",
                    reason_code="wrong_mode",
                )
            if size is not None and image.size != size:
                w, h = size
                raise RasterError(
                    f"{label} must be {w}x{h}: {path.name}",
                    reason_code="wrong_size",
                )
            rgba = image.convert("RGBA")
            if require_binary_alpha:
                alpha = rgba.getchannel("A")
                for value in alpha.get_flattened_data():
                    if value not in (0, 255):
                        raise RasterError(
                            f"non-binary alpha in {path.name}",
                            reason_code="non_binary_alpha",
                        )
            return cells_from_rgba(rgba)
    except UnidentifiedImageError as exc:
        raise RasterError(
            f"unreadable {label}: {path.name}",
            reason_code=f"unreadable_{label}",
        ) from exc


def write_cells(path: Path, cells: list[list[Cell]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_h = len(cells)
    frame_w = len(cells[0]) if cells else 0
    logical = canonicalize_frame(cells, frame_w=frame_w, frame_h=frame_h)
    height = len(logical)
    width = len(logical[0]) if logical else 0
    image = Image.new("RGBA", (width, height), (*MAGENTA, 0))
    pixels = image.load()
    assert pixels is not None
    for y in range(height):
        for x in range(width):
            rgb = logical[y][x]
            if rgb is not None:
                pixels[x, y] = (*rgb, 255)
    image.save(path)


def read_rgba(path: Path) -> list[list[tuple[int, int, int, int]]]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        pixels = rgba.load()
        assert pixels is not None
        return [[pixels[x, y] for x in range(width)] for y in range(height)]


def _silhouette_rgba_from_cells(cells: list[list[Cell]]) -> Image.Image:
    height = len(cells)
    width = len(cells[0]) if cells else 0
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    for y, row in enumerate(cells):
        for x, cell in enumerate(row):
            if cell is not None:
                pixels[x, y] = (0, 0, 0, 255)
    return image


def _compose_silhouette_strip(
    frames: Sequence[list[list[Cell]]],
    layout: StripLayout,
) -> Image.Image:
    strip = Image.new(
        "RGBA",
        (layout.strip_width(), layout.frame_h),
        (0, 0, 0, 0),
    )
    x = 0
    for frame in frames:
        strip.paste(_silhouette_rgba_from_cells(frame), (x, 0))
        x += layout.frame_w + layout.gutter
    return strip


def _silhouette_gif_palette_frame(rgba: Image.Image) -> Image.Image:
    width, height = rgba.size
    indexed = Image.new("P", (width, height))
    indexed.putpalette([0, 0, 0] * 256)
    rgba_pixels = rgba.load()
    indexed_pixels = indexed.load()
    assert rgba_pixels is not None
    assert indexed_pixels is not None
    for y in range(height):
        for x in range(width):
            indexed_pixels[x, y] = 0 if rgba_pixels[x, y][3] == 0 else 1
    indexed.info["transparency"] = 0
    return indexed


def write_silhouette_strip(
    path: Path,
    frames: Sequence[list[list[Cell]]],
    layout: StripLayout,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _compose_silhouette_strip(frames, layout).save(path, format="PNG", optimize=False)


def write_silhouette_gif(
    path: Path,
    frames: Sequence[list[list[Cell]]],
    *,
    durations_ms: Sequence[int],
    loop: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba_frames = [_silhouette_rgba_from_cells(frame) for frame in frames]
    gif_frames = [_silhouette_gif_palette_frame(frame) for frame in rgba_frames]
    gif_frames[0].save(
        path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=list(durations_ms),
        loop=0 if loop else 1,
        disposal=2,
        optimize=False,
    )
