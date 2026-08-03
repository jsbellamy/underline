"""Resolve the `main` baseline a drift test compares against (#328).

`git show main:<path>` is only spelled `main` in a checkout that has the local
branch — a push build, or a developer's clone. GitHub's `pull_request` checkout
has neither: even at `fetch-depth: 0` the action writes remote-tracking refs
(`origin/main`) and leaves HEAD detached on the merge commit, so `main` is an
invalid object name and every baseline test dies with exit 128. Resolution
walks the candidates in order and the first one that names a commit wins, so
the same test passes locally and in PR CI without either side special-casing
the other.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

BASELINE_CANDIDATES: tuple[str, ...] = ("main", "origin/main")


class BaselineRefError(RuntimeError):
    """No candidate ref named a commit in this checkout."""


def resolve_baseline_rev(
    repo: Path, candidates: Sequence[str] = BASELINE_CANDIDATES
) -> str:
    """Return the first candidate that resolves to a commit in ``repo``.

    Raises `BaselineRefError` rather than skipping: a checkout too shallow to
    hold the baseline must fail loudly, or asset drift lands unproven.
    """
    for candidate in candidates:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"],
            cwd=repo,
            capture_output=True,
        )
        if resolved.returncode == 0:
            return candidate
    raise BaselineRefError(
        f"none of {', '.join(candidates)} resolve to a commit in {repo}; "
        "the checkout needs the baseline branch (CI: fetch-depth: 0)"
    )


def read_baseline_bytes(
    repo: Path, path: str, candidates: Sequence[str] = BASELINE_CANDIDATES
) -> bytes:
    """Read ``path`` as committed on the resolved baseline ref."""
    rev = resolve_baseline_rev(repo, candidates)
    return subprocess.check_output(["git", "show", f"{rev}:{path}"], cwd=repo)
