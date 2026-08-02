"""Behavioral proof for tests.support.strip_cache (#261)."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from pathlib import Path

import pytest

from tests.support import strip_cache


def _key(path: Path, layout: str = "idle", qualname: str = "some.qualname") -> tuple:
    stat = path.stat()
    return (qualname, str(path), stat.st_mtime_ns, stat.st_size, layout, ())


def _write_from_subprocess(root: Path, key: tuple, value: dict) -> None:
    """Top-level so `multiprocessing`'s spawn start method can pickle it."""
    strip_cache.write(root, key, value)


# --- C4: store root resolution -------------------------------------------------


def test_store_root_honors_env_override(tmp_path, monkeypatch):
    override = tmp_path / "custom-cache-dir"
    monkeypatch.setenv("UNDERLINE_STRIP_CACHE_DIR", str(override))
    assert strip_cache.store_root(tmp_path) == override


def test_store_root_default_is_outside_repo_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv("UNDERLINE_STRIP_CACHE_DIR", raising=False)
    root_a = strip_cache.store_root(tmp_path)
    root_b = strip_cache.store_root(tmp_path)
    assert root_a == root_b
    assert tmp_path not in root_a.parents and root_a != tmp_path


def test_store_root_default_differs_per_repo_path(tmp_path, monkeypatch):
    monkeypatch.delenv("UNDERLINE_STRIP_CACHE_DIR", raising=False)
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    repo_one.mkdir()
    repo_two.mkdir()
    assert strip_cache.store_root(repo_one) != strip_cache.store_root(repo_two)


# --- C2: keying -----------------------------------------------------------------


def test_key_digest_changes_when_mtime_changes(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"first")
    key_before = _key(target)
    # Force a distinct st_mtime_ns without relying on filesystem timestamp
    # resolution racing the two writes.
    time.sleep(0.01)
    os.utime(target, ns=(time.time_ns(), time.time_ns() + 1_000_000))
    target.write_bytes(b"first")
    key_after = _key(target)
    assert key_before != key_after
    assert strip_cache.key_digest(key_before) != strip_cache.key_digest(key_after)


def test_key_digest_is_deterministic_for_the_same_key(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    key = _key(target)
    assert strip_cache.key_digest(key) == strip_cache.key_digest(key)


# --- C2/C5/C6: read/write round trip and miss handling ---------------------------


def test_read_on_empty_store_is_a_miss(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    hit, value = strip_cache.read(tmp_path / "store", _key(target))
    assert (hit, value) == (False, None)


def test_write_then_read_round_trips_an_equal_value(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)
    value = ([[1, 2], [3, 4]], {"grid": [2, 2]})

    strip_cache.write(root, key, value)
    hit, read_back = strip_cache.read(root, key)

    assert hit is True
    assert read_back == value


def test_mutating_the_returned_value_does_not_affect_the_next_read(tmp_path):
    """C3: pickle round-tripping yields an independent copy each time."""
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)
    value = {"cells": [[1, 2]]}

    strip_cache.write(root, key, value)
    _, first_read = strip_cache.read(root, key)
    first_read["cells"][0].append(999)

    _, second_read = strip_cache.read(root, key)
    assert second_read == {"cells": [[1, 2]]}


def test_a_missing_file_key_is_a_miss_and_write_is_never_called(tmp_path):
    """C6: a raising call must not reach strip_cache.write; simulate that
    contract here by asserting a read for a key nobody wrote stays a miss."""
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)

    hit, value = strip_cache.read(root, key)

    assert (hit, value) == (False, None)
    assert not root.exists() or list(root.glob("*.pkl")) == []


def test_corrupt_entry_is_treated_as_a_miss_and_can_be_overwritten(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)

    strip_cache.write(root, key, {"ok": True})
    (entry,) = root.glob("*.pkl")
    entry.write_bytes(b"not a pickle at all, deliberately truncated")

    hit, value = strip_cache.read(root, key)
    assert (hit, value) == (False, None)

    # A miss must be recoverable: writing the real value again succeeds and
    # the corrupt bytes are replaced, never raised.
    strip_cache.write(root, key, {"ok": True})
    hit, value = strip_cache.read(root, key)
    assert (hit, value) == (True, {"ok": True})


