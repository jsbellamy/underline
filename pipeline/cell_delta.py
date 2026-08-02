"""Exact Cell-delta ledger build, validation, and replay (issue #276)."""

from __future__ import annotations

import copy
import io
import re
from typing import Any, Mapping, Sequence

from PIL import Image

from pipeline.gate_evidence import sha256_bytes
from pipeline.recovery import MAGENTA
from pipeline.strip import Cell, canonicalize_frame

__all__ = [
    "CellDeltaError",
    "assert_cell_delta_replay",
    "build_cell_delta_ledger",
    "replay_cell_delta_ledger",
    "validate_cell_delta_ledger",
]

SCHEMA = "cell-delta-ledger/0"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class CellDeltaError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        frame: int | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.frame = frame
        self.x = x
        self.y = y


def _cell_to_rgba(cell: Cell) -> list[int]:
    if cell is None:
        return [0, 0, 0, 0]
    return [cell[0], cell[1], cell[2], 255]


def _rgba_to_cell(rgba: Sequence[int]) -> Cell:
    if rgba[3] == 0:
        return None
    return (rgba[0], rgba[1], rgba[2])


def _frame_png_bytes(cells: list[list[Cell]]) -> bytes:
    frame_h = len(cells)
    frame_w = len(cells[0]) if cells else 0
    logical = canonicalize_frame(cells, frame_w=frame_w, frame_h=frame_h)
    height = len(logical)
    width = len(logical[0]) if logical else 0
    image = Image.new("RGBA", (width, height), (*MAGENTA, 0))
    pixels = image.load()
    assert pixels is not None
    for row_y in range(height):
        for col_x in range(width):
            rgb = logical[row_y][col_x]
            if rgb is not None:
                pixels[col_x, row_y] = (*rgb, 255)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _frame_sha256(cells: list[list[Cell]]) -> str:
    return sha256_bytes(_frame_png_bytes(cells))


def _frame_dimensions(frame: list[list[Cell]]) -> tuple[int, int]:
    height = len(frame)
    width = len(frame[0]) if frame else 0
    return width, height


def _validate_rgba(value: object, *, field: str) -> list[int]:
    if not isinstance(value, list) or len(value) != 4:
        raise CellDeltaError(
            f"invalid rgba for {field}",
            reason_code="invalid_cell_delta_ledger_alpha",
        )
    rgba = [int(channel) for channel in value]
    for channel in rgba[:3]:
        if not 0 <= channel <= 255:
            raise CellDeltaError(
                f"invalid rgba channel for {field}",
                reason_code="invalid_cell_delta_ledger_alpha",
            )
    alpha = rgba[3]
    if alpha not in (0, 255):
        raise CellDeltaError(
            f"non-binary alpha for {field}",
            reason_code="invalid_cell_delta_ledger_alpha",
        )
    return rgba


def build_cell_delta_ledger(
    base_frames: Sequence[list[list[Cell]]],
    target_frames: Sequence[list[list[Cell]]],
    *,
    base_specification_id: str,
    base_frame_mapping: Sequence[int],
) -> dict[str, Any]:
    if len(base_frame_mapping) != len(target_frames):
        raise CellDeltaError(
            "base_frame_mapping length must match target frame count",
            reason_code="invalid_cell_delta_ledger_target_count",
        )

    base_hashes = [_frame_sha256(frame) for frame in base_frames]
    deltas: list[dict[str, Any]] = []

    for frame_index, (target_frame, base_index) in enumerate(
        zip(target_frames, base_frame_mapping)
    ):
        if not isinstance(base_index, int) or not 0 <= base_index < len(base_frames):
            raise CellDeltaError(
                f"invalid base frame mapping at target {frame_index}",
                reason_code="invalid_cell_delta_ledger_mapping",
            )
        base_frame = base_frames[base_index]
        target_w, target_h = _frame_dimensions(target_frame)
        base_w, base_h = _frame_dimensions(base_frame)
        if target_w != base_w or target_h != base_h:
            raise CellDeltaError(
                f"frame dimension mismatch at target {frame_index}",
                reason_code="invalid_cell_delta_ledger_bounds",
            )

        for y in range(target_h):
            for x in range(target_w):
                base_cell = base_frame[y][x]
                target_cell = target_frame[y][x]
                if base_cell == target_cell:
                    continue
                deltas.append(
                    {
                        "frame": frame_index,
                        "x": x,
                        "y": y,
                        "from": _cell_to_rgba(base_cell),
                        "to": _cell_to_rgba(target_cell),
                    }
                )

    return {
        "schema": SCHEMA,
        "base_specification_id": base_specification_id,
        "base_frames_sha256": base_hashes,
        "base_frame_mapping": list(base_frame_mapping),
        "target_frame_count": len(target_frames),
        "deltas": deltas,
    }


