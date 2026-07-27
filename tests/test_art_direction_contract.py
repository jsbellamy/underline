"""Machine proof for the first-room Master Palette contract (#103)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"

HEX_COLOR = re.compile(r"^#[0-9A-F]{6}$")
MAGENTA_KEY = "#FF00FF"

EXPECTED_UNIQUE_COLORS = [
    "#111018",
    "#1D1720",
    "#2B2230",
    "#3B2F3A",
    "#4A3B48",
    "#62515D",
    "#806A73",
    "#A58C91",
    "#3B221B",
    "#623722",
    "#935631",
    "#C87B43",
    "#6C3D31",
    "#A45F46",
    "#DA8A63",
    "#F3BC82",
    "#193A32",
    "#285B43",
    "#42805A",
    "#78A663",
    "#1D3B50",
    "#2F6075",
    "#4E8DA0",
    "#8FC4C5",
    "#783A18",
    "#BE6222",
    "#F0A33A",
    "#FFD66B",
    "#123A47",
    "#176873",
    "#27A6A3",
    "#72E2D2",
]

REQUIRED_ROLE_GROUPS = (
    "dark/outline",
    "stone",
    "earth/leather/beard",
    "skin",
    "green cloth",
    "blue metal",
    "amber emission",
    "cyan crystal",
)


def _load_palette() -> dict:
    return json.loads(PALETTE_PATH.read_text())


def _collect_colors(palette: dict) -> list[str]:
    colors: list[str] = []
    for group in palette["role_groups"]:
        for color in group["colors"]:
            colors.append(color.upper())
    return colors


def test_palette_file_exists() -> None:
    assert PALETTE_PATH.is_file()


def test_palette_schema_and_id() -> None:
    palette = _load_palette()
    assert palette["schema"] == "master-palette/0"
    assert palette["id"] == "first-room"


def test_palette_has_exactly_thirty_two_unique_colors() -> None:
    palette = _load_palette()
    colors = _collect_colors(palette)
    assert len(colors) == 32
    assert len(set(colors)) == 32
    for color in colors:
        assert HEX_COLOR.match(color)


def test_palette_matches_pinned_hex_values() -> None:
    palette = _load_palette()
    colors = sorted(_collect_colors(palette))
    expected = sorted(c.upper() for c in EXPECTED_UNIQUE_COLORS)
    assert colors == expected


def test_palette_excludes_magenta_transport_key() -> None:
    palette = _load_palette()
    colors = _collect_colors(palette)
    assert MAGENTA_KEY not in colors


def test_palette_has_required_role_groups() -> None:
    palette = _load_palette()
    labels = [group["label"] for group in palette["role_groups"]]
    assert labels == list(REQUIRED_ROLE_GROUPS)


def test_each_role_group_has_four_colors() -> None:
    palette = _load_palette()
    for group in palette["role_groups"]:
        assert len(group["colors"]) == 4
