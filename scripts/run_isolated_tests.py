"""Run each pytest file in a fresh process with bounded parallelism."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_DURATIONS = Path(__file__).resolve().parent / "isolation-durations.json"


@dataclass(frozen=True)
class IsolationResult:
    path: str
    command: tuple[str, ...]
    pid: int
    returncode: int
    output: str
    duration_s: float


class _ConcurrencyCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.max_observed = 0

    def start(self) -> None:
        with self._lock:
            self._active += 1
            self.max_observed = max(self.max_observed, self._active)

    def finish(self) -> None:
        with self._lock:
            self._active -= 1


def _run_file(path: Path, counter: _ConcurrencyCounter) -> IsolationResult:
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-n0",
        "-p",
        "no:cacheprovider",
        str(path),
    )
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    counter.start()
    try:
        output, _ = process.communicate()
    finally:
        counter.finish()
    return IsolationResult(
        path=str(path),
        command=command,
        pid=process.pid,
        returncode=process.returncode,
        output=output,
        duration_s=round(time.monotonic() - started, 3),
    )


def load_durations(path: Path) -> dict[str, float]:
    """Read recorded per-file seconds, keyed by file name. Absent file means no hints."""
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(name): float(seconds)
        for name, seconds in raw.items()
        if not str(name).startswith("_")
    }


def schedule_order(files: Sequence[Path], durations: dict[str, float]) -> list[Path]:
    """Order files slowest-first so the long pole never starts late.

    Makespan is bounded by the longest single file, so dispatching it last wastes
    the workers that finish early. A file with no recorded duration may itself be
    the new long pole, so it sorts ahead of every measured one.
    """

    def key(item: tuple[int, Path]) -> tuple[float, int]:
        index, path = item
        recorded = durations.get(path.name)
        # Negated so the largest duration sorts first; unknown sorts ahead of all.
        return (-recorded if recorded is not None else float("-inf"), index)

    return [path for _, path in sorted(enumerate(files), key=key)]


def run_isolated_files(
    files: Sequence[Path],
    *,
    workers: int,
    durations: dict[str, float] | None = None,
) -> tuple[list[IsolationResult], int, list[Path]]:
    """Run every file alone; return results in caller order, concurrency, and dispatch order."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    counter = _ConcurrencyCounter()
    dispatch = schedule_order(files, durations or {})
    with ThreadPoolExecutor(max_workers=workers) as executor:
        dispatched = list(executor.map(lambda path: _run_file(path, counter), dispatch))
    by_path = {result.path: result for result in dispatched}
    results = [by_path[str(path)] for path in files]
    return results, counter.max_observed, dispatch


def _report_payload(
    results: Sequence[IsolationResult],
    *,
    workers: int,
    max_concurrency_observed: int,
    wall_s: float,
    schedule: Sequence[Path],
) -> dict[str, object]:
    failed = [result for result in results if result.returncode != 0]
    return {
        "schema": "test-isolation-report/0",
        "outcome": "FAIL" if failed else "PASS",
        "workers": workers,
        "max_concurrency_observed": max_concurrency_observed,
        "wall_s": wall_s,
        "schedule": [path.name for path in schedule],
        "files": [
            {
                "path": result.path,
                "command": list(result.command),
                "pid": result.pid,
                "returncode": result.returncode,
                "duration_s": result.duration_s,
            }
            for result in results
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="concurrent subprocesses; defaults to the machine's CPU count",
    )
    parser.add_argument(
        "--durations",
        type=Path,
        default=DEFAULT_DURATIONS,
        help="recorded per-file seconds used to dispatch the slowest files first",
    )
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    files = list(args.files) or sorted(Path("tests").glob("test_*.py"))
    # Each subprocess is a single-process pytest run, so one worker per core
    # saturates the machine without oversubscribing it.
    workers = args.workers if args.workers is not None else (os.cpu_count() or 1)
    started = time.monotonic()
    results, max_observed, schedule = run_isolated_files(
        files,
        workers=workers,
        durations=load_durations(args.durations),
    )
    wall_s = round(time.monotonic() - started, 3)

    for result in results:
        print(f"::group::{result.path}")
        print(result.output, end="" if result.output.endswith("\n") else "\n")
        if result.returncode != 0:
            print(f"FAILED ALONE: {result.path}")
        print("::endgroup::")

    payload = _report_payload(
        results,
        workers=workers,
        max_concurrency_observed=max_observed,
        wall_s=wall_s,
        schedule=schedule,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"isolation_report={json.dumps(payload, separators=(',', ':'))}")
    return 1 if payload["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