def validate_cell_delta_ledger(
    base_frames: Sequence[list[list[Cell]]],
    ledger: Mapping[str, Any],
) -> None:
    schema = ledger.get("schema")
    if schema != SCHEMA:
        raise CellDeltaError(
            f"unknown cell delta ledger schema: {schema!r}",
            reason_code="invalid_cell_delta_ledger_schema",
        )

    base_hashes = ledger.get("base_frames_sha256")
    if not isinstance(base_hashes, list):
        raise CellDeltaError(
            "base_frames_sha256 must be a list",
            reason_code="invalid_cell_delta_ledger_digest",
        )
    for digest in base_hashes:
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise CellDeltaError(
                f"malformed base frame digest: {digest!r}",
                reason_code="invalid_cell_delta_ledger_digest",
            )

    if len(base_hashes) != len(base_frames):
        raise CellDeltaError(
            "base_frames_sha256 length must match supplied base frames",
            reason_code="invalid_cell_delta_ledger_digest",
        )

    for index, (expected, frame) in enumerate(zip(base_hashes, base_frames)):
        actual = _frame_sha256(frame)
        if actual != expected:
            raise CellDeltaError(
                f"base frame hash mismatch at index {index}",
                reason_code="base_frame_hash_mismatch",
            )

    mapping = ledger.get("base_frame_mapping")
    if not isinstance(mapping, list):
        raise CellDeltaError(
            "base_frame_mapping must be a list",
            reason_code="invalid_cell_delta_ledger_mapping",
        )

    target_frame_count = ledger.get("target_frame_count")
    if not isinstance(target_frame_count, int):
        raise CellDeltaError(
            "target_frame_count must be an integer",
            reason_code="invalid_cell_delta_ledger_target_count",
        )
    if target_frame_count != len(mapping):
        raise CellDeltaError(
            "target_frame_count must match base_frame_mapping length",
            reason_code="invalid_cell_delta_ledger_target_count",
        )

    deltas = ledger.get("deltas")
    if not isinstance(deltas, list):
        raise CellDeltaError(
            "deltas must be a list",
            reason_code="invalid_cell_delta_ledger_order",
        )

    previous_key: tuple[int, int, int] | None = None
    seen: set[tuple[int, int, int]] = set()

    for row_index, row in enumerate(deltas):
        if not isinstance(row, Mapping):
            raise CellDeltaError(
                f"delta row {row_index} must be an object",
                reason_code="invalid_cell_delta_ledger_order",
            )

        frame = row.get("frame")
        x = row.get("x")
        y = row.get("y")
        if not isinstance(frame, int) or not isinstance(x, int) or not isinstance(y, int):
            raise CellDeltaError(
                f"delta row {row_index} has invalid coordinates",
                reason_code="invalid_cell_delta_ledger_bounds",
            )

        key = (frame, y, x)
        if key in seen:
            raise CellDeltaError(
                f"duplicate delta at frame {frame}, x {x}, y {y}",
                reason_code="invalid_cell_delta_ledger_duplicate",
            )
        seen.add(key)
        if previous_key is not None and key < previous_key:
            raise CellDeltaError(
                f"delta rows are not sorted at frame {frame}, y {y}, x {x}",
                reason_code="invalid_cell_delta_ledger_order",
            )
        previous_key = key

        if frame < 0 or frame >= target_frame_count:
            raise CellDeltaError(
                f"delta frame {frame} out of range",
                reason_code="invalid_cell_delta_ledger_bounds",
            )

        base_index = mapping[frame]
        if not isinstance(base_index, int) or not 0 <= base_index < len(base_frames):
            raise CellDeltaError(
                f"invalid base mapping for target frame {frame}",
                reason_code="invalid_cell_delta_ledger_mapping",
            )

        base_frame = base_frames[base_index]
        frame_w, frame_h = _frame_dimensions(base_frame)
        if x < 0 or x >= frame_w or y < 0 or y >= frame_h:
            raise CellDeltaError(
                f"delta coordinate out of bounds at frame {frame}, x {x}, y {y}",
                reason_code="invalid_cell_delta_ledger_bounds",
            )

        from_rgba = _validate_rgba(row.get("from"), field="from")
        to_rgba = _validate_rgba(row.get("to"), field="to")
        if from_rgba == to_rgba:
            raise CellDeltaError(
                f"no-op delta at frame {frame}, x {x}, y {y}",
                reason_code="invalid_cell_delta_ledger_noop",
            )

        expected_from = _cell_to_rgba(base_frame[y][x])
        if from_rgba != expected_from:
            raise CellDeltaError(
                f"from value does not match base frame at frame {frame}, x {x}, y {y}",
                reason_code="invalid_cell_delta_ledger_from",
            )


def replay_cell_delta_ledger(
    base_frames: Sequence[list[list[Cell]]],
    ledger: Mapping[str, Any],
) -> list[list[list[Cell]]]:
    validate_cell_delta_ledger(base_frames, ledger)
    mapping = ledger["base_frame_mapping"]
    target_frames = [
        copy.deepcopy(base_frames[mapping[frame_index]])
        for frame_index in range(ledger["target_frame_count"])
    ]
    for row in ledger["deltas"]:
        frame_index = row["frame"]
        x = row["x"]
        y = row["y"]
        target_frames[frame_index][y][x] = _rgba_to_cell(row["to"])
    return target_frames


def assert_cell_delta_replay(
    base_frames: Sequence[list[list[Cell]]],
    target_frames: Sequence[list[list[Cell]]],
    ledger: Mapping[str, Any],
) -> None:
    replayed = replay_cell_delta_ledger(base_frames, ledger)
    if len(replayed) != len(target_frames):
        raise CellDeltaError(
            "replayed target frame count mismatch",
            reason_code="cell_delta_replay_mismatch",
            frame=0,
            x=0,
            y=0,
        )
    for frame_index, (actual, expected) in enumerate(zip(replayed, target_frames)):
        actual_w, actual_h = _frame_dimensions(actual)
        expected_w, expected_h = _frame_dimensions(expected)
        if actual_w != expected_w or actual_h != expected_h:
            raise CellDeltaError(
                f"frame dimension mismatch at target {frame_index}",
                reason_code="cell_delta_replay_mismatch",
                frame=frame_index,
                x=0,
                y=0,
            )
        for y in range(actual_h):
            for x in range(actual_w):
                if actual[y][x] != expected[y][x]:
                    raise CellDeltaError(
                        f"replay mismatch at frame {frame_index}, x {x}, y {y}",
                        reason_code="cell_delta_replay_mismatch",
                        frame=frame_index,
                        x=x,
                        y=y,
                    )
