"""Decide which CI test jobs a changed-file set needs.

The game is TypeScript under `src/` and the Tauri shell under `src-tauri/`;
Python is confined to the asset pipeline. `.github/workflows/ci.yml` gates
the pipeline jobs (pytest suite, isolation sweep), the game job (typecheck +
Vitest), and the external-acceptance job on three independent decisions from
this module.

Each decision is fail-safe on an empty or unreadable changed-file list. A
pipeline-only pull request skips the game job; a game-only pull request skips
the pipeline jobs. Anything outside recognised game surface -- a pipeline
module, an asset, a doc, a path this script has never heard of -- still runs
the pipeline jobs. A new top-level directory therefore costs a redundant
pipeline run, never a missed one.

The external-acceptance decision is narrower, because that job is the only one
that runs the whole suite a third time and it reads a *difference* between two
trees rather than the candidate alone. It is still complementary, not an
allowlist: it names the surfaces that provably cannot move the difference and
runs on everything else, so a new top-level directory costs a redundant run
here too.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass
from typing import Iterable

# Paths whose top-level directory is game surface: TypeScript and the Tauri
# shell the pipeline neither imports nor reads. TypeScript tests live beside
# the code they cover (`docs/agents/code-style.md`), so `src/` covers the
# game's Vitest suite too.
_GAME_DIRS = {"src", "src-tauri"}

# Root-level files that belong to the game build only.
_GAME_ROOT_FILES = frozenset(
    {"vite.config.ts", "tsconfig.json", "index.html"}
)

# Root-level files that affect both CI jobs (shared npm lockfile and scripts).
_SHARED_ROOT_FILES = frozenset({"package.json", "package-lock.json"})

# Surfaces the external-acceptance job provably cannot read a difference from.
# That job judges the candidate's assets twice -- once with main's pipeline,
# once with the candidate's -- and separately runs main's tests against the
# candidate's assets and gate-controls trees. So `pipeline/` and the script and
# dependency set wiring it can make the two judges disagree, and `assets/` and
# `gate-controls/` are what the copied-in trees carry. The directories below
# reach none of that: the game is never imported, the candidate's `tests/` are
# deliberately not the ones that run (C5 runs main's), and no pipeline module
# reads `docs/` or `prompts/`. Everything else -- including a directory this
# script has never heard of -- still runs the job.
_EVALUATOR_INERT_DIRS = {"docs", "prompts", "tests", "src", "src-tauri", ".github"}


@dataclass(frozen=True)
class Decision:
    """Whether a CI job group must run, and why."""

    needed: bool
    reason: str


def is_game_surface(path: pathlib.PurePosixPath) -> bool:
    """Return whether `path` is game surface -- TypeScript and Tauri files no
    Python test or gate reads. This is the single definition of the game/pipeline
    boundary; `scripts/select_changed_tests.py` maps its local gate against it
    too, so CI and the local gate cannot disagree about what counts as the
    game."""
    if not path.parts:
        return False
    if path.parts[0] in _GAME_DIRS:
        return True
    return len(path.parts) == 1 and path.as_posix() in _GAME_ROOT_FILES


def _fail_safe_open(reason: str) -> Decision:
    return Decision(needed=True, reason=reason)


def game_tests_needed(changed_paths: Iterable[str]) -> Decision:
    """Return whether `changed_paths` requires the game CI job (typecheck +
    Vitest). Pure function of its argument."""
    changed = sorted(set(changed_paths))
    if not changed:
        return _fail_safe_open(
            "no changed-file list was available, so the gate stays open",
        )

    for raw_path in changed:
        path = pathlib.PurePosixPath(raw_path)
        posix = path.as_posix()
        if posix in _SHARED_ROOT_FILES:
            return Decision(
                needed=True,
                reason=f"{posix} affects both game and pipeline CI",
            )
        if is_game_surface(path):
            return Decision(
                needed=True,
                reason=f"{posix} is game surface",
            )

    return Decision(
        needed=False,
        reason="every changed path is outside game surface",
    )


def pipeline_tests_needed(changed_paths: Iterable[str]) -> Decision:
    """Return whether `changed_paths` (repo-relative, POSIX-style) requires the
    asset-pipeline CI jobs. Pure function of its argument."""
    changed = sorted(set(changed_paths))
    if not changed:
        return _fail_safe_open(
            "no changed-file list was available, so the gate stays open",
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
        reason="every changed path is game surface",
    )


def is_evaluator_inert(path: pathlib.PurePosixPath) -> bool:
    """Return whether `path` provably cannot move the external-acceptance
    comparison. Unrecognised paths are never inert, so the job stays fail-safe
    against a surface this script has not been taught."""
    if not path.parts:
        return False
    if path.parts[0] in _EVALUATOR_INERT_DIRS:
        return True
    # A root-level document: read by prose and by main's own tests, never by
    # the pipeline whose verdicts this job compares.
    return len(path.parts) == 1 and path.as_posix().endswith(".md")


def external_acceptance_needed(changed_paths: Iterable[str]) -> Decision:
    """Return whether `changed_paths` requires the external-acceptance job.

    Narrower than `pipeline_tests_needed` on purpose: this job is the only one
    that runs the suite a third time, and it proves nothing when the candidate
    and evaluator trees are identical. Fail-safe on an empty list like its
    siblings.
    """
    changed = sorted(set(changed_paths))
    if not changed:
        return _fail_safe_open(
            "no changed-file list was available, so the gate stays open",
        )

    for raw_path in changed:
        path = pathlib.PurePosixPath(raw_path)
        if not is_evaluator_inert(path):
            return Decision(
                needed=True,
                reason=f"{path.as_posix()} can move the evaluator comparison",
            )

    return Decision(
        needed=False,
        reason=(
            "no changed path can make main's pipeline and the candidate's "
            "disagree, so every verdict would match by construction"
        ),
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

    changed = _read_changed_paths(args.changed_from)
    pipeline = pipeline_tests_needed(changed)
    game = game_tests_needed(changed)
    evaluator = external_acceptance_needed(changed)

    pipeline_verdict = "true" if pipeline.needed else "false"
    game_verdict = "true" if game.needed else "false"
    evaluator_verdict = "true" if evaluator.needed else "false"
    print(
        f"ci_surfaces: pipeline jobs needed={pipeline_verdict} -- {pipeline.reason}"
    )
    print(f"ci_surfaces: game job needed={game_verdict} -- {game.reason}")
    print(
        "ci_surfaces: external-acceptance job needed="
        f"{evaluator_verdict} -- {evaluator.reason}"
    )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"pipeline_needed={pipeline_verdict}\n")
            handle.write(f"game_needed={game_verdict}\n")
            handle.write(f"evaluator_needed={evaluator_verdict}\n")
            handle.write(f"pipeline_reason={pipeline.reason}\n")
            handle.write(f"game_reason={game.reason}\n")
            handle.write(f"evaluator_reason={evaluator.reason}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
