"""The baseline-ref contract between `ci.yml` and `tests.support.git_baseline`.

`tests/support/git_baseline.py` reads an asset as committed on `main`, and it
raises when no candidate ref resolves. That precondition is satisfied by the
workflow, not by any Python: a job needs either `fetch-depth: 0` (which writes
`origin/main`) or a checkout of `main` itself (which writes a local branch).
Nothing else in the suite reads that YAML, so deleting the pins would surface
only as a confusing red on an unrelated PR -- the exact shape of the failure
this file exists to prevent.

The second half guards the other direction: a bare `main` rev anywhere in the
suite works on every developer clone and on push builds, and dies with exit 128
in the detached merge-ref checkout GitHub gives a pull request.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SCANNED_DIRS = ("tests", "pipeline", "scripts", "prototype")
# The resolver itself is the sanctioned place to name the candidate refs.
BARE_REV_EXEMPT = frozenset({Path("tests/support/git_baseline.py"), Path("tests/test_ci_contract.py")})
# `main:path` and `main..HEAD` -- the two rev spellings that need a local
# branch named `main`. Deliberately narrow: this is a targeted guard against one
# reintroduced bug, not a general git linter.
BARE_MAIN_REV = re.compile(r"""['"]main(:|\.\.)""")
# Jobs prove a pipeline claim by running pytest, whether directly, through the
# npm script, or through the per-file isolation runner.
PYTEST_INVOCATION = re.compile(r"pytest|test:python|run_isolated_tests")
BASELINE_JOBS = ("external-acceptance", "isolation", "test")


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(job: dict) -> list[dict]:
    return job.get("steps") or []


def _runs_pytest(job: dict) -> bool:
    return any(PYTEST_INVOCATION.search(step.get("run") or "") for step in _steps(job))


def _supplies_baseline_ref(step: dict) -> bool:
    """Whether this checkout leaves a resolvable `main` or `origin/main` behind."""
    if not str(step.get("uses", "")).startswith("actions/checkout"):
        return False
    inputs = step.get("with") or {}
    return inputs.get("fetch-depth") == 0 or inputs.get("ref") == "main"


def _jobs_running_pytest() -> dict[str, dict]:
    return {
        name: job for name, job in _workflow()["jobs"].items() if _runs_pytest(job)
    }


def test_every_job_running_pytest_checks_out_a_resolvable_baseline() -> None:
    for name, job in _jobs_running_pytest().items():
        assert any(_supplies_baseline_ref(step) for step in _steps(job)), (
            f"job '{name}' runs pytest but no checkout step supplies a baseline "
            "ref; tests/support/git_baseline.py will raise BaselineRefError"
        )


def test_the_pytest_job_detector_still_finds_the_known_jobs() -> None:
    """Without this, renaming a run step makes the check above pass vacuously."""
    assert sorted(_jobs_running_pytest()) == sorted(BASELINE_JOBS)


@pytest.mark.parametrize("directory", SCANNED_DIRS)
def test_no_source_file_names_a_bare_main_rev(directory: str) -> None:
    offenders = []
    for path in sorted((ROOT / directory).rglob("*.py")):
        relative = path.relative_to(ROOT)
        if relative in BARE_REV_EXEMPT:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if BARE_MAIN_REV.search(line):
                offenders.append(f"{relative}:{number}: {line.strip()}")
    assert not offenders, (
        "a bare `main` rev only resolves where a local branch exists, so it "
        "passes locally and on push builds and fails in pull-request CI; read "
        "the baseline through tests.support.git_baseline instead:\n"
        + "\n".join(offenders)
    )
