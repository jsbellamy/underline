"""Run each pytest file in a fresh process with bounded parallelism."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class IsolationResult:
    path: str
    command: tuple[str, ...]
    pid: int
    returncode: int
    output: str


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
    )


def run_isolated_files(files: Sequence[Path], *, workers: int) -> tuple[list[IsolationResult], int]:
    """Run every file alone and return ordered results plus observed concurrency."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    counter = _ConcurrencyCounter()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda path: _run_file(path, counter), files))
    return results, counter.max_observed


def _report_payload(
    results: Sequence[IsolationResult],
    *,
    workers: int,
    max_concurrency_observed: int,
) -> dict[str, object]:
    failed = [result for result in results if result.returncode != 0]
    return {
        "schema": "test-isolation-report/0",
        "outcome": "FAIL" if failed else "PASS",
        "workers": workers,
        "max_concurrency_observed": max_concurrency_observed,
        "files": [
            {
                "path": result.path,
                "command": list(result.command),
                "pid": result.pid,
                "returncode": result.returncode,
            }
            for result in results
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    files = list(args.files) or sorted(Path("tests").glob("test_*.py"))
    results, max_observed = run_isolated_files(files, workers=args.workers)

    for result in results:
        print(f"::group::{result.path}")
        print(result.output, end="" if result.output.endswith("\n") else "\n")
        if result.returncode != 0:
            print(f"FAILED ALONE: {result.path}")
        print("::endgroup::")

    payload = _report_payload(
        results,
        workers=args.workers,
        max_concurrency_observed=max_observed,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"isolation_report={json.dumps(payload, separators=(',', ':'))}")
    return 1 if payload["outcome"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
