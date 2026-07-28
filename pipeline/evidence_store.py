"""Gate-controls evidence store paths and record IDs (#139).

Owns root resolution, ID formats, and every path in the on-disk evidence store.
Performs no file I/O beyond ``os.environ`` and ``Path`` arithmetic; reading and
writing stay with :mod:`pipeline.gate_evidence`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REVIEW_ORDINALS: tuple[int, ...] = (1, 2)


class EvidenceStoreError(ValueError):
    """Invalid evidence-store path or relative reference."""


def specification_id(motion_class: str, target_gate: str) -> str:
    return f"{motion_class}/{target_gate}"


def promotion_id_for_spec(spec_id: str) -> str:
    return f"promo--{spec_id.replace('/', '--')}"


def attempt_id(spec_id: str, ordinal: int) -> str:
    return f"{spec_id.replace('/', '--')}--{ordinal:03d}"


def measurement_filename(recorded_at: str) -> str:
    return recorded_at.replace(":", "-") + ".json"


@dataclass(frozen=True)
class EvidenceStore:
    repo_root: Path
    root: Path

    @classmethod
    def for_repo(cls, repo_root: Path | None = None) -> EvidenceStore:
        resolved_repo = repo_root or REPO_ROOT
        override = os.environ.get("UNDERLINE_GATE_CONTROLS_ROOT")
        if override:
            store_root = Path(override)
        else:
            store_root = resolved_repo / "gate-controls"
        return cls(repo_root=resolved_repo, root=store_root)

    @classmethod
    def at(cls, root: Path, *, repo_root: Path) -> EvidenceStore:
        return cls(repo_root=repo_root, root=root)

    def manifest(self) -> Path:
        return (self.root / "manifest.json").resolve()

    def acceptance_profiles(self) -> Path:
        return (self.root / "acceptance-profiles.json").resolve()

    def attempts(self) -> Path:
        return (self.root / "attempts.jsonl").resolve()

    def counters(self) -> Path:
        return (self.root / ".attempt-counters.json").resolve()

    def manifest_lock(self) -> Path:
        return (self.root / ".manifest.lock").resolve()

    def raw(self, attempt_id: str) -> Path:
        return (self.root / "raw" / f"{attempt_id}.png").resolve()

    def provenance(self, attempt_id: str) -> Path:
        return (self.root / "provenance" / f"{attempt_id}.json").resolve()

    def report_dir(self, attempt_id: str) -> Path:
        return (self.root / "reports" / attempt_id).resolve()

    def measurement(self, attempt_id: str, recorded_at: str) -> Path:
        return (
            self.report_dir(attempt_id) / measurement_filename(recorded_at)
        ).resolve()

    def review_dir(self, attempt_id: str) -> Path:
        return (self.root / "reviews" / attempt_id).resolve()

    def packet(self, attempt_id: str) -> Path:
        return (self.review_dir(attempt_id) / "packet.json").resolve()

    def composite(self, attempt_id: str) -> Path:
        return (self.review_dir(attempt_id) / "composite.png").resolve()

    def review(self, attempt_id: str, ordinal: int) -> Path:
        return (
            self.review_dir(attempt_id) / f"review--{ordinal:02d}.json"
        ).resolve()

    def review_input(self, attempt_id: str, ordinal: int) -> Path:
        return (
            self.review_dir(attempt_id) / f"review-input--{ordinal:02d}.json"
        ).resolve()

    def verification(self, promotion_id: str) -> Path:
        return (self.root / "verification" / f"{promotion_id}.json").resolve()

    def relative(self, path: Path) -> str:
        absolute = path.resolve()
        store_root = self.root.resolve()
        repo_root = self.repo_root.resolve()
        try:
            absolute.relative_to(store_root)
        except ValueError as exc:
            raise EvidenceStoreError(
                f"path {absolute} escapes evidence store {store_root}"
            ) from exc
        try:
            return absolute.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise EvidenceStoreError(
                f"path {absolute} is outside repository root {repo_root}"
            ) from exc

    def resolve(self, rel: str) -> Path:
        if Path(rel).is_absolute():
            raise EvidenceStoreError(f"absolute path not allowed: {rel!r}")
        candidate = (self.repo_root / rel).resolve()
        store_root = self.root.resolve()
        try:
            candidate.relative_to(store_root)
        except ValueError as exc:
            raise EvidenceStoreError(
                f"path {rel!r} escapes evidence store {store_root}"
            ) from exc
        return candidate


__all__ = [
    "EvidenceStore",
    "EvidenceStoreError",
    "REVIEW_ORDINALS",
    "attempt_id",
    "measurement_filename",
    "promotion_id_for_spec",
    "specification_id",
]
