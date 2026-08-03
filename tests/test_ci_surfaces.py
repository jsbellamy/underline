"""Unit tests for the CI surface gate.

The gate is exercised as a pure function of a synthetic changed-file list --
no git subprocess, no filesystem scan, no GitHub API.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from scripts.ci_surfaces import game_tests_needed, pipeline_tests_needed

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_cli(tmp_path: pathlib.Path, changed: str | None) -> dict[str, str]:
    """Run the CLI the way `ci.yml` does and return its GitHub step outputs."""
    github_output = tmp_path / "github-output"
    github_output.touch()
    changed_file = tmp_path / "changed.txt"
    if changed is not None:
        changed_file.write_text(changed, encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            "scripts/ci_surfaces.py",
            "--changed-from",
            str(changed_file),
        ],
        cwd=ROOT,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(github_output)},
        capture_output=True,
        text=True,
        check=True,
    )

    return dict(
        line.split("=", 1)
        for line in github_output.read_text(encoding="utf-8").splitlines()
        if line
    )


def test_game_only_change_does_not_need_the_pipeline_suite() -> None:
    decision = pipeline_tests_needed(["src/core/simulation.ts"])

    assert decision.needed is False


def test_game_only_change_needs_the_game_job() -> None:
    decision = game_tests_needed(["src/core/simulation.ts"])

    assert decision.needed is True


def test_pipeline_only_change_does_not_need_the_game_job() -> None:
    decision = game_tests_needed(["pipeline/strip.py"])

    assert decision.needed is False


def test_pipeline_only_change_needs_the_pipeline_suite() -> None:
    decision = pipeline_tests_needed(["pipeline/strip.py"])

    assert decision.needed is True


def test_src_tauri_is_game_surface() -> None:
    assert pipeline_tests_needed(["src-tauri/src/lib.rs"]).needed is False
    assert game_tests_needed(["src-tauri/src/lib.rs"]).needed is True


def test_vite_config_is_game_surface() -> None:
    assert pipeline_tests_needed(["vite.config.ts"]).needed is False
    assert game_tests_needed(["vite.config.ts"]).needed is True


def test_an_empty_changed_set_still_needs_the_pipeline_suite() -> None:
    # A diff this script could not compute arrives here as an empty list. The
    # gate is fail-safe, so "I know nothing" runs the jobs.
    decision = pipeline_tests_needed([])

    assert decision.needed is True


def test_a_game_change_alongside_a_pipeline_change_needs_the_pipeline_suite() -> None:
    decision = pipeline_tests_needed(
        ["src/core/simulation.ts", "pipeline/strip.py"]
    )

    assert decision.needed is True
    assert "pipeline/strip.py" in decision.reason


def test_non_game_surfaces_each_need_the_pipeline_suite() -> None:
    # One case per surface the pipeline jobs actually prove something about,
    # plus a shared root file. None of these is game surface, so none may be
    # skipped by the game rule.
    for path in (
        "pipeline/strip.py",
        "tests/test_strip.py",
        "scripts/run_isolated_tests.py",
        "prototype/strip-coherence/corpus.py",
        "assets/miner/idle/strip.png",
        "gate-controls/idle/report.json",
        "docs/strip-acquisition-contract.md",
        "package.json",
        "requirements.txt",
        "pytest.ini",
        ".github/workflows/ci.yml",
    ):
        decision = pipeline_tests_needed([path])

        assert decision.needed is True, path
        assert path in decision.reason


def test_non_game_surfaces_do_not_need_the_game_job() -> None:
    for path in (
        "pipeline/strip.py",
        "tests/test_strip.py",
        "assets/miner/idle/strip.png",
        "gate-controls/idle/report.json",
        "docs/strip-acquisition-contract.md",
        "requirements.txt",
        "pytest.ini",
        ".github/workflows/ci.yml",
    ):
        decision = game_tests_needed([path])

        assert decision.needed is False, path


def test_package_json_needs_both_jobs() -> None:
    assert pipeline_tests_needed(["package.json"]).needed is True
    assert game_tests_needed(["package.json"]).needed is True


def test_an_unrecognised_top_level_directory_needs_the_pipeline_suite() -> None:
    # A directory this script has never heard of is not assumed to be game
    # surface: a new top-level tree costs a redundant run, never a missed one.
    decision = pipeline_tests_needed(["renderer/webgl/atlas.ts"])

    assert decision.needed is True


def test_a_directory_merely_prefixed_with_src_is_not_game_surface() -> None:
    decision = pipeline_tests_needed(["srcs/thing.py"])

    assert decision.needed is True


def test_cli_reports_a_game_only_diff_as_not_needing_the_pipeline_suite(
    tmp_path: pathlib.Path,
) -> None:
    outputs = _run_cli(tmp_path, "src/core/simulation.ts\nsrc/ui/hud.ts\n")

    assert outputs["pipeline_needed"] == "false"
    assert outputs["game_needed"] == "true"


def test_cli_reports_a_pipeline_diff_as_needing_the_pipeline_suite(
    tmp_path: pathlib.Path,
) -> None:
    outputs = _run_cli(tmp_path, "src/core/simulation.ts\npipeline/strip.py\n")

    assert outputs["pipeline_needed"] == "true"
    assert outputs["game_needed"] == "true"


def test_cli_reports_a_pipeline_only_diff_as_not_needing_the_game_job(
    tmp_path: pathlib.Path,
) -> None:
    outputs = _run_cli(tmp_path, "pipeline/strip.py\n")

    assert outputs["pipeline_needed"] == "true"
    assert outputs["game_needed"] == "false"


def test_cli_falls_back_to_needing_the_suite_when_the_diff_is_unreadable(
    tmp_path: pathlib.Path,
) -> None:
    # `ci.yml` writes no file when it cannot enumerate the PR's files. A gate
    # that cannot see the diff must not be the thing that skips the tests.
    outputs = _run_cli(tmp_path, changed=None)

    assert outputs["pipeline_needed"] == "true"
    assert outputs["game_needed"] == "true"
