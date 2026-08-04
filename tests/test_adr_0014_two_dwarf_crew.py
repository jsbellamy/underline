"""Behavioral proof for ADR 0014 two-dwarf crew and Heap backpressure (#388)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "adr" / "0014-two-dwarf-crew-and-heap-backpressure.md"
ADR_README = ROOT / "docs" / "adr" / "README.md"


def test_adr_0014_exists_and_is_accepted() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert ADR.is_file()
    for section in (
        "## Status",
        "## Context",
        "## Decision",
        "## Consequences",
        "## Rejected alternatives",
    ):
        assert section in text
    assert "Accepted (2026-08-03)" in text


def test_adr_0014_records_pipeline_and_tuning_formulas() -> None:
    text = ADR.read_text(encoding="utf-8")
    assert "Miner → Heap → Hauler → Cart" in text
    assert "pickupMsPerLoad(n) = 10_000 / (1 + 0.25n)" in text
    assert "haulSpeedFor(n) = 1 + 0.25n" in text
    assert "departs only when its Bag is full" in text


def test_adr_0014_worked_rates_match_contract() -> None:
    text = ADR.read_text(encoding="utf-8")
    for value in (
        "0.100000 Loads/s",
        "0.092593 Loads/s",
        "0.007407 Loads/s",
        "1350 s",
        "0.125000 Loads/s",
        "0.032407",
        "308.6 s",
        "0.113636 Loads/s",
        "0.133929",
    ):
        assert value in text


def test_adr_0014_records_rejected_alternatives_and_known_gap() -> None:
    text = ADR.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    assert "Flat Load cadence with constant Ore per Load" in text
    assert "DROPS_PER_FACE" in text
    assert "oreForDrop" in text
    assert "a Load is worth more on a tougher Face" in text
    assert "HAUL_ROUND_TRIP_MS" in text
    assert "~100s" in text
    assert "HAUL_SPEED_PX_PER_MS" in text
    assert "pane-layout.ts" in text
    assert "Hauler departs on a partial Bag" in text
    assert "dropDamage" in text
    assert "Hardness" in text
    assert "known gap" in normalized.lower()


def test_adr_readme_indexes_0014() -> None:
    text = ADR_README.read_text(encoding="utf-8")
    assert "[0014](0014-two-dwarf-crew-and-heap-backpressure.md)" in text
    assert "Heap backpressure" in text
