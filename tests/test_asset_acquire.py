"""Attested asset-acquisition Attempt store tests (#229)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline import asset_acquire as aa
from pipeline import gate_evidence as ge


def _candidate(path: Path, *, size: tuple[int, int] = (24, 32), tag: int = 0) -> Path:
    image = Image.new("RGBA", size, (tag % 256, 10, 20, 255))
    image.save(path)
    return path


def _env(store_root: Path) -> dict[str, str]:
    return {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}


def _record(
    tmp_path: Path,
    store_root: Path,
    *,
    specification_id: str = "first-room/dwarf/swing",
    candidate: Path | None = None,
    clock=lambda: "2026-07-27T12:00:00+00:00",
    **kwargs,
):
    candidate = candidate or _candidate(tmp_path / "candidate.png")
    with patch.dict("os.environ", _env(store_root)):
        return aa.record_asset_attempt(
            candidate,
            specification_id,
            motion_class=kwargs.pop("motion_class", "swing"),
            generation_mode=kwargs.pop("generation_mode", "image-edit"),
            acquiring_agent=kwargs.pop("acquiring_agent", "cursor-agent"),
            prompt_text=kwargs.pop("prompt_text", "swing the pick"),
            repo_root=tmp_path,
            clock=clock,
            **kwargs,
        )


# --- C1: store layout and root resolution -----------------------------------


def test_store_root_resolves_to_default_when_override_unset(tmp_path: Path) -> None:
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("UNDERLINE_ACQUISITION_CONTROLS_ROOT", None)
        root = aa.acquisition_controls_root(tmp_path)
    assert root == tmp_path / "acquisition-controls"


def test_store_root_resolves_to_override_when_set(tmp_path: Path) -> None:
    override = tmp_path / "elsewhere" / "store"
    with patch.dict("os.environ", {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(override)}):
        root = aa.acquisition_controls_root(tmp_path)
    assert root == override


def test_record_writes_every_store_path_under_resolved_root(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    row = _record(tmp_path, store_root)
    assert (store_root / "attempts.jsonl").is_file()
    assert (store_root / row["raw_path"]).is_file()
    assert (store_root / row["provenance_path"]).is_file()
    assert (store_root / ".attempt-counters.json").is_file()


# --- C2: specification IDs and monotonic Attempt allocation -----------------


def test_three_attempts_for_one_specification_have_dense_ordinals_and_predecessor_chain(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    first = _record(tmp_path, store_root)
    second = _record(tmp_path, store_root)
    third = _record(tmp_path, store_root)

    assert (first["ordinal"], second["ordinal"], third["ordinal"]) == (1, 2, 3)
    assert first["attempt_id"] == "first-room--dwarf--swing--001"
    assert second["attempt_id"] == "first-room--dwarf--swing--002"
    assert third["attempt_id"] == "first-room--dwarf--swing--003"
    assert first["predecessor_attempt_id"] is None
    assert second["predecessor_attempt_id"] == "first-room--dwarf--swing--001"
    assert third["predecessor_attempt_id"] == "first-room--dwarf--swing--002"


def test_interleaved_specification_ids_get_independent_ordinal_sequences(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    swing_1 = _record(tmp_path, store_root, specification_id="first-room/dwarf/swing")
    walk_1 = _record(tmp_path, store_root, specification_id="first-room/dwarf/walk")
    swing_2 = _record(tmp_path, store_root, specification_id="first-room/dwarf/swing")
    walk_2 = _record(tmp_path, store_root, specification_id="first-room/dwarf/walk")

    assert (swing_1["ordinal"], swing_2["ordinal"]) == (1, 2)
    assert (walk_1["ordinal"], walk_2["ordinal"]) == (1, 2)
    assert swing_2["predecessor_attempt_id"] == swing_1["attempt_id"]
    assert walk_2["predecessor_attempt_id"] == walk_1["attempt_id"]


# --- C3: the caller may not supply attested fields ---------------------------


@pytest.mark.parametrize(
    "field",
    ["attempt_id", "ordinal", "predecessor_attempt_id", "generated_at", "raw_sha256", "dimensions"],
)
def test_attested_fields_are_not_accepted_from_the_caller(tmp_path: Path, field: str) -> None:
    store_root = tmp_path / "acquisition-controls"
    candidate = _candidate(tmp_path / "candidate.png")
    with patch.dict("os.environ", _env(store_root)):
        with pytest.raises(TypeError):
            aa.record_asset_attempt(
                candidate,
                "first-room/dwarf/swing",
                motion_class="swing",
                generation_mode="image-edit",
                acquiring_agent="cursor-agent",
                prompt_text="swing the pick",
                repo_root=tmp_path,
                **{field: "not-allowed"},
            )


def test_recorded_at_comes_from_the_injected_clock(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    row = _record(tmp_path, store_root, clock=lambda: "2099-01-01T00:00:00+00:00")
    assert row["recorded_at"] == "2099-01-01T00:00:00+00:00"


# --- C4: bytes are captured before they are described -----------------------


def test_mutating_the_callers_png_after_recording_does_not_change_the_store_copy(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    candidate = _candidate(tmp_path / "candidate.png", size=(24, 32))
    row = _record(tmp_path, store_root, candidate=candidate)
    raw_path = store_root / row["raw_path"]
    original_bytes = raw_path.read_bytes()
    original_sha = row["raw_sha256"]
    original_dimensions = row["dimensions"]

    Image.new("RGBA", (99, 99), (255, 255, 255, 255)).save(candidate)

    assert raw_path.read_bytes() == original_bytes
    assert ge.sha256_file(raw_path) == original_sha
    assert original_dimensions == [24, 32]


def test_recording_into_an_occupied_raw_path_raises(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    row = _record(tmp_path, store_root)
    raw_path = store_root / row["raw_path"]
    # Force a collision by writing the raw file directly for the next ordinal.
    next_raw = store_root / "raw" / "first-room--dwarf--swing--002.png"
    next_raw.parent.mkdir(parents=True, exist_ok=True)
    next_raw.write_bytes(raw_path.read_bytes())

    with pytest.raises(aa.AssetAcquisitionError):
        _record(tmp_path, store_root)


# --- C5: rejections are Attempts ---------------------------------------------


def test_rejected_attempt_carries_reason_and_consumes_an_ordinal(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    row = _record(tmp_path, store_root, outcome="rejected", rejection_reason="silhouette failed")
    assert row["outcome"] == "rejected"
    assert row["rejection_reason"] == "silhouette failed"
    assert row["ordinal"] == 1

    second = _record(tmp_path, store_root)
    assert second["ordinal"] == 2
    assert second["predecessor_attempt_id"] == row["attempt_id"]


def test_rejected_attempt_without_reason_raises(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    with pytest.raises(aa.AssetAcquisitionError):
        _record(tmp_path, store_root, outcome="rejected")


# --- C6: ledger rows are append-only -----------------------------------------


def test_attempts_jsonl_grows_by_one_line_per_attempt_and_earlier_lines_are_unchanged(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    _record(tmp_path, store_root)
    ledger_path = store_root / "attempts.jsonl"
    first_line = ledger_path.read_text().splitlines()[0]

    _record(tmp_path, store_root)
    lines = ledger_path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == first_line


def test_load_asset_attempts_raises_on_a_hand_deleted_middle_row(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    _record(tmp_path, store_root)
    _record(tmp_path, store_root)
    _record(tmp_path, store_root)

    ledger_path = store_root / "attempts.jsonl"
    lines = ledger_path.read_text().splitlines()
    del lines[1]
    ledger_path.write_text("\n".join(lines) + "\n")

    with pytest.raises(aa.AssetAcquisitionError):
        aa.load_asset_attempts(store_root, "first-room/dwarf/swing")


def test_load_asset_attempts_returns_rows_in_ordinal_order(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    _record(tmp_path, store_root)
    _record(tmp_path, store_root)
    _record(tmp_path, store_root)

    rows = aa.load_asset_attempts(store_root, "first-room/dwarf/swing")
    assert [row["ordinal"] for row in rows] == [1, 2, 3]
