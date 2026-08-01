"""Shared temporary-store and Attempt-recording support for final-polish tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pipeline import asset_acquire as aa


def acquisition_store_env(store_root: Path) -> dict[str, str]:
    return {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}


def bundle_store_root(bundle: Path) -> Path | None:
    store_root = bundle.parent / "acquisition-controls"
    if (store_root / "attempts.jsonl").is_file():
        return store_root
    return None


def bundle_store_env(bundle: Path) -> dict[str, str] | None:
    store_root = bundle_store_root(bundle)
    if store_root is None:
        return None
    return acquisition_store_env(store_root)


@contextmanager
def bundle_store_env_context(bundle: Path) -> Iterator[Path | None]:
    store_root = bundle_store_root(bundle)
    if store_root is None:
        yield None
        return
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        yield store_root


def record_store_attempt(
    store_root: Path,
    provider_path: Path,
    specification_id: str,
    *,
    motion_class: str,
    generation_mode: str,
    acquiring_agent: str,
    prompt_text: str,
    repo_root: Path,
    outcome: str = "accepted",
    rejection_reason: str | None = None,
    reference_image_sha256: str | None = None,
    edit_source: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    record_kwargs: dict[str, object] = {
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "acquiring_agent": acquiring_agent,
        "prompt_text": prompt_text,
        "outcome": outcome,
        "rejection_reason": rejection_reason,
        "repo_root": repo_root,
    }
    if reference_image_sha256 is not None:
        record_kwargs["reference_image_sha256"] = reference_image_sha256
    if edit_source is not None:
        record_kwargs["edit_source"] = edit_source
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        row = aa.record_asset_attempt(
            provider_path,
            specification_id,
            **record_kwargs,
        )
    stored_provider_path = store_root / row["raw_path"]
    return row, stored_provider_path
