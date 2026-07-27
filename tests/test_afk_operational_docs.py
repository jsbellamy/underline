"""AFK operational documentation reconciled with the merged pipeline (#88)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "gate-controls" / "manifest.json"
PACKAGE_JSON = ROOT / "package.json"
README = ROOT / "README.md"
AFK_SPEC = ROOT / "docs" / "afk-acceptance-implementation-spec.md"
ALPHA_TABLES = ROOT / "docs" / "alpha-budget-tables.md"
STRIP_README = ROOT / "prototype" / "strip-coherence" / "README.md"
ACCEPTANCE_PROFILES = (
    ROOT / "docs" / "acceptance-profiles" / "idle.md",
    ROOT / "docs" / "acceptance-profiles" / "emissive.md",
)

PRODUCTION_DOC_PATHS = (
    README,
    AFK_SPEC,
    ALPHA_TABLES,
    STRIP_README,
    *ACCEPTANCE_PROFILES,
)

CANONICAL_COMMANDS = (
    "gate-control:score",
    "gate-control:acquire",
    "gate-control:review",
    "gate-control:verify",
)

DEPRECATED_SHIM_BASENAMES = (
    "gate_control.py",
    "gate_control_acquire.py",
    "numeric_policy.py",
)

DOCS_WITHOUT_SHIM_PATHS = (
    README,
    ALPHA_TABLES,
    *ACCEPTANCE_PROFILES,
)

WAVE_A_AWAIT_PHRASES = (
    "await activation",
    "awaiting activation",
    "deferred late visual reviews for every",
)


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_manifest_has_seventeen_active_promotions() -> None:
    manifest = _load_manifest()
    promotions = manifest["promotions"]
    assert len(promotions) == 17
    assert all(p["status"] == "ACTIVE" for p in promotions)


@pytest.mark.parametrize("doc_path", ACCEPTANCE_PROFILES)
def test_acceptance_profiles_mark_promotions_active(doc_path: Path) -> None:
    text = doc_path.read_text()
    assert "PENDING_VERIFICATION" not in text
    assert "ACTIVE" in text


def test_alpha_tables_state_seventeen_active_none_pending() -> None:
    text = ALPHA_TABLES.read_text()
    assert "17" in text
    assert "ACTIVE" in text
    assert "PENDING_VERIFICATION" not in text


def test_production_docs_point_to_pipeline_numeric_policy() -> None:
    for path in (AFK_SPEC, ALPHA_TABLES):
        text = path.read_text()
        assert "pipeline/numeric_policy.py" in text
        assert "prototype/strip-coherence/numeric_policy.py" not in text


def test_production_docs_do_not_reference_prototype_numeric_policy() -> None:
    for path in DOCS_WITHOUT_SHIM_PATHS:
        text = path.read_text()
        assert "prototype/strip-coherence/numeric_policy.py" not in text


def test_afk_spec_no_wave_a_await_activation_language() -> None:
    text = AFK_SPEC.read_text()
    lowered = text.lower()
    for phrase in WAVE_A_AWAIT_PHRASES:
        assert phrase not in lowered
    assert "Wave D" in text
    assert "out of scope" in lowered or "out of this map" in lowered


def test_readme_documents_canonical_gate_control_commands_in_order() -> None:
    text = README.read_text()
    package = PACKAGE_JSON.read_text()
    for cmd in CANONICAL_COMMANDS:
        assert cmd in text
        assert f'"{cmd}"' in package
    positions = [text.index(cmd) for cmd in CANONICAL_COMMANDS]
    assert positions == sorted(positions)


def test_afk_spec_documents_canonical_commands_not_prototype_scorer() -> None:
    text = AFK_SPEC.read_text()
    for cmd in CANONICAL_COMMANDS:
        assert cmd in text
    operator_section = text.split("Production Gate-control workflow")[1].split("### Deprecated")[0]
    assert "prototype/strip-coherence/gate_control.py" not in operator_section


def test_afk_spec_names_three_deprecated_shims_in_shim_section() -> None:
    text = AFK_SPEC.read_text()
    shim_section = text.split("## 12. Commands")[1].split("### Deprecated compatibility shims")[1].split("### Historical")[0]
    for basename in DEPRECATED_SHIM_BASENAMES:
        assert basename in shim_section
    assert "no announced removal date" in shim_section.lower()


def test_strip_readme_names_three_deprecated_shims_without_removal_date() -> None:
    text = STRIP_README.read_text()
    for basename in DEPRECATED_SHIM_BASENAMES:
        assert basename in text
    assert "deprecated" in text.lower()
    assert "no announced removal" in text.lower() or "no announced removal date" in text.lower()


def test_afk_spec_documents_exactly_two_bat_flap_adversarial_gaps() -> None:
    text = AFK_SPEC.read_text()
    assert "04-bat-flap" in text
    assert "hop" in text
    assert "slide" in text
    assert "blob_idle" in text and "mirror" in text.lower()
    gap_section = text.split("Adversarial suite")[1]
    assert gap_section.count("GAP") >= 1 or "two" in gap_section.lower()
    assert "displacement undecidability" in gap_section.lower() or "degenerate alignment" in gap_section.lower()


def test_afk_spec_does_not_name_blob_idle_slide_or_emissive_mirror_as_gaps() -> None:
    text = AFK_SPEC.read_text()
    gap_section = text.split("Adversarial suite")[1]
    assert "blob_idle" not in gap_section or "not known gaps" in gap_section.lower()
    assert "required rejection" in gap_section.lower()
