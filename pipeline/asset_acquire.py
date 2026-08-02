"""Attested asset-acquisition Attempt store (#229).

Sibling to ``pipeline/gate_control_acquire.py``: allocates Attempt identity
under a repository lock, copies provider bytes into the store before
describing them, and derives every attested field (``attempt_id``, ordinal,
predecessor, timestamp, hash, dimensions, repository commit) from what was
observed rather than from what the acquiring agent asserted. This module only
registers Attempts against ``acquisition-controls/``; wiring bundle ``init``
to consume the store is #233.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from pipeline import gate_control as gc
from pipeline import gate_evidence as ge
from pipeline.final_polish import ATTEMPT_OUTCOMES, GENERATION_MODES

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

LEDGER_SCHEMA = "asset-acquisition/0"
PROVENANCE_SCHEMA = "asset-acquisition-provenance/0"

Clock = Callable[[], str]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


class AssetAcquisitionError(ValueError):
    """Fail-closed asset-acquisition failure."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class AssetAttemptIdentity:
    specification_id: str
    ordinal: int
    attempt_id: str
    predecessor_attempt_id: str | None


def acquisition_controls_root(repo_root: pathlib.Path | None = None) -> pathlib.Path:
    """Resolve the ``acquisition-controls/`` root, mirroring ``gate_controls_root``."""
    root = repo_root or REPO_ROOT
    override = os.environ.get("UNDERLINE_ACQUISITION_CONTROLS_ROOT")
    if override:
        return pathlib.Path(override)
    return root / "acquisition-controls"


def allocate_asset_attempt_identity(
    store_root: pathlib.Path,
    specification_id: str,
) -> AssetAttemptIdentity:
    """Monotonic Attempt ID allocation under an exclusive repository lock."""
    lock_path = store_root / ".attempt-alloc.lock"
    attempts_path = store_root / "attempts.jsonl"
    counters_path = store_root / ".attempt-counters.json"
    with ge.repository_lock(lock_path):
        ledger_max = 0
        predecessor: str | None = None
        if attempts_path.is_file():
            for line in attempts_path.read_text().splitlines():
                if not line.strip():
                    continue
                doc = json.loads(line)
                if doc.get("specification_id") != specification_id:
                    continue
                row_ordinal = int(doc.get("ordinal", 0))
                if row_ordinal >= ledger_max:
                    ledger_max = row_ordinal
                    predecessor = str(doc["attempt_id"])
        counters: dict[str, int] = {}
        if counters_path.is_file():
            counters = {
                str(key): int(value)
                for key, value in json.loads(counters_path.read_text()).items()
            }
        ordinal = max(ledger_max, counters.get(specification_id, 0)) + 1
        attempt_id = f"{specification_id.replace('/', '--')}--{ordinal:03d}"
        raw_path = store_root / "raw" / f"{attempt_id}.png"
        if raw_path.exists():
            raise AssetAcquisitionError(f"raw bytes already recorded: {raw_path}")
        counters[specification_id] = ordinal
        counters_path.write_text(json.dumps(counters, sort_keys=True) + "\n")
        pred = predecessor if ordinal > 1 else None
        return AssetAttemptIdentity(
            specification_id=specification_id,
            ordinal=ordinal,
            attempt_id=attempt_id,
            predecessor_attempt_id=pred,
        )


def _write_raw_bytes(raw_path: pathlib.Path, png: pathlib.Path) -> str:
    if raw_path.exists():
        raise AssetAcquisitionError(f"raw bytes already recorded: {raw_path}")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(png, raw_path)
    return ge.sha256_file(raw_path)


def _image_dimensions(path: pathlib.Path) -> list[int]:
    from PIL import Image

    with Image.open(path) as image:
        return list(image.size)


