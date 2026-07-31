"""PROTOTYPE — pure Cell-author logic for a swing pose from idle.

Throwaway. Lift only if a later acquisition path adopts Cell authoring.

Impact model (within Identity Lock permits):
  f0 coil back  → helmet/belt dx=-1
  f1 whip       → locks at 0; long tool leverage
  f2 commit     → helmet/belt dx=+1; reach
  f3 strike     → helmet/belt (+1,+1) squash; tip planted ahead of boots
"""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable

from pipeline.strip import Cell

# Master Palette samples (assets/palettes/first-room.json)
OUTLINE = (0x11, 0x10, 0x18)
HANDLE = (0x62, 0x37, 0x22)
HANDLE_MID = (0x93, 0x56, 0x31)
HEAD = (0x2F, 0x60, 0x75)
HEAD_LIT = (0x4E, 0x8D, 0xA0)
HEAD_DARK = (0x1D, 0x3B, 0x50)
GLOVE = (0x3B, 0x22, 0x1B)
GLOVE_LIT = (0x62, 0x37, 0x22)
TUNIC = (0x28, 0x5B, 0x43)
TUNIC_MID = (0x42, 0x80, 0x5A)
TUNIC_DARK = (0x19, 0x3A, 0x32)
BEARD = (0x93, 0x56, 0x31)
BEARD_DARK = (0x62, 0x37, 0x22)

HELMET = ("helmet_face", 5, 12, 1, 10)
BELT = ("belt_core", 4, 12, 15, 18)
BOOTS = ("boots", 3, 14, 21, 23)
LOCKS = (HELMET, BELT, BOOTS)

W, H = 16, 24

# Art-direction swing timing (ms) — used by the runner GIF.
SWING_FRAME_MS = (150, 80, 60, 180)


def in_active_lock(
    x: int,
    y: int,
    helmet_off: tuple[int, int],
    belt_off: tuple[int, int],
) -> bool:
    hx, hy = helmet_off
    if 5 + hx <= x <= 12 + hx and 1 + hy <= y <= 10 + hy:
        return True
    bx, by = belt_off
    if 4 + bx <= x <= 12 + bx and 15 + by <= y <= 18 + by:
        return True
    if 3 <= x <= 14 and 21 <= y <= 23:
        return True
    return False


# Back-compat for run.py lock overlays (canonical rects).
def in_lock(x: int, y: int) -> bool:
    return in_active_lock(x, y, (0, 0), (0, 0))


def clone_frame(frame: list[list[Cell]]) -> list[list[Cell]]:
    return deepcopy(frame)


def force_set(frame: list[list[Cell]], x: int, y: int, rgb: Cell) -> None:
    if 0 <= x < W and 0 <= y < H:
        frame[y][x] = rgb


def set_cell(
    frame: list[list[Cell]],
    x: int,
    y: int,
    rgb: Cell,
    *,
    helmet_off: tuple[int, int],
    belt_off: tuple[int, int],
) -> None:
    if not (0 <= x < W and 0 <= y < H):
        return
    if in_active_lock(x, y, helmet_off, belt_off):
        return
    frame[y][x] = rgb


def paint(
    frame: list[list[Cell]],
    cells: Iterable[tuple[int, int, Cell]],
    *,
    helmet_off: tuple[int, int],
    belt_off: tuple[int, int],
) -> None:
    for x, y, rgb in cells:
        set_cell(frame, x, y, rgb, helmet_off=helmet_off, belt_off=belt_off)


def shift_rect(
    frame: list[list[Cell]],
    idle: list[list[Cell]],
    x0: int,
    x1: int,
    y0: int,
    y1: int,
    dx: int,
    dy: int,
) -> None:
    """Move an Identity Lock rectangle by a permitted offset."""
    if dx == 0 and dy == 0:
        return
    block = [[idle[y][x] for x in range(x0, x1 + 1)] for y in range(y0, y1 + 1)]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            force_set(frame, x, y, None)
    for j, y in enumerate(range(y0, y1 + 1)):
        for i, x in enumerate(range(x0, x1 + 1)):
            force_set(frame, x + dx, y + dy, block[j][i])


def apply_body_offsets(
    frame: list[list[Cell]],
    idle: list[list[Cell]],
    helmet_off: tuple[int, int],
    belt_off: tuple[int, int],
) -> None:
    _, hx0, hx1, hy0, hy1 = HELMET
    _, bx0, bx1, by0, by1 = BELT
    shift_rect(frame, idle, hx0, hx1, hy0, hy1, *helmet_off)
    shift_rect(frame, idle, bx0, bx1, by0, by1, *belt_off)


