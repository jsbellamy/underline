"""Integration proof for the bounded per-file isolation runner (issue #202)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "run_isolated_tests.py"


def _write_test(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _run_isolation(
    tmp_path: Path,
    files: list[Path],
    *,
    workers: int = 2,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    report_path = tmp_path / "isolation-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workers",
            str(workers),
            "--report",
            str(report_path),
            *(str(path) for path in files),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return result, report


def test_each_file_gets_a_fresh_process_with_bounded_parallelism_and_ordered_logs(
    tmp_path: Path,
) -> None:
    files = [
        _write_test(
            tmp_path / f"test_probe_{index}.py",
            "import time\n\ndef test_probe():\n    time.sleep(0.25)\n",
        )
        for index in range(4)
    ]

    result, report = _run_isolation(tmp_path, files)

    assert result.returncode == 0, result.stdout + result.stderr
    assert report["schema"] == "test-isolation-report/0"
    assert report["outcome"] == "PASS"
    assert report["workers"] == 2
    assert report["max_concurrency_observed"] == 2
    rows = report["files"]
    assert isinstance(rows, list)
    assert [row["path"] for row in rows] == [str(path) for path in files]
    assert len({row["pid"] for row in rows}) == len(files)
    assert all(row["returncode"] == 0 for row in rows)
    assert all("-n0" in row["command"] for row in rows)
    group_positions = [result.stdout.index(f"::group::{path}") for path in files]
    assert group_positions == sorted(group_positions)
    assert "isolation_report={" in result.stdout


def test_every_file_runs_and_all_failed_alone_files_are_reported(tmp_path: Path) -> None:
    passing_a = _write_test(
        tmp_path / "test_passing_a.py",
        "def test_passes():\n    assert True\n",
    )
    failing = _write_test(
        tmp_path / "test_failing.py",
        "def test_fails():\n    assert False\n",
    )
    passing_b = _write_test(
        tmp_path / "test_passing_b.py",
        "def test_passes():\n    assert True\n",
    )

    result, report = _run_isolation(tmp_path, [passing_a, failing, passing_b])

    assert result.returncode == 1
    assert report["outcome"] == "FAIL"
    rows = report["files"]
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert [row["returncode"] == 0 for row in rows] == [True, False, True]
    assert f"FAILED ALONE: {failing}" in result.stdout
    assert 'isolation_report={"schema":"test-isolation-report/0","outcome":"FAIL"' in result.stdout


def test_no_explicit_files_discovers_every_test_file_in_sorted_order(
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    _write_test(tests_dir / "test_b.py", "def test_b():\n    assert True\n")
    _write_test(tests_dir / "test_a.py", "def test_a():\n    assert True\n")
    report_path = tmp_path / "isolation-report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--workers",
            "2",
            "--report",
            str(report_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert [row["path"] for row in report["files"]] == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]