def _write_once_json(path: pathlib.Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise AssetAcquisitionError(f"refusing to overwrite existing evidence record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _append_ledger_row(path: pathlib.Path, row: Mapping[str, Any]) -> None:
    line = json.dumps(dict(row), sort_keys=True)
    json.loads(line)  # fail fast rather than interleave partial JSON
    lock_path = path.parent / ".attempts.lock"
    with ge.repository_lock(lock_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def record_asset_attempt(
    png: pathlib.Path,
    specification_id: str,
    *,
    motion_class: str,
    generation_mode: str,
    acquiring_agent: str,
    prompt_text: str | None = None,
    prompt_path: pathlib.Path | None = None,
    reference_image_sha256: str | None = None,
    edit_source: pathlib.Path | None = None,
    outcome: str = "accepted",
    rejection_reason: str | None = None,
    repo_root: pathlib.Path | None = None,
    clock: Clock = utc_now,
) -> dict[str, Any]:
    """Capture, hash, and ledger one asset Attempt from bytes this call observed.

    Every attested field (``attempt_id``, ``ordinal``, ``predecessor_attempt_id``,
    ``generated_at``/``recorded_at``, ``raw_sha256``, ``dimensions``,
    ``repository_commit``, ``prompt_sha256``) is derived here; none of them is a
    parameter, so passing one as a keyword raises ``TypeError`` from the
    signature itself.
    """
    if generation_mode == "cell-author":
        raise AssetAcquisitionError(
            "provider Attempt cannot claim cell-author generation mode",
            reason_code="provider_attempt_claims_cell_author",
        )
    if generation_mode not in GENERATION_MODES:
        raise AssetAcquisitionError(f"unknown generation_mode {generation_mode!r}")
    if outcome not in ATTEMPT_OUTCOMES:
        raise AssetAcquisitionError(f"unknown outcome {outcome!r}")
    if outcome == "rejected" and not rejection_reason:
        raise AssetAcquisitionError("a rejected Attempt requires a non-empty rejection_reason")

    root = repo_root or REPO_ROOT
    store_root = acquisition_controls_root(root)
    recorded_at = clock()

    if not png.is_file():
        raise AssetAcquisitionError(f"missing candidate PNG: {png}")

    if prompt_text is None:
        prompt_text = prompt_path.read_text() if prompt_path else ""
    prompt_sha256 = hashlib.sha256(prompt_text.encode()).hexdigest()

    identity = allocate_asset_attempt_identity(store_root, specification_id)

    raw_rel = f"raw/{identity.attempt_id}.png"
    raw_path = store_root / raw_rel
    provenance_rel = f"provenance/{identity.attempt_id}.json"
    provenance_path = store_root / provenance_rel

    raw_sha256 = _write_raw_bytes(raw_path, png)
    dimensions = _image_dimensions(raw_path)
    repository_commit = gc.git_commit(root)

    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "specification_id": specification_id,
        "attempt_id": identity.attempt_id,
        "predecessor_attempt_id": identity.predecessor_attempt_id,
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "prompt_text": prompt_text,
        "prompt_sha256": prompt_sha256,
        "reference_image_sha256": reference_image_sha256,
        "edit_source_sha256": ge.sha256_file(edit_source) if edit_source is not None else None,
        "generated_at": recorded_at,
        "acquiring_agent": acquiring_agent,
        "repository_commit": repository_commit,
        "raw_path": raw_rel,
        "raw_sha256": raw_sha256,
        "media_type": "image/png",
        "dimensions": dimensions,
        "outcome": outcome,
        "rejection_reason": rejection_reason,
    }
    _write_once_json(provenance_path, provenance)

    row = {
        "schema": LEDGER_SCHEMA,
        "attempt_id": identity.attempt_id,
        "specification_id": specification_id,
        "ordinal": identity.ordinal,
        "predecessor_attempt_id": identity.predecessor_attempt_id,
        "recorded_at": recorded_at,
        "acquiring_agent": acquiring_agent,
        "generation_mode": generation_mode,
        "outcome": outcome,
        "rejection_reason": rejection_reason,
        "prompt_sha256": prompt_sha256,
        "raw_path": raw_rel,
        "raw_sha256": raw_sha256,
        "dimensions": dimensions,
        "provenance_path": provenance_rel,
    }
    _append_ledger_row(store_root / "attempts.jsonl", row)
    return row


def load_asset_attempts(store_root: pathlib.Path, specification_id: str) -> list[dict[str, Any]]:
    """Return this specification's Attempts in ordinal order.

    Raises when ordinals are non-contiguous, duplicated, or out of order — a
    ledger that was edited by hand fails to load rather than loading wrong.
    """
    path = store_root / "attempts.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        if doc.get("specification_id") != specification_id:
            continue
        rows.append(doc)
    ordinals = [int(doc.get("ordinal", 0)) for doc in rows]
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise AssetAcquisitionError(
            f"attempts.jsonl ordinals for {specification_id!r} are not dense, "
            f"gap-free, and in order: {ordinals}"
        )
    return rows
