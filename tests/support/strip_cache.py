"""Disk-backed second tier for the in-process strip-read cache (#261).

`tests/conftest.py`'s `_memoized_strip_read` keeps an in-process dict as its
first tier so a single test-session hit never touches disk. This module backs
that dict with a store under the pytest temp root: a cross-process hit (a
different `-n auto` worker, or a later per-file isolation run) costs a pickle
load instead of a full Strip recovery. Root resolution, keying, and atomic
read/write live here; `conftest.py` owns the in-process tier and the callee
wiring it wraps.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

PICKLE_PROTOCOL = 5


def store_root(repo_root: Path) -> Path:
    """Resolve the disk store root for ``repo_root``.

    ``UNDERLINE_STRIP_CACHE_DIR`` wins when set. Otherwise the store lives
    under the system temp dir, keyed by the repo path so distinct checkouts
    never collide. Either way the root is outside the repository, so the
    working tree stays clean.
    """
    override = os.environ.get("UNDERLINE_STRIP_CACHE_DIR")
    if override:
        return Path(override)
    digest = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"underline-strip-cache-{digest}"


def key_digest(key: tuple[Any, ...]) -> str:
    """Hash an in-process cache key to a filename-safe digest.

    The key is exactly the tuple `_memoized_strip_read` already builds:
    ``(qualname, str(raw_path), st_mtime_ns, st_size, layout, sorted kwargs)``.
    A regenerated Strip changes ``st_mtime_ns``/``st_size`` and therefore the
    digest, so a stale entry can never be served for the new file.
    """
    return hashlib.sha256(repr(key).encode("utf-8")).hexdigest()


def _entry_path(root: Path, key: tuple[Any, ...]) -> Path:
    return root / f"{key_digest(key)}.pkl"


def read(root: Path, key: tuple[Any, ...]) -> tuple[bool, Any]:
    """Return ``(True, value)`` on a hit, ``(False, None)`` on a miss.

    A missing, truncated, or otherwise unreadable entry is treated as a miss
    and never raised — the caller recomputes and overwrites it.
    """
    path = _entry_path(root, key)
    try:
        data = path.read_bytes()
    except OSError:
        return False, None
    try:
        return True, pickle.loads(data)
    except Exception:
        return False, None


def write(root: Path, key: tuple[Any, ...], value: Any) -> None:
    """Atomically store ``value`` under ``key``.

    Serializes with pickle protocol 5 to a temporary file inside ``root`` and
    ``os.replace``s it into place, so two processes computing the same key
    concurrently each produce a complete file and neither can observe a
    torn read of the other's write.
    """
    root.mkdir(parents=True, exist_ok=True)
    payload = pickle.dumps(value, protocol=PICKLE_PROTOCOL)
    fd, tmp_name = tempfile.mkstemp(dir=root, prefix=".tmp-", suffix=".pkl")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.replace(tmp_name, _entry_path(root, key))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
