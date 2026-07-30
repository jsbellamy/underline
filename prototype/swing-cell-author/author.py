"""PROTOTYPE — pure Cell-author logic for a swing pose from idle.

Throwaway. Lift only if a later acquisition path adopts Cell authoring.
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
TUNIC_DARK = (0x19, 0x3A, 0x32)
BEARD = (0x93, 0x56, 0x31)

# Swing Identity Lock rectangles (inclusive) — never paint these.
LOCKS: tuple[tuple[str, int, int, int, int], ...] = (
    ("helmet_face", 5, 12, 1, 10),
    ("belt_core", 4, 12, 15, 18),
    ("boots", 3, 14, 21, 23),
)

W, H = 16, 24


def in_lock(x: int, y: int) -> bool:
    for _, x0, x1, y0, y1 in LOCKS:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def clone_frame(frame: list[list[Cell]]) -> list[list[Cell]]:
    return deepcopy(frame)


def set_cell(frame: list[list[Cell]], x: int, y: int, rgb: Cell) -> None:
    if not (0 <= x < W and 0 <= y < H):
        return
    if in_lock(x, y):
        return
    frame[y][x] = rgb


def clear_cell(frame: list[list[Cell]], x: int, y: int) -> None:
    set_cell(frame, x, y, None)


def paint(
    frame: list[list[Cell]], cells: Iterable[tuple[int, int, Cell]]
) -> None:
    for x, y, rgb in cells:
        set_cell(frame, x, y, rgb)


def erase_idle_pickaxe_and_raised_arm(frame: list[list[Cell]]) -> None:
    """Clear idle tool / rear-shoulder mass left of the helmet lock."""
    clear_xy = [
        (3, 3),
        (4, 3),
        (2, 4),
        (3, 4),
        (1, 5),
        (2, 5),
        (3, 5),
        (4, 5),
        (1, 6),
        (2, 6),
        (3, 6),
        (0, 7),
        (1, 7),
        (2, 7),
        (3, 7),
        (4, 7),
        (0, 8),
        (1, 8),
        (0, 9),
        (1, 9),
        (3, 9),
        (2, 11),
        (2, 12),
    ]
    for x, y in clear_xy:
        clear_cell(frame, x, y)


def _head_blob(cx: int, cy: int) -> list[tuple[int, int, Cell]]:
    return [
        (cx - 1, cy - 1, HEAD_DARK),
        (cx, cy - 1, HEAD),
        (cx + 1, cy - 1, HEAD_LIT),
        (cx - 1, cy, HEAD),
        (cx, cy, HEAD_LIT),
        (cx + 1, cy, HEAD),
        (cx - 1, cy + 1, OUTLINE),
        (cx, cy + 1, HEAD_DARK),
        (cx + 1, cy + 1, OUTLINE),
    ]


def author_swing_frames(idle: list[list[Cell]]) -> list[list[list[Cell]]]:
    """Four Frames: anticipation → downswing → cross → ground contact.

    Handle / head Cells are routed around Identity Lock rectangles so the
    idle lock bytes stay byte-identical inside those rects.
    """
    frames: list[list[list[Cell]]] = []

    # Frame 0 — anticipation: pickaxe raised behind / above helmet (left column).
    f0 = clone_frame(idle)
    erase_idle_pickaxe_and_raised_arm(f0)
    paint(
        f0,
        [
            (2, 0, HEAD_DARK),
            (3, 0, HEAD_LIT),
            (4, 0, HEAD),
            *_head_blob(3, 1),
            # handle down x=4 (left of helmet lock x0=5)
            (4, 2, HANDLE_MID),
            (4, 3, HANDLE),
            (4, 4, HANDLE_MID),
            (4, 5, HANDLE),
            (4, 6, HANDLE_MID),
            (4, 7, HANDLE),
            (4, 8, GLOVE_LIT),
            (3, 8, GLOVE),
            (3, 9, OUTLINE),
            (2, 8, OUTLINE),
            (3, 11, TUNIC),
            (3, 12, TUNIC_DARK),
        ],
    )
    frames.append(f0)

    # Frame 1 — downswing at head height, ahead/right. Stay at x>=13 through face band.
    f1 = clone_frame(idle)
    erase_idle_pickaxe_and_raised_arm(f1)
    paint(
        f1,
        [
            *_head_blob(14, 5),
            (15, 4, HEAD_LIT),
            (15, 5, HEAD),
            (15, 6, HEAD_DARK),
            (13, 5, HANDLE_MID),
            (13, 6, HANDLE),
            (13, 7, HANDLE_MID),
            (13, 8, HANDLE),
            (13, 9, HANDLE_MID),
            (13, 10, HANDLE),
            (13, 11, GLOVE_LIT),
            (13, 12, GLOVE),
            (14, 11, OUTLINE),
            (12, 12, GLOVE),
            (12, 13, OUTLINE),
            (11, 13, GLOVE_LIT),
            (11, 14, HANDLE),
        ],
    )
    frames.append(f1)

    # Frame 2 — crossing forward below the face lock.
    f2 = clone_frame(idle)
    erase_idle_pickaxe_and_raised_arm(f2)
    paint(
        f2,
        [
            *_head_blob(14, 12),
            (15, 11, HEAD_LIT),
            (15, 12, HEAD),
            (15, 13, HEAD_DARK),
            (13, 11, HANDLE_MID),
            (13, 12, HANDLE),
            (12, 12, HANDLE_MID),
            (12, 13, HANDLE),
            (11, 13, HANDLE_MID),
            (11, 14, HANDLE),
            (10, 14, HANDLE_MID),
            (9, 14, GLOVE_LIT),
            (8, 14, GLOVE),
            (8, 13, OUTLINE),
            (7, 13, OUTLINE),
            (13, 14, BEARD),
        ],
    )
    frames.append(f2)

    # Frame 3 — ground contact ahead of boots (x=15 outside boots lock x1=14).
    # Route handle along x=13 (right of belt lock x1=12) then across y=14.
    f3 = clone_frame(idle)
    erase_idle_pickaxe_and_raised_arm(f3)
    paint(
        f3,
        [
            (15, 20, HEAD_LIT),
            (15, 21, HEAD),
            (15, 22, HEAD_DARK),
            (15, 23, OUTLINE),
            (14, 20, HEAD),
            (13, 20, HANDLE_MID),
            (13, 19, HANDLE),
            (13, 18, HANDLE_MID),
            (13, 17, HANDLE),
            (13, 16, HANDLE_MID),
            (13, 15, HANDLE),
            (13, 14, HANDLE_MID),
            (12, 14, HANDLE),
            (11, 14, HANDLE_MID),
            (10, 14, HANDLE),
            (9, 14, GLOVE_LIT),
            (8, 14, GLOVE),
            (8, 13, OUTLINE),
            (7, 13, OUTLINE),
            (14, 19, HEAD_DARK),
        ],
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
