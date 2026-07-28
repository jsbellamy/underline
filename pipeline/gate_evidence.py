"""Fail-closed Gate-control evidence loaders and graph validation.

Production consumers for Wave A and the AFK acquisition loop. Validates the
evidence graph under ``gate-controls/`` without mutating any record.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence

from pipeline import canonical

KNOWN_SCHEMAS: dict[str, frozenset[str]] = {
    "manifest": frozenset({"gate-control-manifest/0"}),
    "attempt": frozenset({"gate-control-acquisition/0"}),
    "acceptance_profile": frozenset({"acceptance-profile-index/0"}),
    "measurement": frozenset(
        {"gate-control-measurement/0", "gate-control-measurement/1"}
    ),
    "provenance": frozenset({"gate-control-provenance/0"}),
    "review": frozenset({"gate-review-audit/0"}),
    "verification": frozenset({"gate-control-verification/0"}),
    "packet": frozenset({"gate-review-packet/0"}),
}


class EvidenceError(ValueError):
    """Fail-closed validation failure for Gate-control evidence."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fingerprint_tree(root: Path) -> dict[str, str]:
    """Relative-path → SHA-256 map for every regular file under ``root``."""
    if not root.exists():
        return {}
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = sha256_file(path)
    return out


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceError(f"missing required file: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"expected object at {path}")
    return data


def require_schema(doc: Mapping[str, Any], allowed: Iterable[str], *, where: str) -> str:
    schema = doc.get("schema")
    if not isinstance(schema, str):
        raise EvidenceError(f"missing schema at {where}")
    allowed_set = frozenset(allowed)
    if schema not in allowed_set:
        raise EvidenceError(f"unknown schema {schema!r} at {where}")
    return schema


def require_str(doc: Mapping[str, Any], field: str, *, where: str) -> str:
    value = doc.get(field)
    if not isinstance(value, str) or value == "":
        raise EvidenceError(f"missing required field {field!r} at {where}")
    return value


def _resolve(root: Path, rel: str | None) -> Path | None:
    if rel is None:
        return None
    path = Path(rel)
    if path.is_absolute():
        return path
    return root / path


@dataclass(frozen=True)
class Specification:
    id: str
    motion_class: str
    target_gate: str
    active_promotion: str | None


@dataclass(frozen=True)
class Promotion:
    id: str
    specification_id: str
    attempt_id: str
    measurement_path: str
    status: str
    recorded_at: str
    note: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Manifest:
    schema: str
    specifications: tuple[Specification, ...]
    promotions: tuple[Promotion, ...]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Attempt:
    schema: str
    attempt_id: str
    specification_id: str
    ordinal: int
    artifact_state: str
    isolation: str
    measurement_path: str | None
    provenance_path: str | None
    composite_path: str | None
    raw_sha256: str | None
    recorded_at: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class MeasurementRun:
    schema: str
    path: Path
    motion_class: str
    target_gate: str
    raw_sha256: str
    isolation: str
    caveats: tuple[str, ...]
    gates: Mapping[str, Any]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class Provenance:
    schema: str
    path: Path
    specification_id: str
    attempt_id: str
    raw_path: str
    raw_sha256: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class GateProfile:
    status: str
    budget: float | None
    hard_fail: float | None
    active_promotion: str | None
    control_attempt: str | None
    evidence_attempt: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class AcceptanceProfiles:
    schema: str
    profiles: Mapping[str, Mapping[str, GateProfile]]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ReviewRecord:
    schema: str
    path: Path
    review_id: str
    attempt_id: str | None
    gate: str | None
    verdict: str | None
    packet_sha256: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class VerificationRecord:
    schema: str
    path: Path
    promotion_id: str
    attempt_id: str | None
    status: str | None
    manifest_sha256: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class EvidenceGraph:
    root: Path
    gc_root: Path
    manifest: Manifest
    attempts: Mapping[str, Attempt]
    promotions: Mapping[str, Promotion]
    specifications: Mapping[str, Specification]
    profiles: AcceptanceProfiles
    measurements: Mapping[str, MeasurementRun]
    provenances: Mapping[str, Provenance]
    reviews: Mapping[str, ReviewRecord]
    verifications: Mapping[str, VerificationRecord]


def load_manifest(path: Path) -> Manifest:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["manifest"], where=str(path))
    specs: list[Specification] = []
    seen_spec: set[str] = set()
    for item in doc.get("specifications", []):
        if not isinstance(item, dict):
            raise EvidenceError(f"invalid specification entry in {path}")
        sid = item.get("id")
        if not isinstance(sid, str):
            raise EvidenceError(f"specification missing id in {path}")
        if sid in seen_spec:
            raise EvidenceError(f"duplicate specification id {sid!r}")
        seen_spec.add(sid)
        specs.append(
            Specification(
                id=sid,
                motion_class=require_str(item, "motion_class", where=str(path)),
                target_gate=require_str(item, "target_gate", where=str(path)),
                active_promotion=(
                    require_str(item, "active_promotion", where=str(path))
                    if item.get("active_promotion") is not None
                    else None
                ),
            )
        )
    promotions: list[Promotion] = []
    seen_promo: set[str] = set()
    for item in doc.get("promotions", []):
        if not isinstance(item, dict):
            raise EvidenceError(f"invalid promotion entry in {path}")
        pid = item.get("id")
        if not isinstance(pid, str) or pid == "":
            raise EvidenceError(f"promotion missing id in {path}")
        if pid in seen_promo:
            raise EvidenceError(f"duplicate promotion id {pid!r}")
        seen_promo.add(pid)
        promotions.append(
            Promotion(
                id=pid,
                specification_id=require_str(
                    item, "specification_id", where=str(path)
                ),
                attempt_id=require_str(item, "attempt_id", where=str(path)),
                measurement_path=require_str(
                    item, "measurement_path", where=str(path)
                ),
                status=require_str(item, "status", where=str(path)),
                recorded_at=require_str(item, "recorded_at", where=str(path)),
                note=item.get("note") if isinstance(item.get("note"), str) else None,
                raw=item,
            )
        )
    return Manifest(
        schema=schema,
        specifications=tuple(specs),
        promotions=tuple(promotions),
        raw=doc,
    )


