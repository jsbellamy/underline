"""Canonical JSON serialization and hash binding (issue #136)."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from pipeline import canonical

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PACKETS = sorted((ROOT / "gate-controls" / "reviews").glob("*/packet.json"))
MANIFEST_PATH = ROOT / "gate-controls" / "manifest.json"


@pytest.mark.parametrize("packet_path", REVIEW_PACKETS, ids=lambda p: p.parent.name)
def test_packet_digest_matches_committed_packet_sha256(packet_path: Path) -> None:
    doc = json.loads(packet_path.read_text(encoding="utf-8"))
    assert canonical.self_excluding_digest(doc, field="packet_sha256") == doc[
        "packet_sha256"
    ]


def test_manifest_bytes_matches_committed_manifest() -> None:
    doc = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert canonical.manifest_bytes(doc) == MANIFEST_PATH.read_bytes()


def test_self_excluding_digest_round_trip() -> None:
    payload = {"schema": "test/0", "value": 42, "nested": {"a": 1}}
    digest = canonical.self_excluding_digest(payload, field="packet_sha256")
    bound = {**payload, "packet_sha256": digest}
    assert canonical.self_excluding_digest(bound, field="packet_sha256") == digest


def test_packet_bytes_matches_compact_sorted_form() -> None:
    doc = {"z": 1, "a": {"b": 2}}
    expected = json.dumps(dict(doc), sort_keys=True, separators=(",", ":")).encode()
    assert canonical.packet_bytes(doc) == expected


def test_canonical_value_round_trip() -> None:
    payload = {"z": 1, "a": {"b": 2}, "tags": ["x", "y"]}
    expected = json.loads(json.dumps(payload, sort_keys=True))
    assert canonical.canonical_value(payload) == expected


def test_canonical_module_does_not_import_gate_evidence() -> None:
    source = inspect.getsource(canonical)
    assert "gate_evidence" not in source


@pytest.fixture
def bound_artifact(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "root"
    root.mkdir()
    data_dir = root / "data"
    data_dir.mkdir()
    file_path = data_dir / "artifact.bin"
    content = b"bound-bytes"
    file_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    binding = {"relative_path": "data/artifact.bin", "sha256": digest}
    return root, binding, file_path


def test_verify_binding_returns_resolved_path(
    bound_artifact: tuple[Path, dict[str, str], Path],
) -> None:
    root, binding, file_path = bound_artifact
    resolved = canonical.verify_binding(binding, root=root, label="artifact")
    assert resolved == file_path.resolve()


def test_verify_binding_honours_custom_path_key(
    bound_artifact: tuple[Path, dict[str, str], Path],
) -> None:
    root, binding, file_path = bound_artifact
    alt_binding = {"path": binding["relative_path"], "sha256": binding["sha256"]}
    resolved = canonical.verify_binding(
        alt_binding, root=root, label="artifact", path_key="path"
    )
    assert resolved == file_path.resolve()


@pytest.mark.parametrize(
    ("binding", "label"),
    [
        ({}, "artifact"),
        ({"relative_path": "data/artifact.bin"}, "artifact"),
        ({"sha256": "a" * 64}, "artifact"),
        ({"relative_path": 1, "sha256": "a" * 64}, "artifact"),
        ({"relative_path": "data/artifact.bin", "sha256": 123}, "artifact"),
    ],
)
def test_verify_binding_invalid_binding(
    binding: dict[str, object], label: str, tmp_path: Path
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(canonical.BindingError) as exc:
        canonical.verify_binding(binding, root=root, label=label)
    assert exc.value.reason_code == f"invalid_{label}"


def test_verify_binding_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"escaped")
    digest = hashlib.sha256(b"escaped").hexdigest()
    binding = {"relative_path": "../outside.txt", "sha256": digest}
    with pytest.raises(canonical.BindingError) as exc:
        canonical.verify_binding(binding, root=root, label="artifact")
    assert exc.value.reason_code == "artifact_path_escape"


def test_verify_binding_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    binding = {
        "relative_path": "missing/artifact.bin",
        "sha256": "a" * 64,
    }
    with pytest.raises(canonical.BindingError) as exc:
        canonical.verify_binding(binding, root=root, label="artifact")
    assert exc.value.reason_code == "missing_artifact"


def test_verify_binding_hash_mismatch(
    bound_artifact: tuple[Path, dict[str, str], Path],
) -> None:
    root, binding, _file_path = bound_artifact
    tampered = dict(binding)
    tampered["sha256"] = "b" * 64
    with pytest.raises(canonical.BindingError) as exc:
        canonical.verify_binding(tampered, root=root, label="artifact")
    assert exc.value.reason_code == "artifact_hash_mismatch"
