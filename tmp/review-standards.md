# Standards review — cell-author generation mode

## Documented-standard violations

**STD-001 — Speculative dead hook** (`docs/agents/code-style.md`, “Every abstraction… is needed by the implementing issue’s acceptance criteria”)

`_resolve_cell_author_base_bundle` is defined but never called; it only raises with a placeholder message. Remove it or wire it into the replay path the issue describes (embedded base release frames).

```python
def _resolve_cell_author_base_bundle(...) -> Path:
    del bundle_root, manifest, ledger
    raise InvalidBundleError(
        "cell-author replay uses embedded base release frames",
        reason_code="missing_base_bundle",
    )
```

**STD-002 — Hardcoded palette binding** (`docs/agents/code-style.md`, speculative generality)

`_bundle_master_palette_rgb_set` forces `palette_id = "first-room"` for every cell-author bundle instead of reading a provenance-bound palette. Walk/swing cell-author bundles (dwarf-miner profile) are not issue-sanctioned to assume first-room; palette exactness is supposed to run unchanged (C5).

**STD-003 — Incomplete machine-readable CLI failures** (`docs/agents/code-style.md`, “A validator emits a machine-readable report… on both the pass and fail paths”)

`_handle_init_cell` emits JSON only for `InitializationRejectedError`. With `--json`, `BundleExistsError`, `ValueError`, and post-init `check_bundle` failures still print stderr only. `_handle_acquire` likewise swallows `AssetAcquisitionError.reason_code` on the `--json` path despite adding that field — agents cannot read `provider_attempt_claims_cell_author` from stdout.

**STD-004 — Test names describe implementation, not behavior** (`docs/agents/code-style.md`, test naming)

Examples: `test_cell_author_provenance_schema_and_field_set`, `test_init_cell_creates_providerless_v2_bundle`, `test_pose_plan_schema_bound`. Prefer contract vocabulary (“a cell-authored bundle rejects a provider attempt”, “manifest mode tamper fails closed”).

## Baseline smells

**SMELL-001 — Dead Code** (Fowler): `_resolve_cell_author_base_bundle` (same hunk as STD-001).

**SMELL-002 — Duplicated Code** (Fowler): `MOTION_POSE_PLAN_SCHEMA` is duplicated in `pipeline/final_polish.py` and `tests/support/polish_bundle.py`; test support re-exports a production constant.

**SMELL-003 — Long Method** (Fowler): `initialize_cell_authored_bundle` (~250 lines) interleaves validation, temp-dir assembly, and manifest writes; readable but dense. ADR 0006 endorses a deep `final_polish.py` façade, so this is judgement-only, not a breach.
