"""Cell-grid ↔ raster PNG adapter (issue #137)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from pipeline.cell_raster import (
    RasterError,
    cells_from_rgba,
    read_cells,
    read_rgba,
    write_cells,
    write_silhouette_gif,
    write_silhouette_strip,
)
from pipeline.strip import DEFAULT_LAYOUT, StripLayout, export_frames


def test_cells_from_rgba_transparent_pixel_becomes_none() -> None:
    image = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    pixels[1, 0] = (10, 20, 30, 255)
    pixels[0, 1] = (40, 50, 60, 255)
    pixels[1, 1] = (70, 80, 90, 255)
    pixels[2, 1] = (100, 110, 120, 255)
    # (2, 0) stays fully transparent

    expected: list[list[tuple[int, int, int] | None]] = [
        [None, (10, 20, 30), None],
        [(40, 50, 60), (70, 80, 90), (100, 110, 120)],
    ]
    assert cells_from_rgba(image) == expected


@pytest.mark.parametrize("label", ["frame", "item"])
def test_read_cells_missing_file(label: str, tmp_path: Path) -> None:
    path = tmp_path / f"{label}.png"
    with pytest.raises(RasterError) as exc:
        read_cells(path, size=(2, 2), label=label)
    assert exc.value.reason_code == f"missing_{label}"


@pytest.mark.parametrize("label", ["frame", "item"])
def test_read_cells_wrong_mode(label: str, tmp_path: Path) -> None:
    path = tmp_path / f"{label}.png"
    Image.new("RGB", (2, 2), (0, 0, 0)).save(path)
    with pytest.raises(RasterError) as exc:
        read_cells(path, size=(2, 2), label=label)
    assert exc.value.reason_code == "wrong_mode"


@pytest.mark.parametrize("label", ["frame", "item"])
def test_read_cells_wrong_size(label: str, tmp_path: Path) -> None:
    path = tmp_path / f"{label}.png"
    Image.new("RGBA", (3, 2), (0, 0, 0, 0)).save(path)
    with pytest.raises(RasterError) as exc:
        read_cells(path, size=(2, 2), label=label)
    assert exc.value.reason_code == "wrong_size"


@pytest.mark.parametrize("label", ["frame", "item"])
def test_read_cells_non_binary_alpha(label: str, tmp_path: Path) -> None:
    path = tmp_path / f"{label}.png"
    image = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    pixels[0, 0] = (255, 0, 0, 128)
    image.save(path)
    with pytest.raises(RasterError) as exc:
        read_cells(path, size=(2, 2), label=label)
    assert exc.value.reason_code == "non_binary_alpha"


@pytest.mark.parametrize("label", ["frame", "item"])
def test_read_cells_unreadable_image(label: str, tmp_path: Path) -> None:
    path = tmp_path / f"{label}.png"
    path.write_bytes(b"not a png")
    with pytest.raises(RasterError) as exc:
        read_cells(path, size=(2, 2), label=label)
    assert exc.value.reason_code == f"unreadable_{label}"
    assert isinstance(exc.value.__cause__, UnidentifiedImageError)


def test_write_cells_round_trip(tmp_path: Path) -> None:
    cells: list[list[tuple[int, int, int] | None]] = [
        [(255, 0, 0), None, (0, 255, 0)],
        [None, (0, 0, 255), (128, 128, 128)],
    ]
    path = tmp_path / "frame.png"
    write_cells(path, cells)
    assert read_cells(path, size=(3, 2), label="frame") == cells


def test_write_cells_matches_export_frames_bytes(tmp_path: Path) -> None:
    cells: list[list[tuple[int, int, int] | None]] = [
        [(255, 0, 0), None, (0, 255, 0)],
        [None, (0, 0, 255), (128, 128, 128)],
    ]
    adapter_path = tmp_path / "adapter.png"
    write_cells(adapter_path, cells)

    staging = tmp_path / "staging"
    export_frames([cells], staging, "export", frame_w=3, frame_h=2)
    export_path = staging / "export-f0.png"

    assert adapter_path.read_bytes() == export_path.read_bytes()


def test_write_cells_leaves_no_staging_directory(tmp_path: Path) -> None:
    cells: list[list[tuple[int, int, int] | None]] = [[(1, 2, 3)]]
    path = tmp_path / "only.png"
    write_cells(path, cells)
    assert list(path.parent.iterdir()) == [path]


def test_read_rgba_preserves_semi_transparent_alpha(tmp_path: Path) -> None:
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    pixels = image.load()
    assert pixels is not None
    pixels[0, 0] = (10, 20, 30, 128)
    pixels[1, 0] = (40, 50, 60, 255)
    path = tmp_path / "rgba.png"
    image.save(path)

    rgba_cells = read_rgba(path)
    assert rgba_cells == [[(10, 20, 30, 128), (40, 50, 60, 255)]]


def test_cell_raster_exports_exactly_six_public_symbols() -> None:
    import pipeline.cell_raster as cell_raster

    expected = {
        "RasterError",
        "cells_from_rgba",
        "read_cells",
        "read_rgba",
        "write_cells",
        "write_silhouette_gif",
        "write_silhouette_strip",
    }
    assert set(cell_raster.__all__) == expected


def _distinct_rgba_states(path: Path) -> set[tuple[int, int, int, int]]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        width, height = rgba.size
        return {pixels[x, y] for y in range(height) for x in range(width)}


def test_write_silhouette_strip_composes_logical_row_with_gutter(tmp_path: Path) -> None:
    layout = StripLayout(frame_w=2, frame_h=2, frame_count=2, gutter=1)
    frames = [
        [[(255, 0, 0), None], [None, (0, 255, 0)]],
        [[None, (0, 0, 255)], [(128, 128, 128), None]],
    ]
    path = tmp_path / "silhouette-strip.png"
    write_silhouette_strip(path, frames, layout)

    assert path.is_file()
    with Image.open(path) as strip:
        assert strip.size == (5, 2)
    assert _distinct_rgba_states(path) == {(0, 0, 0, 0), (0, 0, 0, 255)}


def test_write_silhouette_gif_uses_authored_frame_durations(tmp_path: Path) -> None:
    layout = StripLayout(frame_w=2, frame_h=2, frame_count=2, gutter=1)
    frames = [
        [[(255, 0, 0), None], [None, (0, 255, 0)]],
        [[None, (0, 0, 255)], [(128, 128, 128), None]],
    ]
    durations_ms = [150, 80]
    path = tmp_path / "silhouette.gif"
    write_silhouette_gif(path, frames, durations_ms=durations_ms, loop=True)

    with Image.open(path) as gif:
        assert gif.size == (2, 2)
        assert gif.n_frames == 2
        frame_durations = []
        for index in range(gif.n_frames):
            gif.seek(index)
            frame_durations.append(gif.info["duration"])
    assert frame_durations == durations_ms
