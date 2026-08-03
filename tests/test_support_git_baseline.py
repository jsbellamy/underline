"""Behavioral proof for tests.support.git_baseline (#328 CI fix)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.support import git_baseline


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT
    )


def _repo_with_main(root: Path, contents: str = "baseline\n") -> Path:
    """An origin repo whose `main` branch holds `assets/palette.json`."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "--initial-branch", "main", "--quiet")
    _git(root, "config", "user.email", "ci@example.com")
    _git(root, "config", "user.name", "CI")
    asset = root / "assets" / "palette.json"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_text(contents, encoding="utf-8")
    _git(root, "add", "assets/palette.json")
    _git(root, "commit", "--quiet", "-m", "baseline")
    return root


def _clone_without_local_main(origin: Path, dest: Path) -> Path:
    """A clone checked out on a topic branch, with no local `main` — the PR CI shape."""
    _git(dest.parent, "clone", "--quiet", str(origin), str(dest))
    _git(dest, "config", "user.email", "ci@example.com")
    _git(dest, "config", "user.name", "CI")
    _git(dest, "checkout", "--quiet", "-b", "topic")
    _git(dest, "branch", "--quiet", "-D", "main")
    return dest


def test_resolves_local_main_when_the_branch_is_checked_out(tmp_path):
    repo = _repo_with_main(tmp_path / "repo")

    assert git_baseline.resolve_baseline_rev(repo) == "main"


def test_resolves_origin_main_when_only_the_remote_tracking_ref_exists(tmp_path):
    origin = _repo_with_main(tmp_path / "origin")
    clone = _clone_without_local_main(origin, tmp_path / "clone")

    assert git_baseline.resolve_baseline_rev(clone) == "origin/main"


def test_raises_when_no_candidate_ref_resolves(tmp_path):
    repo = tmp_path / "orphan"
    repo.mkdir()
    _git(repo, "init", "--initial-branch", "topic", "--quiet")

    with pytest.raises(git_baseline.BaselineRefError) as exc_info:
        git_baseline.resolve_baseline_rev(repo)

    assert "origin/main" in str(exc_info.value)


def test_reads_the_baseline_blob_from_the_resolved_ref(tmp_path):
    origin = _repo_with_main(tmp_path / "origin", contents='{"palette": 1}\n')
    clone = _clone_without_local_main(origin, tmp_path / "clone")
    (clone / "assets" / "palette.json").write_text("drifted\n", encoding="utf-8")

    assert (
        git_baseline.read_baseline_bytes(clone, "assets/palette.json")
        == b'{"palette": 1}\n'
    )
