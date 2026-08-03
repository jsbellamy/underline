"""Decide whether a changed-file set needs the Python asset-pipeline CI jobs.

The game is TypeScript under `src/`; Python is confined to the asset pipeline.
A pull request that only moves game code has nothing for the pipeline suite,
the per-file isolation sweep, or the external-acceptance job to prove, so
`.github/workflows/ci.yml` gates those three jobs on this decision.

The rule is one-directional and fail-safe: the pipeline jobs are skipped only
when *every* changed path is game surface. Anything else -- a pipeline module,
an asset, a doc, a lockfile, a path this script has never heard of -- runs
them. A new top-level directory therefore costs a redundant CI run, never a
missed one.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Iterable

# Paths whose top-level directory is game surface: TypeScript the pipeline
# neither imports nor reads. TypeScript tests live beside the code they cover
# (`docs/agents/code-style.md`), so `src/` covers the game's tests too.
_GAME_DIRS = {"src"}


@dataclass(frozen=True)
class Decision:
    """Whether the asset-pipeline CI jobs must run, and why."""

    needed: bool
    reason: str


def is_game_surface(path: pathlib.PurePosixPath) -> bool:
    """Return whether `path` is game surface -- TypeScript no Python test or
    gate reads. This is the single definition of the game/pipeline boundary;
    `scripts/select_changed_tests.py` maps its local gate against it too, so
    CI and the local gate cannot disagree about what counts as the game."""
    return bool(path.parts) and path.parts[0] in _GAME_DIRS


def pipeline_tests_needed(changed_paths: Iterable[str]) -> Decision:
    """Return whether `changed_paths` (repo-relative, POSIX-style) requires the
    asset-pipeline CI jobs. Pure function of its argument."""
    changed = sorted(set(changed_paths))
    if not changed:
        return Decision(
            needed=True,
            reason="no changed-file list was available, so the gate stays open",
        )

    for raw_path in changed:
        path = pathlib.PurePosixPath(raw_path)
        if not is_game_surface(path):
            return Decision(
                needed=True,
                reason=f"{path.as_posix()} is not game surface",
            )

    return Decision(
        needed=False,
        reason="every changed path is game surface (src/)",
    )


def _read_changed_paths(path: pathlib.Path) -> list[str]:
    """Read a newline-delimited changed-file list, treating an absent or
    unreadable file as "no list available" -- which the gate fails safe on."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-from",
        required=True,
        type=pathlib.Path,
        help="file holding the newline-delimited changed-path list",
    )
    args = parser.parse_args(argv)

    decision = pipeline_tests_needed(_read_changed_paths(args.changed_from))

    verdict = "true" if decision.needed else "false"
    print(f"ci_surfaces: pipeline jobs needed={verdict} -- {decision.reason}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"needed={verdict}\n")
            handle.write(f"reason={decision.reason}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
