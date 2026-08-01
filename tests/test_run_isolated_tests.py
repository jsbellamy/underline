"""Integration proof for the bounded per-file isolation runner (issue #202)."""

from __future__ import annotations

import json
import os
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
    workers: int | None = 2,
    extra_args: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    report_path = tmp_path / "isolation-report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            *(() if workers is None else ("--workers", str(workers))),
            *(extra_args or []),
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


def test_report_records_per_file_duration_and_total_wall_time(tmp_path: Path) -> None:
    files = [
        _write_test(
            tmp_path / f"test_timed_{index}.py",
            "import time\n\ndef test_probe():\n    time.sleep(0.3)\n",
        )
        for index in range(2)
    ]

    _, report = _run_isolation(tmp_path, files, workers=1)

    rows = report["files"]
    assert isinstance(rows, list)
    # Each probe sleeps 0.3s, so its process cannot have taken less than that.
    assert all(row["duration_s"] >= 0.3 for row in rows)
    # Serialised by workers=1, so the wall clock covers both files end to end.
    # Each reported value is rounded to milliseconds independently.
    rounding_tolerance_s = 0.001 * (len(rows) + 1)
    assert report["wall_s"] + rounding_tolerance_s >= sum(
        row["duration_s"] for row in rows
    )


def test_hint_accuracy_is_reported_without_affecting_outcome_or_schedule(
    tmp_path: Path,
) -> None:
    files = _probe_files(tmp_path, ["test_timed_0.py", "test_timed_1.py"])
    durations = tmp_path / "durations.json"
    # test_timed_0.py's hint is deliberately too low (stale); test_timed_1.py's
    # hint comfortably covers a fast probe, so it never reads as stale.
    durations.write_text(
        json.dumps({"test_timed_0.py": 0.001, "test_timed_1.py": 10.0}),
        encoding="utf-8",
    )

    _, report = _run_isolation(
        tmp_path,
        files,
        workers=1,
        extra_args=["--durations", str(durations)],
    )

    # C2: reporting only -- the schedule still follows the hints themselves
    # (largest recorded hint dispatched first), and the outcome is unaffected.
    assert report["schedule"] == ["test_timed_1.py", "test_timed_0.py"]
    assert report["outcome"] == "PASS"

    by_name = {Path(row["path"]).name: row for row in report["files"]}
    stale_row = by_name["test_timed_0.py"]
    accurate_row = by_name["test_timed_1.py"]
    assert stale_row["hint_s"] == 0.001
    assert stale_row["hint_ratio"] > 2.0
    assert accurate_row["hint_s"] == 10.0
    assert accurate_row["hint_ratio"] < 1.0

    # C3: only the file whose measured duration exceeds 2x its hint is named.
    assert report["stale_hint_files"] == ["test_timed_0.py"]
    assert report["worst_case_hint_ratio"] == stale_row["hint_ratio"]


def test_accurate_hints_report_no_stale_files(tmp_path: Path) -> None:
    files = _probe_files(tmp_path, ["test_a.py", "test_b.py"])
    durations = tmp_path / "durations.json"
    durations.write_text(
        json.dumps({"test_a.py": 10.0, "test_b.py": 10.0}),
        encoding="utf-8",
    )

    _, report = _run_isolation(
        tmp_path,
        files,
        workers=1,
        extra_args=["--durations", str(durations)],
    )

    assert report["stale_hint_files"] == []
    assert all(row["hint_ratio"] < 2.0 for row in report["files"])


def test_worker_count_defaults_to_the_available_cpus_and_runs_files_concurrently(
    tmp_path: Path,
) -> None:
    cpus = os.cpu_count() or 1
    files = [
        _write_test(
            tmp_path / f"test_parallel_{index}.py",
            "import time\n\ndef test_probe():\n    time.sleep(0.5)\n",
        )
        for index in range(4)
    ]

    _, report = _run_isolation(tmp_path, files, workers=None)

    assert report["workers"] == min(cpus, len(files))
    if cpus > 1:
        # Four 0.5s probes cannot finish in under a second unless they overlap.
        assert report["max_concurrency_observed"] > 1
        assert report["wall_s"] < sum(row["duration_s"] for row in report["files"])


def _probe_files(tmp_path: Path, names: list[str]) -> list[Path]:
    return [
        _write_test(tmp_path / name, "def test_probe():\n    assert True\n") for name in names
    ]


def test_slowest_known_files_are_dispatched_first_without_reordering_the_report(
    tmp_path: Path,
) -> None:
    files = _probe_files(tmp_path, ["test_a.py", "test_b.py", "test_z.py"])
    durations = tmp_path / "durations.json"
    durations.write_text(
        json.dumps({"test_a.py": 0.5, "test_b.py": 0.1, "test_z.py": 9.0}),
        encoding="utf-8",
    )

    _, report = _run_isolation(
        tmp_path,
        files,
        workers=1,
        extra_args=["--durations", str(durations)],
    )

    # Dispatched slowest-first so the long pole starts before the short files.
    assert report["schedule"] == ["test_z.py", "test_a.py", "test_b.py"]
    # Logs and report rows stay in the order the caller gave, for readability.
    assert [Path(row["path"]).name for row in report["files"]] == [
        "test_a.py",
        "test_b.py",
        "test_z.py",
    ]


def test_files_with_no_recorded_duration_are_dispatched_before_known_ones(
    tmp_path: Path,
) -> None:
    files = _probe_files(tmp_path, ["test_known_slow.py", "test_unknown.py"])
    durations = tmp_path / "durations.json"
    durations.write_text(json.dumps({"test_known_slow.py": 9.0}), encoding="utf-8")

    _, report = _run_isolation(
        tmp_path,
        files,
        workers=1,
        extra_args=["--durations", str(durations)],
    )

    # An unmeasured file might be the new long pole, so schedule it first.
    assert report["schedule"] == ["test_unknown.py", "test_known_slow.py"]


def test_missing_durations_file_leaves_the_given_order_untouched(tmp_path: Path) -> None:
    files = _probe_files(tmp_path, ["test_a.py", "test_b.py"])

    _, report = _run_isolation(
        tmp_path,
        files,
        workers=1,
        extra_args=["--durations", str(tmp_path / "absent.json")],
    )

    assert report["schedule"] == ["test_a.py", "test_b.py"]
    assert report["outcome"] == "PASS"


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