# --- C5: atomic concurrent writes ------------------------------------------------


def test_concurrent_writers_of_the_same_key_both_succeed_and_agree(tmp_path):
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)
    value = {"cells": list(range(2000))}  # large enough to make a torn write plausible
    errors: list[BaseException] = []

    def _writer() -> None:
        try:
            strip_cache.write(root, key, value)
        except BaseException as exc:  # pragma: no cover - failure path only
            errors.append(exc)

    threads = [threading.Thread(target=_writer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    hit, read_back = strip_cache.read(root, key)
    assert hit is True
    assert read_back == value


def test_concurrent_writers_of_the_same_key_across_processes_both_succeed_and_agree(tmp_path):
    """C5's proof names two processes, not threads: exercise the real
    cross-process case an xdist worker pair actually hits."""
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")
    root = tmp_path / "store"
    key = _key(target)
    value = {"cells": list(range(2000))}

    processes = [
        multiprocessing.Process(target=_write_from_subprocess, args=(root, key, value))
        for _ in range(4)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)

    assert [p.exitcode for p in processes] == [0] * len(processes)
    hit, read_back = strip_cache.read(root, key)
    assert hit is True
    assert read_back == value


# --- C1/C2 integration through the conftest wrapper -----------------------------


def test_second_read_through_the_wrapper_hits_disk_without_recomputing(tmp_path, monkeypatch):
    """C1, C2: a disk-tier hit serves the value without invoking the callee,
    simulated by clearing the in-process dict tier between two 'processes'."""
    from tests import conftest as ct

    monkeypatch.setenv("UNDERLINE_STRIP_CACHE_DIR", str(tmp_path / "store"))
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")

    calls = {"count": 0}

    def _fake_recover(raw_path: Path, layout: str, **kwargs: object) -> dict:
        calls["count"] += 1
        return {"cells": "recomputed", "call": calls["count"]}

    _fake_recover.__qualname__ = "fake_recover_for_test_261"
    wrapped = ct._memoized_strip_read(_fake_recover)

    first = wrapped(target, "idle")
    assert calls["count"] == 1

    # Simulate a second process: no shared in-process dict.
    ct._STRIP_READ_CACHE.clear()
    second = wrapped(target, "idle")

    assert calls["count"] == 1  # disk tier served the hit; callee not invoked again
    assert second == first

    # Touching the file to change st_mtime_ns forces a recompute (C2).
    time.sleep(0.01)
    os.utime(target, ns=(time.time_ns(), time.time_ns() + 1_000_000))
    ct._STRIP_READ_CACHE.clear()
    third = wrapped(target, "idle")
    assert calls["count"] == 2
    assert third != first


def test_a_raising_call_through_the_wrapper_is_never_cached(tmp_path, monkeypatch):
    """C6: raising calls stay uncached, on both the in-process and disk tier."""
    from tests import conftest as ct

    store_dir = tmp_path / "store"
    monkeypatch.setenv("UNDERLINE_STRIP_CACHE_DIR", str(store_dir))
    target = tmp_path / "strip.png"
    target.write_bytes(b"data")

    calls = {"count": 0}

    def _fake_raising_recover(raw_path: Path, layout: str, **kwargs: object) -> dict:
        calls["count"] += 1
        raise ValueError("pitch-fail: deliberately unrecoverable for the test")

    _fake_raising_recover.__qualname__ = "fake_raising_recover_for_test_261"
    wrapped = ct._memoized_strip_read(_fake_raising_recover)

    key = _key(target, qualname=_fake_raising_recover.__qualname__)

    with pytest.raises(ValueError):
        wrapped(target, "idle")
    assert calls["count"] == 1
    assert key not in ct._STRIP_READ_CACHE
    assert not store_dir.exists() or list(store_dir.glob("*.pkl")) == []

    # A second call still raises and still recomputes: nothing was cached.
    with pytest.raises(ValueError):
        wrapped(target, "idle")
    assert calls["count"] == 2
