"""Select and run the pytest files touched by the current diff against `main`.

`npm run test:changed` is the local gate an implementer runs before publishing
a PR: CI (`.github/workflows/ci.yml`) owns the full suite and the per-file
isolation sweep on every PR, so the local loop only needs to cover the files a
change actually touches. Selection is mechanical (see `select_test_files`)
so an agent starting cold runs one command and cites its printed output.

See the issue-193 Contract (C1-C4) for the mapping rules this implements.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"

# Changed paths that require the whole suite outright (C2 row 3).
_WHOLE_SUITE_PATHS = {
    "tests/conftest.py",
    "pytest.ini",
    "requirements.txt",
    "package.json",
}

# Changed paths under these top-level directories require the whole suite
# outright (C2 row 3).
_WHOLE_SUITE_DIRS = {"assets", "gate-controls"}


@dataclass(frozen=True)
class Selection:
    """The result of mapping a changed-file set to a test selection.

    `kind` is one of:
    - "nothing": no changed files; there is nothing to run.
    - "selected": `files` is the exact, non-empty set of test files to run.
    - "whole_suite": the mapping widened to the full suite (C3).
    """

    kind: str
    reason: str
    files: tuple[str, ...] = ()


def _mapped_module_name(path: pathlib.PurePosixPath) -> str | None:
    """Return the module stem `path` maps to under C2 rows 1-2, or None if
    `path` does not match either shape."""
    parts = path.parts
    if len(parts) == 2 and parts[0] == "pipeline" and path.suffix == ".py":
        return path.stem
    if len(parts) == 3 and parts[0] == "prototype" and path.suffix == ".py":
        return path.stem
    return None


def select_test_files(
    changed_paths: Iterable[str], existing_tests: Iterable[str]
) -> Selection:
    """Map `changed_paths` (repo-relative, POSIX-style) to the test files
    that cover them, per the issue-193 C2 rules. Pure function of its
    arguments — no git, no filesystem access.

    `existing_tests` is the set of repo-relative test file paths that
    actually exist, used to detect a mapping that resolves to nothing (C3).
    """
    changed = sorted(set(changed_paths))
    if not changed:
        return Selection(kind="nothing", reason="no changed files")

    existing = set(existing_tests)
    selected: set[str] = set()

    for raw_path in changed:
        path = pathlib.PurePosixPath(raw_path)
        posix = path.as_posix()

        if posix in _WHOLE_SUITE_PATHS:
            return Selection(
                kind="whole_suite",
                reason=f"{posix} changed, which always selects the whole suite",
            )

        if path.parts and path.parts[0] in _WHOLE_SUITE_DIRS:
            return Selection(
                kind="whole_suite",
                reason=f"{posix} is under {path.parts[0]}/, which always selects the whole suite",
            )

        if (
            len(path.parts) == 2
            and path.parts[0] == "tests"
            and path.name.startswith("test_")
            and path.suffix == ".py"
        ):
            selected.add(posix)
            continue

        module_name = _mapped_module_name(path)
        if module_name is None:
            return Selection(
                kind="whole_suite",
                reason=f"{posix} has no mapping rule, so the selection widens to the whole suite",
            )

        exact = f"tests/test_{module_name}.py"
        prefix = f"tests/test_{module_name}_"
        matches = {
            t
            for t in existing
            if t == exact or (t.startswith(prefix) and t.endswith(".py"))
        }
        if not matches:
            return Selection(
                kind="whole_suite",
                reason=(
                    f"{posix} maps to no existing test file, so the selection "
                    "widens to the whole suite"
                ),
            )
        selected.update(matches)

    return Selection(
        kind="selected",
        reason="mapped from the changed-file set",
        files=tuple(sorted(selected)),
    )


def _run(args: list[str], cwd: pathlib.Path) -> str:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout


def _git_changed_paths(root: pathlib.Path) -> list[str]:
    merge_base = _run(["git", "merge-base", "HEAD", "main"], root).strip()
    diffed = _run(
        ["git", "diff", "--name-only", f"{merge_base}...HEAD"], root
    ).splitlines()

    uncommitted: list[str] = []
    for line in _run(["git", "status", "--porcelain"], root).splitlines():
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        uncommitted.append(entry)

    return [p for p in (*diffed, *uncommitted) if p]


def _existing_test_files(tests_dir: pathlib.Path, root: pathlib.Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in tests_dir.glob("test_*.py")}


def main() -> int:
    changed = _git_changed_paths(ROOT)
    existing = _existing_test_files(TESTS_DIR, ROOT)
    selection = select_test_files(changed, existing)

    if selection.kind == "nothing":
        print(f"select_changed_tests: {selection.reason}; nothing to run")
        return 0

    if selection.kind == "whole_suite":
        print(f"select_changed_tests: {selection.reason}")
        print("select_changed_tests: running the whole suite")
        pytest_args = ["-q"]
    else:
        print("select_changed_tests: selected test files:")
        for test_file in selection.files:
            print(f"  {test_file}")
        pytest_args = ["-q", *selection.files]

    # execvp replaces this process image without flushing Python's buffered
    # stdout, so an unflushed print above would silently vanish when stdout
    # is not a tty (e.g. piped through `npm run`).
    sys.stdout.flush()
    os.execvp(sys.executable, [sys.executable, "-m", "pytest", *pytest_args])
    return 0  # pragma: no cover - execvp never returns on success


if __name__ == "__main__":
    sys.exit(main())
