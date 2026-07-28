"""Canonical JSON serialization and path/hash binding verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

__all__ = [
    "BindingError",
    "manifest_bytes",
    "packet_bytes",
    "self_excluding_digest",
    "verify_binding",
]


class BindingError(ValueError):
    """Fail-closed path/hash binding verification failure."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def packet_bytes(doc: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(doc), sort_keys=True, separators=(",", ":")).encode()


def manifest_bytes(doc: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(doc), indent=2) + "\n").encode()


def self_excluding_digest(doc: Mapping[str, Any], *, field: str) -> str:
    remainder = dict(doc)
    remainder.pop(field, None)
    return hashlib.sha256(packet_bytes(remainder)).hexdigest()


def verify_binding(
    binding: Mapping[str, Any],
    *,
    root: Path,
    label: str,
    path_key: str = "relative_path",
) -> Path:
    relative_path = binding.get(path_key)
    expected_sha = binding.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_sha, str):
        raise BindingError(
            f"{label} binding is invalid",
            reason_code=f"invalid_{label}",
        )
    resolved = (root / relative_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BindingError(
            f"{label} path escapes root",
            reason_code=f"{label}_path_escape",
        ) from exc
    if not resolved.is_file():
        raise BindingError(
            f"missing {label}: {resolved}",
            reason_code=f"missing_{label}",
        )
    actual_sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise BindingError(
            f"{label} hash does not match binding",
            reason_code=f"{label}_hash_mismatch",
        )
    return resolved