def load_attempts(path: Path) -> tuple[Attempt, ...]:
    if not path.is_file():
        raise EvidenceError(f"missing required file: {path}")
    attempts: list[Attempt] = []
    seen: set[str] = set()
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(doc, dict):
            raise EvidenceError(f"expected object at {path}:{line_no}")
        schema = require_schema(doc, KNOWN_SCHEMAS["attempt"], where=f"{path}:{line_no}")
        attempt_id = doc.get("attempt_id")
        if not isinstance(attempt_id, str):
            raise EvidenceError(f"attempt missing attempt_id at {path}:{line_no}")
        if attempt_id in seen:
            raise EvidenceError(f"duplicate attempt_id {attempt_id!r}")
        seen.add(attempt_id)
        where = f"{path}:{line_no}"
        attempts.append(
            Attempt(
                schema=schema,
                attempt_id=attempt_id,
                specification_id=require_str(doc, "specification_id", where=where),
                ordinal=int(doc.get("ordinal", 0)),
                artifact_state=require_str(doc, "artifact_state", where=where),
                isolation=require_str(doc, "isolation", where=where),
                measurement_path=(
                    require_str(doc, "measurement_path", where=where)
                    if doc.get("measurement_path") is not None
                    else None
                ),
                provenance_path=(
                    require_str(doc, "provenance_path", where=where)
                    if doc.get("provenance_path") is not None
                    else None
                ),
                composite_path=(
                    require_str(doc, "composite_path", where=where)
                    if doc.get("composite_path") is not None
                    else None
                ),
                raw_sha256=(
                    require_str(doc, "raw_sha256", where=where)
                    if doc.get("raw_sha256") is not None
                    else None
                ),
                recorded_at=require_str(doc, "recorded_at", where=where),
                raw=doc,
            )
        )
    return tuple(attempts)


