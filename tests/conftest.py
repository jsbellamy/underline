"""Pytest configuration for the underline prototype."""

from __future__ import annotations

import copy
import functools
import importlib.util
import pathlib
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STRIP_COHERENCE = ROOT / "prototype" / "strip-coherence"


# Recovering and ingesting a corpus strip is pure with respect to the PNG on
# disk, but the suite asks for the same handful of strips about two and a half
# times over — 105 reads across 40 distinct strips, most of the wall clock.
# Memoize them for the test session only. The cache key carries the file's
# mtime and size so a regenerated strip can never serve a stale result, and
# results are deep-copied on the way out so one test cannot mutate cells that
# a later test reads. Copying costs ~0.002s against a ~0.45s recompute.
_STRIP_READ_CACHE: dict[Any, Any] = {}


def _memoized_strip_read(fn: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(fn)
    def wrapper(raw_path: pathlib.Path, layout: Any, **kwargs: Any) -> Any:
        try:
            stat = pathlib.Path(raw_path).stat()
        except OSError:
            # Missing-file behaviour belongs to the real callee, not the cache.
            return fn(raw_path, layout, **kwargs)
        key = (
            fn.__qualname__,
            str(raw_path),
            stat.st_mtime_ns,
            stat.st_size,
            layout,
            tuple(sorted(kwargs.items())),
        )
        if key not in _STRIP_READ_CACHE:
            # Raising calls stay uncached: pytest.raises cases are cheap.
            _STRIP_READ_CACHE[key] = fn(raw_path, layout, **kwargs)
        return copy.deepcopy(_STRIP_READ_CACHE[key])

    return wrapper


def _install_strip_read_cache() -> None:
    from pipeline import strip

    for name in ("recover_strip_cells", "ingest_strip_provider"):
        setattr(strip, name, _memoized_strip_read(getattr(strip, name)))


# Must run before any module binds these names with a `from ... import`.
_install_strip_read_cache()


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