def erase_idle_pickaxe(frame: list[list[Cell]], *, helmet_off: tuple[int, int], belt_off: tuple[int, int]) -> None:
    clear_xy = [
        (3, 3), (4, 3), (2, 4), (3, 4),
        (1, 5), (2, 5), (3, 5), (4, 5),
        (1, 6), (2, 6), (3, 6),
        (0, 7), (1, 7), (2, 7), (3, 7), (4, 7),
        (0, 8), (1, 8), (0, 9), (1, 9), (3, 9),
        (2, 11), (2, 12),
    ]
    for x, y in clear_xy:
        set_cell(frame, x, y, None, helmet_off=helmet_off, belt_off=belt_off)


def _head_blob(cx: int, cy: int) -> list[tuple[int, int, Cell]]:
    """Heavier 3×3-ish pickaxe head for readable mass."""
    return [
        (cx - 1, cy - 1, HEAD_DARK),
        (cx, cy - 1, HEAD_LIT),
        (cx + 1, cy - 1, HEAD),
        (cx - 1, cy, HEAD),
        (cx, cy, HEAD_LIT),
        (cx + 1, cy, HEAD),
        (cx - 1, cy + 1, OUTLINE),
        (cx, cy + 1, HEAD_DARK),
        (cx + 1, cy + 1, HEAD_DARK),
        (cx, cy - 2, HEAD),
        (cx + 1, cy - 2, HEAD_LIT),
    ]


def _lean_mass(
    *,
    direction: str,
    helmet_off: tuple[int, int],
    belt_off: tuple[int, int],
) -> list[tuple[int, int, Cell]]:
    """Unlocked torso / shoulder mass that sells weight shift."""
    cells: list[tuple[int, int, Cell]] = []
    if direction == "back":
        # stack mass on the rear (left) between face and belt
        for y, color in (
            (11, TUNIC_DARK),
            (12, TUNIC),
            (13, TUNIC_MID),
            (14, TUNIC),
        ):
            cells.extend([(2, y, color), (3, y, TUNIC_DARK)])
        cells.extend([(1, 12, OUTLINE), (1, 13, TUNIC_DARK)])
    elif direction == "forward":
        for y, color in (
            (11, TUNIC),
            (12, TUNIC_MID),
            (13, TUNIC),
            (14, TUNIC_DARK),
        ):
            cells.extend([(13, y, color), (14, y, TUNIC_DARK)])
        cells.extend(
            [
                (13, 11, BEARD_DARK),
                (14, 11, BEARD),
                (15, 12, OUTLINE),
                (15, 13, TUNIC_DARK),
            ]
        )
    elif direction == "squash":
        # impact: compress midsection; refill the band vacated when belt moves +1y
        cells.extend(
            [
                (13, 14, TUNIC_MID),
                (14, 14, TUNIC),
                (13, 19, TUNIC_DARK),
                (14, 19, TUNIC),
                (2, 14, TUNIC_DARK),
                (3, 14, TUNIC),
                (2, 19, TUNIC_DARK),
                (3, 19, OUTLINE),
                (13, 13, BEARD),
                (14, 13, BEARD_DARK),
                # bridge old belt row (y=15) after belt_core shifts to y=16..19
                (4, 15, TUNIC_DARK),
                (5, 15, TUNIC),
                (6, 15, TUNIC_MID),
                (7, 15, TUNIC),
                (8, 15, TUNIC_DARK),
                (9, 15, TUNIC),
                (10, 15, TUNIC_MID),
                (11, 15, TUNIC),
                (12, 15, TUNIC_DARK),
                (3, 15, OUTLINE),
                (13, 15, OUTLINE),
            ]
        )
    return cells


def _base(idle: list[list[Cell]], helmet_off: tuple[int, int], belt_off: tuple[int, int]) -> list[list[Cell]]:
    frame = clone_frame(idle)
    apply_body_offsets(frame, idle, helmet_off, belt_off)
    erase_idle_pickaxe(frame, helmet_off=helmet_off, belt_off=belt_off)
    return frame


