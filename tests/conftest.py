"""Pytest configuration for the underline prototype."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STRIP_COHERENCE = ROOT / "prototype" / "strip-coherence"


def _load_prototype_module(name: str) -> None:
    if name in sys.modules:
        return
    path = STRIP_COHERENCE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load prototype module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


for _name in ("corpus", "adversarial"):
    _load_prototype_module(_name)
