"""Unit tests for pitch slicing and bounded silhouette registration."""

from __future__ import annotations

import strip as S

Cell = tuple[int, int, int] | None


def _grid(w: int, h: int, fill: Cell = None) -> list[list[Cell]]:
    return [[fill for _ in range(w)] for _ in range(h)]


def _mark(grid: list[list[Cell]], x: int, y: int, rgb: tuple[int, int, int]) -> None:
    grid[y][x] = rgb


def test_slice_frames_pitch_64_into_four_16_wide() -> None:
    cells = _grid(64, 24)
    for i in range(4):
        _mark(cells, i * 16 + 8, 10, (100, 100, 100))

    frames, meta = S.slice_frames_pitch(cells, frame_count=4)

    assert frames is not None
    assert len(frames) == 4
    assert all(len(f[0]) == 16 for f in frames)
    assert all(len(f) == 24 for f in frames)
    assert meta["mode"] == "pitch"
    assert meta["pitch"] == 16
    assert meta["frame_starts"] == [0, 16, 32, 48]
    assert meta["grid"] == [64, 24]


def test_slice_frames_pitch_non_divisible_returns_none() -> None:
    cells = _grid(63, 24)

    frames, meta = S.slice_frames_pitch(cells, frame_count=4)

    assert frames is None
    assert meta["reason"] == "grid width 63 not divisible by 4"


def test_silhouette_diff_span_zero_matches_legacy() -> None:
    a = _grid(4, 5)
    b = _grid(4, 5)
    rgb = (80, 80, 80)
    foot = 4
    for x in range(4):
        _mark(a, x, foot, rgb)
        _mark(b, x, foot, rgb)
    _mark(a, 1, 2, rgb)

    changed, union = S.silhouette_diff(a, b, span=0)
    assert (changed, union) == (1, 1)


def test_silhouette_diff_span_one_absorbs_one_column_shift() -> None:
    a = _grid(6, 5)
    b = _grid(6, 5)
    rgb = (80, 80, 80)
    foot = 4
    for x in range(6):
        _mark(a, x, foot, rgb)
        _mark(b, x, foot, rgb)
    for x in range(4):
        _mark(a, x, 1, rgb)
    for x in range(1, 5):
        _mark(b, x, 1, rgb)

    changed, union = S.silhouette_diff(a, b, span=0)
    assert union > 0
    assert changed / union > 0

    changed1, union1 = S.silhouette_diff(a, b, span=1)
    assert union1 > 0
    assert changed1 == 0