def author_swing_frames(idle: list[list[Cell]]) -> list[list[list[Cell]]]:
    """Four Frames with coil → whip → commit → strike (not a single pivot)."""
    frames: list[list[list[Cell]]] = []

    # Frame 0 — anticipation coil: lean back, tool high behind head.
    h0, b0 = (-1, 0), (-1, 0)
    f0 = _base(idle, h0, b0)
    paint(
        f0,
        [
            *_lean_mass(direction="back", helmet_off=h0, belt_off=b0),
            # tool high / behind — tall wind-up
            (1, 0, HEAD_DARK),
            (2, 0, HEAD_LIT),
            (3, 0, HEAD),
            (0, 1, HEAD_DARK),
            *_head_blob(2, 2),
            (1, 3, HANDLE_MID),
            (2, 4, HANDLE),
            (2, 5, HANDLE_MID),
            (3, 6, HANDLE),
            (3, 7, HANDLE_MID),
            (3, 8, GLOVE_LIT),
            (2, 8, GLOVE),
            (2, 9, OUTLINE),
            (1, 8, OUTLINE),
            (3, 9, GLOVE),
            # rear elbow / shoulder pull
            (1, 10, OUTLINE),
            (2, 10, GLOVE_LIT),
        ],
        helmet_off=h0,
        belt_off=b0,
    )
    frames.append(f0)

    # Frame 1 — accelerated downswing at head height (fast beat).
    h1, b1 = (0, 0), (0, 0)
    f1 = _base(idle, h1, b1)
    paint(
        f1,
        [
            # long horizontal leverage — head ahead of face, handle stretches back
            *_head_blob(14, 4),
            (15, 3, HEAD_LIT),
            (15, 4, HEAD),
            (15, 5, HEAD_DARK),
            (13, 4, HANDLE_MID),
            (13, 5, HANDLE),
            (13, 6, HANDLE_MID),
            (13, 7, HANDLE),
            (13, 8, HANDLE_MID),
            (13, 9, HANDLE),
            (13, 10, GLOVE_LIT),
            (14, 10, OUTLINE),
            (12, 11, GLOVE),
            (11, 12, GLOVE_LIT),
            (10, 12, OUTLINE),
            (9, 13, GLOVE),
            (8, 13, OUTLINE),
            # trailing motion streak (1 cell) behind the head
            (12, 3, HEAD_DARK),
            (11, 14, HANDLE),
        ],
        helmet_off=h1,
        belt_off=b1,
    )
    frames.append(f1)

    # Frame 2 — commit forward: body lean + tool crossing down.
    h2, b2 = (1, 0), (1, 0)
    f2 = _base(idle, h2, b2)
    paint(
        f2,
        [
            *_lean_mass(direction="forward", helmet_off=h2, belt_off=b2),
            *_head_blob(14, 13),
            (15, 12, HEAD_LIT),
            (15, 13, HEAD),
            (15, 14, HEAD_DARK),
            (13, 12, HANDLE_MID),
            (13, 13, HANDLE),
            (12, 13, HANDLE_MID),
            (12, 14, HANDLE),
            (11, 14, HANDLE_MID),
            (10, 14, GLOVE_LIT),
            (9, 14, GLOVE),
            (9, 13, OUTLINE),
            (8, 13, OUTLINE),
            (8, 14, GLOVE),
            # follow-through beard / arm mass outside face lock
            (14, 11, BEARD),
            (13, 11, BEARD_DARK),
        ],
        helmet_off=h2,
        belt_off=b2,
    )
    frames.append(f2)

    # Frame 3 — impact: squash (+1,+1), tip buried ahead of planted boots.
    h3, b3 = (1, 1), (1, 1)
    f3 = _base(idle, h3, b3)
    paint(
        f3,
        [
            *_lean_mass(direction="squash", helmet_off=h3, belt_off=b3),
            # chunky contact wedge at ground, ahead of boots (x=15)
            (15, 19, HEAD_LIT),
            (15, 20, HEAD),
            (15, 21, HEAD_DARK),
            (15, 22, OUTLINE),
            (15, 23, OUTLINE),
            (14, 20, HEAD),
            (14, 19, HEAD_DARK),
            # handle braced from strike up the right column (outside belt after +1)
            (13, 19, HANDLE_MID),
            (13, 18, HANDLE),  # may be inside shifted belt — skipped if locked
            (14, 18, HANDLE_MID),
            (14, 17, HANDLE),
            (14, 16, HANDLE_MID),
            (14, 15, HANDLE),
            (13, 14, HANDLE_MID),
            (12, 14, HANDLE),
            (11, 14, GLOVE_LIT),
            (10, 14, GLOVE),
            (10, 13, OUTLINE),
            (9, 13, OUTLINE),
            (9, 14, GLOVE),
            # impact "weight" in free cells just above boots
            (2, 20, OUTLINE),
            (13, 20, HANDLE),
        ],
        helmet_off=h3,
        belt_off=b3,
    )
    frames.append(f3)

    return frames


def frame_to_ascii(frame: list[list[Cell]]) -> str:
    lines = []
    for y, row in enumerate(frame):
        lines.append(
            f"{y:02d} " + "".join("#" if cell is not None else "." for cell in row)
        )
    return "\n".join(lines)
