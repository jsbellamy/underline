"""Unit tests for pitch slicing and bounded silhouette registration."""

from __future__ import annotations

from pipeline import strip as S

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


def _grounded_baseline_fixture() -> list[list[list[Cell]]]:
    """Three frames: frame 1's lowest opaque row sits one row higher than frame 0."""
    rgb = (80, 80, 80)
    frames: list[list[list[Cell]]] = []
    for fi in range(3):
        grid = _grid(4, 6)
        foot = 4 if fi != 1 else 5
        for x in range(4):
            _mark(grid, x, foot, rgb)
        _mark(grid, 1, 2, rgb)
        frames.append(grid)
    return frames


def test_grounded_anchor_trips_baseline_row_stable() -> None:
    frames = _grounded_baseline_fixture()
    result = S.coherence_split(frames, motion_class="idle")
    assert result["baseline_row_stable"] is False
    assert result["pass"] is False


def test_ungrounded_excludes_baseline_row_stable() -> None:
    frames = _grounded_baseline_fixture()
    result = S.coherence_split(frames, motion_class="airborne")
    assert result["baseline_row_stable"] is None
    assert "baseline_row_stable" not in [
        g for g in ("dimension_parity", "baseline_row_stable", "silhouette_budget",
                    "min_pair_cohort_pass", "loop_closure_pass", "palette_drift_pass")
        if result.get(g) is False
    ]


def test_canonicalize_frame_bottom_aligns_on_baseline() -> None:
    rgb = (80, 80, 80)
    tall = _grid(16, 42)
    for x in range(6, 10):
        _mark(tall, x, 28, rgb)
    _mark(tall, 8, 11, rgb)

    cropped = S.canonicalize_frame(tall, frame_w=16, frame_h=24)

    assert len(cropped) == 24
    assert len(cropped[0]) == 16
    assert S.baseline_row(cropped) == 23
    assert cropped[23][8] == rgb
    assert cropped[6][8] == rgb


def test_canonicalize_frame_noop_when_already_canonical() -> None:
    frame = _grid(16, 24)
    _mark(frame, 4, 23, (1, 2, 3))
    assert S.canonicalize_frame(frame, frame_w=16, frame_h=24) == frame
