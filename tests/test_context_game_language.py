"""Behavioral proof for CONTEXT.md § Game language vocabulary (#328, #388)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "CONTEXT.md"


def _game_language_section() -> str:
    text = CONTEXT.read_text(encoding="utf-8")
    match = re.search(r"^## Game language\n", text, flags=re.MULTILINE)
    assert match is not None
    start = match.start()
    next_section = re.search(r"^## ", text[start + 1 :], flags=re.MULTILINE)
    end = start + 1 + next_section.start() if next_section else len(text)
    return text[start:end]


def _entry_body(section: str, term: str) -> str:
    match = re.search(
        rf"\*\*{re.escape(term)}\*\*:\n(.*?)(?=\n\*\*[A-Za-z][^*]*\*\*:|\Z)",
        section,
        flags=re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _normalized(body: str) -> str:
    return re.sub(r"\s+", " ", body.strip())


def test_game_language_upgrade_names_three_colony_purchases() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Upgrade")
    assert "Dig Rate Upgrade" in body
    assert "Smelter Upgrade" in body
    assert "Carry Capacity Upgrade" in body
    assert "Singular by design" not in body
    assert "single-type" not in body.lower()


def test_game_language_dig_rate_upgrade_raises_dig_rate() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Dig Rate")
    assert "Dig Rate Upgrade" in body
    assert "the one thing an Upgrade raises" not in body
    assert "visibly faster Dwarf on the Pane" in body


def test_game_language_hardness_is_face_damage_capacity() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Hardness")
    assert "damage capacity" in body
    assert "exponential" in body.lower()
    assert "Advance" in body
    assert "fixed bands" not in body
    assert "number of Swings" not in body
    assert "shaft" not in body.lower()
    assert "_Avoid_: health, HP, durability, toughness" in body


def test_game_language_yield_scales_with_hardness() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Yield")
    assert "Hardness" in body
    assert "scales" in body.lower()
    assert "Constant for the slice" not in body
    assert "_Avoid_: drop, reward, loot, payout" in body


@pytest.mark.parametrize(
    "term,avoid_fragment",
    [
        ("Pick Damage", "attack, power, DPS"),
        ("Load", "stack, unit, batch"),
        ("Bag", "inventory, pack, backpack"),
        ("Carry Capacity", "bag size, storage, limit"),
        ("Haul", "trip, delivery run, fetch"),
        ("Haul Speed", "walk speed, move speed"),
        ("Cart", "minecart (the game word is Cart), depot, dropoff"),
    ],
)
def test_game_language_haul_loop_term_defined(term: str, avoid_fragment: str) -> None:
    section = _game_language_section()
    body = _entry_body(section, term)
    assert body.strip()
    assert "_Avoid_:" in body
    assert avoid_fragment in body


def test_game_language_smelter_throughput_raised_by_upgrade() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Smelter")
    assert "Smelter Upgrade" in body
    assert "fixed for the slice" not in body.lower()
    assert "status on the Colony surface" in body


def test_game_language_sound_off_until_player_enables() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Sound")
    assert "Swing" in body
    assert "Face break" in body
    assert "off until the player enables it" in body
    assert "player preference" in body
    assert "economy state" in body
    assert "_Avoid_:" in body


def test_game_language_pane_control_cluster_names_colony_sound_quit() -> None:
    section = _game_language_section()
    body = _entry_body(section, "Pane control cluster")
    assert "Colony" in body
    assert "Sound" in body
    assert "Quit" in body
    assert "corner group" in body
    assert "_Avoid_:" in body


def test_game_language_crew_is_two_dwarf_cap() -> None:
    section = _game_language_section()
    body = _normalized(_entry_body(section, "Crew"))
    assert "Dwarves the Colony has" in body
    assert "one Miner, one Hauler" in body
    assert "Two at most" in body
    assert "_Avoid_: team, party, roster, squad" in body


def test_game_language_miner_holds_face_and_swings() -> None:
    section = _game_language_section()
    body = _normalized(_entry_body(section, "Miner"))
    assert "holding the Face and Swinging" in body
    assert "never leaves the Face" in body
    assert "drops Ore into the Heap" in body
    assert "stalls when the Heap is full" in body
    assert "_Avoid_: digger, driller" in body


def test_game_language_hauler_moves_heap_to_cart() -> None:
    section = _game_language_section()
    body = _normalized(_entry_body(section, "Hauler"))
    assert "moving Ore from the Heap to the Cart" in body
    assert "fixed pickup cost" in body
    assert "walks a Haul once its Bag is full" in body
    assert "_Avoid_: carrier, porter, runner" in body


def test_game_language_heap_is_face_backpressure() -> None:
    section = _game_language_section()
    body = _normalized(_entry_body(section, "Heap"))
    assert "Ore accumulated at the Face" in body
    assert "counted in Loads" in body
    assert "Carry Capacity" in body
    assert "full Heap stalls the Miner" in body
    assert "second backpressure point" in body
    assert "Smelter" in body
    assert "_Avoid_: pile, stockpile, buffer, queue" in body


def test_game_language_dwarf_entry_spends_miner_reservation() -> None:
    section = _game_language_section()
    body = _normalized(_entry_body(section, "Dwarf"))
    assert "character species in the Crew" in body
    assert "assigned one job — Miner or Hauler" in body
    assert "assets/characters/dwarf/" in body
    assert "east/west facing only" in body
    assert "Miner" in body
    assert "_Avoid_: worker, unit, character" in body
    assert "miner (that is a job" not in body
    assert "A being, not a job" not in body
    assert "only one of them" not in body
