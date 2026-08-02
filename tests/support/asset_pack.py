"""Asset-pack fixture builders shared across pipeline.asset_pack tests (issue #253)."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from pipeline.asset_pack import PACK_SCHEMA, TERRACED_SHAFT_PREVIEW_SCENE
from pipeline.gate_evidence import sha256_file

ROOT = Path(__file__).resolve().parents[2]
PALETTE_PATH = ROOT / "assets" / "palettes" / "first-room.json"
PALETTE_SHA = sha256_file(PALETTE_PATH)

STONE = (74, 59, 72)
STONE_LIGHT = (98, 81, 93)
STONE_MID = (128, 106, 115)
CYAN = (39, 166, 163)
DWARF = (66, 128, 90)
LANTERN = (240, 163, 58)


def _path_prefix(root: Path) -> str:
    try:
        rel = root.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return ""
    return f"{rel}/" if rel else ""


def _rel(root: Path, suffix: str) -> str:
    return f"{_path_prefix(root)}{suffix}"


def _repo_file(root: Path, rel_path: str) -> Path:
    if _path_prefix(root):
        return ROOT / rel_path
    return root / rel_path


def _write_rgba(root: Path, rel_path: str, size: tuple[int, int], rgb: tuple[int, int, int]) -> str:
    path = _repo_file(root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (*rgb, 255))
    image.save(path)
    return sha256_file(path)


def _animation_report(*, outcome: str = "PASS") -> dict[str, object]:
    return {
        "schema": "final-polish-report/0",
        "outcome": outcome,
        "fingerprint": "abc",
    }


def _static_report(*, outcome: str = "PASS") -> dict[str, object]:
    return {
        "schema": "static-asset-report/0",
        "outcome": outcome,
        "fingerprint": "def",
    }


def _animation_releases(root: Path, prefix: str, rgb: tuple[int, int, int]) -> list[dict[str, str]]:
    releases: list[dict[str, str]] = []
    for index in range(4):
        rel = f"{prefix}/frame-{index}.png"
        digest = _write_rgba(root, rel, (16, 24), rgb)
        releases.append({"path": rel, "sha256": digest})
    return releases


def _static_releases(
    root: Path,
    prefix: str,
    items: dict[str, tuple[int, int, int]],
) -> list[dict[str, str]]:
    releases: list[dict[str, str]] = []
    for item_id, rgb in items.items():
        rel = f"{prefix}/{item_id}.png"
        digest = _write_rgba(root, rel, (32, 32), rgb)
        releases.append({"path": rel, "sha256": digest})
    return releases


def _write_report(root: Path, rel_path: str, payload: dict[str, object]) -> str:
    path = _repo_file(root, rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def _base_assets(root: Path) -> list[dict[str, object]]:
    dwarf_idle_report = _write_report(root, _rel(root, "reports/dwarf-idle.json"), _animation_report())
    dwarf_walk_report = _write_report(root, _rel(root, "reports/dwarf-walk.json"), _animation_report())
    dwarf_swing_report = _write_report(
        root,
        _rel(root, "reports/dwarf-swing.json"),
        _animation_report(),
    )
    lantern_report = _write_report(root, _rel(root, "reports/lantern.json"), _animation_report())
    cave_report = _write_report(root, _rel(root, "reports/cave.json"), _static_report())
    mining_report = _write_report(root, _rel(root, "reports/mining.json"), _static_report())

    return [
        {
            "id": "dwarf-idle",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-idle"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-idle.json"),
                "sha256": dwarf_idle_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-idle"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [200, 200, 200, 200],
        },
        {
            "id": "dwarf-walk",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-walk"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-walk.json"),
                "sha256": dwarf_walk_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-walk"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [125, 125, 125, 125],
        },
        {
            "id": "dwarf-swing",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/dwarf-swing"),
            "final_report": {
                "path": _rel(root, "reports/dwarf-swing.json"),
                "sha256": dwarf_swing_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/dwarf-swing"), DWARF),
            "facing": "right",
            "runtime_mirror": True,
            "loop": False,
            "durations_ms": [150, 80, 60, 180],
            "contact_frame": 3,
        },
        {
            "id": "lantern",
            "kind": "animation",
            "bundle_path": _rel(root, "bundles/lantern"),
            "final_report": {
                "path": _rel(root, "reports/lantern.json"),
                "sha256": lantern_report,
            },
            "releases": _animation_releases(root, _rel(root, "releases/lantern"), LANTERN),
            "facing": "right",
            "runtime_mirror": True,
            "loop": True,
            "durations_ms": [160, 160, 160, 160],
        },
        {
            "id": "cave",
            "kind": "static",
            "bundle_path": _rel(root, "bundles/cave"),
            "final_report": {"path": _rel(root, "reports/cave.json"), "sha256": cave_report},
            "releases": _static_releases(
                root,
                _rel(root, "releases/cave"),
                {
                    "cave-v0": STONE,
                    "cave-v1": STONE_LIGHT,
                    "cave-v2": STONE_MID,
                },
            ),
            "item_ids": ["cave-v0", "cave-v1", "cave-v2"],
        },
        {
            "id": "mining",
            "kind": "static",
            "bundle_path": _rel(root, "bundles/mining"),
            "final_report": {"path": _rel(root, "reports/mining.json"), "sha256": mining_report},
            "releases": _static_releases(
                root,
                _rel(root, "releases/mining"),
                {"ore-cyan-seam": CYAN},
            ),
            "item_ids": ["ore-cyan-seam"],
        },
    ]


def pack_doc(
    root: Path,
    *,
    assets: list[dict[str, object]] | None = None,
    preview_scene: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema": PACK_SCHEMA,
        "id": "first-room",
        "master_palette": {
            "path": "assets/palettes/first-room.json",
            "sha256": PALETTE_SHA,
        },
        "viewport": [320, 180],
        "assets": assets if assets is not None else _base_assets(root),
        "preview_scene": preview_scene if preview_scene is not None else TERRACED_SHAFT_PREVIEW_SCENE,
    }


def ensure_repo_palette(root: Path) -> None:
    dest = root / "assets" / "palettes" / "first-room.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(PALETTE_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def write_pack(root: Path, doc: dict[str, object] | None = None) -> Path:
    ensure_repo_palette(root)
    payload = doc if doc is not None else pack_doc(root)
    path = root / "pack.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