def load_acceptance_profiles(path: Path) -> AcceptanceProfiles:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["acceptance_profile"], where=str(path))
    profiles: dict[str, dict[str, GateProfile]] = {}
    for motion_class, profile in (doc.get("profiles") or {}).items():
        if not isinstance(profile, dict):
            raise EvidenceError(f"invalid profile {motion_class!r} in {path}")
        gates: dict[str, GateProfile] = {}
        for gate, entry in (profile.get("gates") or {}).items():
            if not isinstance(entry, dict):
                raise EvidenceError(f"invalid gate profile {motion_class}/{gate}")
            budget = entry.get("budget")
            hard_fail = entry.get("hard_fail")
            where = f"{path}:{motion_class}/{gate}"
            gates[gate] = GateProfile(
                status=require_str(entry, "status", where=where),
                budget=float(budget) if isinstance(budget, (int, float)) else None,
                hard_fail=(
                    float(hard_fail) if isinstance(hard_fail, (int, float)) else None
                ),
                active_promotion=(
                    require_str(entry, "active_promotion", where=where)
                    if entry.get("active_promotion") is not None
                    else None
                ),
                control_attempt=(
                    require_str(entry, "control_attempt", where=where)
                    if entry.get("control_attempt") is not None
                    else None
                ),
                evidence_attempt=(
                    require_str(entry, "evidence_attempt", where=where)
                    if entry.get("evidence_attempt") is not None
                    else None
                ),
                raw=entry,
            )
        profiles[str(motion_class)] = gates
    return AcceptanceProfiles(schema=schema, profiles=profiles, raw=doc)


def load_measurement(path: Path) -> MeasurementRun:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["measurement"], where=str(path))
    raw_sha = doc.get("raw_sha256")
    if not isinstance(raw_sha, str):
        raise EvidenceError(f"measurement missing raw_sha256 at {path}")
    caveats = tuple(str(c) for c in (doc.get("caveats") or []))
    gates = doc.get("gates") or {}
    if not isinstance(gates, dict):
        raise EvidenceError(f"measurement gates must be an object at {path}")
    where = str(path)
    return MeasurementRun(
        schema=schema,
        path=path,
        motion_class=require_str(doc, "motion_class", where=where),
        target_gate=require_str(doc, "target_gate", where=where),
        raw_sha256=raw_sha,
        isolation=require_str(doc, "isolation", where=where),
        caveats=caveats,
        gates=gates,
        raw=doc,
    )


def load_provenance(path: Path) -> Provenance:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["provenance"], where=str(path))
    raw_sha = doc.get("raw_sha256")
    if not isinstance(raw_sha, str) or raw_sha == "":
        raise EvidenceError(f"provenance missing raw_sha256 at {path}")
    where = str(path)
    return Provenance(
        schema=schema,
        path=path,
        specification_id=require_str(doc, "specification_id", where=where),
        attempt_id=require_str(doc, "attempt_id", where=where),
        raw_path=require_str(doc, "raw_path", where=where),
        raw_sha256=raw_sha,
        raw=doc,
    )


def load_review(path: Path) -> ReviewRecord:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["review"], where=str(path))
    return ReviewRecord(
        schema=schema,
        path=path,
        review_id=str(doc.get("review_id") or path.stem),
        attempt_id=str(doc["attempt_id"]) if doc.get("attempt_id") is not None else None,
        gate=str(doc["gate"]) if doc.get("gate") is not None else None,
        verdict=str(doc["verdict"]) if doc.get("verdict") is not None else None,
        packet_sha256=(
            str(doc["packet_sha256"]) if doc.get("packet_sha256") is not None else None
        ),
        raw=doc,
    )


def load_verification(path: Path) -> VerificationRecord:
    doc = load_json(path)
    schema = require_schema(doc, KNOWN_SCHEMAS["verification"], where=str(path))
    return VerificationRecord(
        schema=schema,
        path=path,
        promotion_id=str(doc.get("promotion_id") or path.stem),
        attempt_id=str(doc["attempt_id"]) if doc.get("attempt_id") is not None else None,
        status=str(doc["status"]) if doc.get("status") is not None else None,
        manifest_sha256=(
            str(doc["manifest_sha256"])
            if doc.get("manifest_sha256") is not None
            else None
        ),
        raw=doc,
    )


