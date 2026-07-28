"""Tests for pipeline.evidence_store (#139)."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import evidence_store as es

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("env", "case"),
    [
        pytest.param(None, "unset", id="unset"),
        pytest.param("custom-store", "override", id="override"),
        pytest.param("", "empty_string", id="empty_string"),
    ],
)
def test_for_repo_resolves_gate_controls_root(
    tmp_path: Path,
    env: str | None,
    case: str,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    if case == "override":
        override = tmp_path / "custom-store"
        override.mkdir()
        expected = override
        env_value = str(override)
    else:
        expected = repo / "gate-controls"
        env_value = env if env is not None else ""

    env_patch: dict[str, str] = {}
    if case == "unset":
        removed = os.environ.pop("UNDERLINE_GATE_CONTROLS_ROOT", None)
        try:
            store = es.EvidenceStore.for_repo(repo)
        finally:
            if removed is not None:
                os.environ["UNDERLINE_GATE_CONTROLS_ROOT"] = removed
    else:
        env_patch["UNDERLINE_GATE_CONTROLS_ROOT"] = env_value
        with patch.dict(os.environ, env_patch, clear=False):
            store = es.EvidenceStore.for_repo(repo)

    assert store.repo_root == repo
    assert store.root == expected


def test_at_custom_store_directory(tmp_path: Path) -> None:
    repo = tmp_path
    custom = tmp_path / "custom-name"
    custom.mkdir()
    store = es.EvidenceStore.at(custom, repo_root=repo)
    assert store.root == custom
    assert store.raw("idle--palette_drift_pass--001") == (
        custom / "raw/idle--palette_drift_pass--001.png"
    ).resolve()


def test_review_ordinals_and_filenames() -> None:
    assert es.REVIEW_ORDINALS == (1, 2)
    store = es.EvidenceStore.for_repo(ROOT)
    attempt = "idle--palette_drift_pass--001"
    assert store.review(attempt, 1).name == "review--01.json"
    assert store.review_input(attempt, 2).name == "review-input--02.json"


def test_relative_resolve_roundtrip_and_escape() -> None:
    store = es.EvidenceStore.for_repo(ROOT)
    sample = store.raw("idle--palette_drift_pass--001")
    assert sample.is_file()
    rel = store.relative(sample)
    assert rel == "gate-controls/raw/idle--palette_drift_pass--001.png"
    assert store.resolve(rel) == sample.resolve()
    with pytest.raises(es.EvidenceStoreError):
        store.resolve("../escape.json")


def test_module_performs_no_file_io() -> None:
    source = inspect.getsource(es)
    assert "read_text" not in source
    assert "write_text" not in source
    assert "open(" not in source
    assert "json." not in source


def test_id_helpers_match_acquire_formats() -> None:
    spec = es.specification_id("idle", "palette_drift_pass")
    assert spec == "idle/palette_drift_pass"
    promo = es.promotion_id_for_spec(spec)
    assert promo == "promo--idle--palette_drift_pass"
    attempt = es.attempt_id(spec, 1)
    assert attempt == "idle--palette_drift_pass--001"
    assert (
        es.measurement_filename("2026-07-26T16:21:45+00:00")
        == "2026-07-26T16-21-45+00-00.json"
    )


def _load_attempt_rows(store: es.EvidenceStore) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in store.attempts().read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _recorded_at_from_measurement_path(measurement_path: str) -> str:
    stem = Path(measurement_path).stem
    date_part, time_part = stem.split("T", 1)
    return f"{date_part}T{time_part.replace('-', ':')}"


def test_committed_store_paths_match_records() -> None:
    """Every path accessor agrees with the committed gate-controls store."""
    store = es.EvidenceStore.for_repo(ROOT)

    manifest = json.loads(store.manifest().read_text())
    promotions = manifest["promotions"]
    assert len(promotions) == 17

    for promo in promotions:
        attempt = str(promo["attempt_id"])
        promotion_id = str(promo["id"])
        measurement_path = str(promo["measurement_path"])
        recorded_at = _recorded_at_from_measurement_path(measurement_path)

        assert store.raw(attempt).is_file()
        assert store.provenance(attempt).is_file()
        assert store.measurement(attempt, recorded_at).is_file()
        assert store.review_dir(attempt).is_dir()
        assert store.packet(attempt).is_file()
        assert store.verification(promotion_id).is_file()

        assert store.resolve(measurement_path) == store.measurement(
            attempt, recorded_at
        ).resolve()

    for row in _load_attempt_rows(store):
        attempt = str(row["attempt_id"])

        raw_path = store.raw(attempt)
        if raw_path.is_file():
            assert store.resolve(store.relative(raw_path)) == raw_path.resolve()

        provenance_path = row.get("provenance_path")
        if provenance_path is not None:
            resolved = store.resolve(str(provenance_path))
            assert resolved.is_file()
            if Path(str(provenance_path)).name == f"{attempt}.json":
                assert resolved == store.provenance(attempt).resolve()

        measurement_path = row.get("measurement_path")
        if measurement_path is not None:
            recorded_at = _recorded_at_from_measurement_path(str(measurement_path))
            resolved = store.resolve(str(measurement_path))
            assert resolved.is_file()
            if f"reports/{attempt}/" in str(measurement_path):
                assert resolved == store.measurement(attempt, recorded_at).resolve()

        composite_path = row.get("composite_path")
        if composite_path is not None:
            resolved = store.resolve(str(composite_path))
            assert resolved.is_file()
            if f"reviews/{attempt}/" in str(composite_path):
                assert resolved == store.composite(attempt).resolve()
                assert store.review_dir(attempt).is_dir()

        packet_path = store.packet(attempt)
        if packet_path.is_file():
            assert packet_path == store.review_dir(attempt) / "packet.json"

        for ordinal in es.REVIEW_ORDINALS:
            review_path = store.review(attempt, ordinal)
            if review_path.is_file():
                assert review_path.name == f"review--{ordinal:02d}.json"