def write_json_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    """Append-only helper: refuse to overwrite an existing evidence record."""
    if path.exists():
        raise EvidenceError(f"refusing to mutate existing evidence record: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


@contextmanager
def repository_lock(lock_path: Path) -> Iterator[None]:
    """Exclusive repository-local lock for append-only ledgers and ID allocation."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_attempt_record(doc: Mapping[str, Any], *, where: str = "attempt record") -> None:
    require_schema(doc, KNOWN_SCHEMAS["attempt"], where=where)
    require_str(doc, "attempt_id", where=where)
    require_str(doc, "specification_id", where=where)
    require_str(doc, "artifact_state", where=where)
    require_str(doc, "isolation", where=where)
    require_str(doc, "recorded_at", where=where)
    if doc.get("artifact_state") not in {"retained", "discarded"}:
        raise EvidenceError(f"invalid artifact_state at {where}")


def append_attempt_record(path: Path, doc: Mapping[str, Any]) -> None:
    """Append one validated Attempt ledger row without interleaving partial JSON."""
    validate_attempt_record(doc, where=str(path))
    line = json.dumps(dict(doc), sort_keys=True)
    json.loads(line)
    attempt_id = str(doc["attempt_id"])
    lock_path = path.parent / ".attempts.lock"
    with repository_lock(lock_path):
        if path.is_file():
            for line_no, existing_line in enumerate(path.read_text().splitlines(), start=1):
                if not existing_line.strip():
                    continue
                existing = json.loads(existing_line)
                if existing.get("attempt_id") == attempt_id:
                    raise EvidenceError(f"duplicate attempt_id {attempt_id!r} at {path}:{line_no}")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def validate_provenance_record(doc: Mapping[str, Any], *, where: str = "provenance") -> None:
    require_schema(doc, KNOWN_SCHEMAS["provenance"], where=where)
    require_str(doc, "specification_id", where=where)
    require_str(doc, "attempt_id", where=where)
    require_str(doc, "generator", where=where)
    require_str(doc, "prompt_text", where=where)
    require_str(doc, "prompt_sha256", where=where)
    require_str(doc, "generated_at", where=where)
    require_str(doc, "acquiring_agent", where=where)
    require_str(doc, "repository_commit", where=where)
    require_str(doc, "raw_path", where=where)
    require_str(doc, "raw_sha256", where=where)
    require_str(doc, "media_type", where=where)
    if doc.get("generator") != "cursor-image-gen":
        raise EvidenceError(f"unsupported generator at {where}")


def write_provenance_record(path: Path, doc: Mapping[str, Any]) -> None:
    validate_provenance_record(doc, where=str(path))
    write_json_immutable(path, doc)


def write_manifest_document(path: Path, doc: Mapping[str, Any]) -> None:
    require_schema(doc, KNOWN_SCHEMAS["manifest"], where=str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical.manifest_bytes(doc))


def mutate_manifest_document(
    path: Path,
    mutator: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Read-modify-write one manifest under an exclusive repository lock."""
    lock_path = path.parent / ".manifest.lock"
    with repository_lock(lock_path):
        if path.is_file():
            doc = load_json(path)
        else:
            doc = {
                "schema": "gate-control-manifest/0",
                "specifications": [],
                "promotions": [],
            }
        updated = mutator(doc)
        write_manifest_document(path, updated)
        return updated


def _gate_controls_root(root: Path) -> Path:
    gc = root / "gate-controls"
    if not gc.is_dir():
        raise EvidenceError(f"missing required file: {gc}")
    return gc


def _validate_promotion_subgraph(
    *,
    root: Path,
    promo: Promotion,
    attempt: Attempt,
    spec: Specification,
    measurements: dict[str, MeasurementRun],
    provenances: dict[str, Provenance],
) -> None:
    """Fail-closed identity/hash/artifact checks for one Promotion candidate."""
    if promo.specification_id != attempt.specification_id:
        raise EvidenceError(
            f"identity mismatch: promotion {promo.id} specification_id "
            f"{promo.specification_id!r} != attempt {attempt.specification_id!r}"
        )
    if attempt.artifact_state == "discarded":
        raise EvidenceError(
            f"discarded promotion candidate: attempt {attempt.attempt_id} "
            f"cannot back promotion {promo.id}"
        )

    measurement_path = _resolve(root, promo.measurement_path)
    if measurement_path is None or not measurement_path.is_file():
        raise EvidenceError(
            f"missing required file: {promo.measurement_path} "
            f"(promotion {promo.id})"
        )
    measurement = load_measurement(measurement_path)
    if measurement.target_gate != spec.target_gate:
        raise EvidenceError(
            f"identity mismatch: measurement target_gate "
            f"{measurement.target_gate!r} != specification "
            f"{spec.target_gate!r} for promotion {promo.id}"
        )
    if measurement.motion_class != spec.motion_class:
        raise EvidenceError(
            f"identity mismatch: measurement motion_class "
            f"{measurement.motion_class!r} != specification "
            f"{spec.motion_class!r} for promotion {promo.id}"
        )
    measurements[attempt.attempt_id] = measurement

    if attempt.provenance_path is None:
        raise EvidenceError(
            f"missing required file: provenance for promoted attempt "
            f"{attempt.attempt_id}"
        )
    provenance_path = _resolve(root, attempt.provenance_path)
    if provenance_path is None or not provenance_path.is_file():
        raise EvidenceError(f"missing required file: {attempt.provenance_path}")
    provenance = load_provenance(provenance_path)
    if provenance.attempt_id != attempt.attempt_id:
        raise EvidenceError(
            f"identity mismatch: provenance attempt_id "
            f"{provenance.attempt_id!r} != {attempt.attempt_id!r}"
        )
    if provenance.specification_id != attempt.specification_id:
        raise EvidenceError(
            f"identity mismatch: provenance specification_id "
            f"{provenance.specification_id!r} != {attempt.specification_id!r}"
        )
    provenances[attempt.attempt_id] = provenance

    raw_path = _resolve(root, provenance.raw_path)
    if raw_path is None or not raw_path.is_file():
        raise EvidenceError(f"missing required file: {provenance.raw_path}")
    actual = sha256_file(raw_path)
    for label, expected in (
        ("provenance", provenance.raw_sha256),
        ("measurement", measurement.raw_sha256),
        ("attempt", attempt.raw_sha256),
    ):
        if expected is None:
            raise EvidenceError(
                f"missing raw_sha256 on {label} for attempt {attempt.attempt_id}"
            )
        if expected != actual:
            raise EvidenceError(
                f"SHA-256 mismatch: {label} hash {expected} != raw {actual} "
                f"for attempt {attempt.attempt_id}"
            )


def validate_evidence_graph(
    root: Path,
    *,
    promotion_ids: Sequence[str] | None = None,
) -> EvidenceGraph:
    """Load and fail-closed-validate the evidence graph under ``root/gate-controls``.

    Promotion candidates are always checked for retained raw bytes and SHA-256
    identity. Historical non-promoted Attempts are schema/reference-checked when
    their declared Measurement/provenance files exist; missing discarded raws do
    not fail the graph. Pass ``promotion_ids`` to deep-validate only those
    Promotions (Wave A named-Promotion reviews).
    """
    root = root.resolve()
    gc = _gate_controls_root(root)
    manifest = load_manifest(gc / "manifest.json")
    attempts_list = load_attempts(gc / "attempts.jsonl")
    profiles = load_acceptance_profiles(gc / "acceptance-profiles.json")

    attempts = {a.attempt_id: a for a in attempts_list}
    specifications = {s.id: s for s in manifest.specifications}
    promotions = {p.id: p for p in manifest.promotions}

    focus: set[str] | None = None
    if promotion_ids is not None:
        focus = set(promotion_ids)
        for pid in focus:
            if pid not in promotions:
                raise EvidenceError(f"unknown promotion_id {pid!r}")

    for spec in manifest.specifications:
        if spec.active_promotion is None:
            continue
        promo = promotions.get(spec.active_promotion)
        if promo is None:
            raise EvidenceError(
                f"broken reference: specification {spec.id} active_promotion "
                f"{spec.active_promotion!r}"
            )
        if promo.specification_id != spec.id:
            raise EvidenceError(
                f"identity mismatch: promotion {promo.id} specification_id "
                f"{promo.specification_id!r} != specification {spec.id!r}"
            )

    measurements: dict[str, MeasurementRun] = {}
    provenances: dict[str, Provenance] = {}

    for promo in manifest.promotions:
        if focus is not None and promo.id not in focus:
            continue
        attempt = attempts.get(promo.attempt_id)
        if attempt is None:
            raise EvidenceError(
                f"identity mismatch: promotion {promo.id} references missing "
                f"attempt {promo.attempt_id!r}"
            )
        spec = specifications.get(promo.specification_id)
        if spec is None:
            raise EvidenceError(
                f"broken reference: promotion {promo.id} specification "
                f"{promo.specification_id!r}"
            )
        _validate_promotion_subgraph(
            root=root,
            promo=promo,
            attempt=attempt,
            spec=spec,
            measurements=measurements,
            provenances=provenances,
        )

    # Schema-load non-promoted Attempt evidence when files exist. Raw bytes are
    # required only for Promotion candidates (above); discarded PNGs are expected
    # to be absent for historical Attempts.
    for attempt in attempts.values():
        if attempt.attempt_id in measurements:
            continue
        if attempt.measurement_path:
            mpath = _resolve(root, attempt.measurement_path)
            if mpath is not None and mpath.is_file():
                measurements[attempt.attempt_id] = load_measurement(mpath)
            elif focus is None:
                raise EvidenceError(f"missing required file: {attempt.measurement_path}")
        if attempt.provenance_path:
            ppath = _resolve(root, attempt.provenance_path)
            if ppath is not None and ppath.is_file():
                provenance = load_provenance(ppath)
                provenances[attempt.attempt_id] = provenance
                raw_path = _resolve(root, provenance.raw_path)
                if raw_path is not None and raw_path.is_file():
                    actual = sha256_file(raw_path)
                    if provenance.raw_sha256 != actual:
                        raise EvidenceError(
                            f"SHA-256 mismatch: provenance hash "
                            f"{provenance.raw_sha256} != raw {actual} "
                            f"for attempt {attempt.attempt_id}"
                        )
                    measurement = measurements.get(attempt.attempt_id)
                    if measurement is not None and measurement.raw_sha256 != actual:
                        raise EvidenceError(
                            f"SHA-256 mismatch: measurement hash "
                            f"{measurement.raw_sha256} != raw {actual} "
                            f"for attempt {attempt.attempt_id}"
                        )
                    if attempt.raw_sha256 is not None and attempt.raw_sha256 != actual:
                        raise EvidenceError(
                            f"SHA-256 mismatch: attempt hash {attempt.raw_sha256} "
                            f"!= raw {actual} for attempt {attempt.attempt_id}"
                        )
            elif focus is None and attempt.artifact_state == "retained":
                raise EvidenceError(f"missing required file: {attempt.provenance_path}")

    reviews: dict[str, ReviewRecord] = {}
    reviews_root = gc / "reviews"
    if reviews_root.is_dir():
        # Packet manifests (packet.json) share the review directory; only audit
        # records use the review--*.json naming from the §10 / Wave A layout.
        for path in sorted(reviews_root.rglob("review--*.json")):
            record = load_review(path)
            key = str(path.relative_to(gc))
            reviews[key] = record

    verifications: dict[str, VerificationRecord] = {}
    verification_root = gc / "verification"
    if verification_root.is_dir():
        for path in sorted(verification_root.glob("*.json")):
            record = load_verification(path)
            verifications[record.promotion_id] = record

    return EvidenceGraph(
        root=root,
        gc_root=gc,
        manifest=manifest,
        attempts=attempts,
        promotions=promotions,
        specifications=specifications,
        profiles=profiles,
        measurements=measurements,
        provenances=provenances,
        reviews=reviews,
        verifications=verifications,
    )
