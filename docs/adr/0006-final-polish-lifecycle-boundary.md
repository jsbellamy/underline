# ADR 0006: Final-polish lifecycle boundary

## Status

Accepted (2026-08-01, issue #256).

## Context

After deleting the never-shipped `final-polish-bundle/0` manifest schema (#254),
a deferred proposal suggested extracting seven attestation and Attempt-ledger
helpers from `pipeline/final_polish.py` into a separate module. The module is
large and symbol-scoped anchors already bound agent read cost; the question is
whether line count alone warrants a split.

### Findings

Measurement at commit `52801a2` (immediately after the legacy-0 deletion):

1. **`pipeline/final_polish.py` is 2,254 lines** (`git show 52801a2:pipeline/final_polish.py | wc -l`).

2. **Four public lifecycle functions** are the module's production surface:
   `load_polish_brief`, `initialize_bundle`, `check_bundle`, and `finalize_bundle`.
   No other module-level `def` lacks a leading underscore.

3. **62 private functions** (`git show 52801a2:pipeline/final_polish.py | rg '^def _' | wc -l`).

4. **The proposed extraction cluster has no production caller outside
   `pipeline/final_polish.py`.** Repo-wide reference inspection finds these
   seven helpers only in that file:
   `_load_legacy_bundle_allowlist`, `_legacy_bundle_allowed`,
   `_project_store_rows_to_ledger`, `_build_legacy_single_row_attempt_ledger`,
   `_build_initial_attempt_ledger`, `_ledger_attestation_view`,
   `_resolve_bundle_attestation`.

5. **`pipeline.asset_acquire` is the Attempt store, not a second consumer of a
   final-polish attestation API.** `record_asset_attempt` writes
   `acquisition-controls/attempts.jsonl`; `load_asset_attempts` reads it.
   Final polish projects those rows into bundle-local ledgers during `init` and
   validates them during `check` — it does not expose a shared attestation
   module for other pipeline stages to import.

6. **ADR 0004 retains the dual lifecycle paths** that these helpers implement:
   `final-polish-bundle/1` with `acquisition-controls/legacy-bundles.json` and
   `attestation.state: "legacy"` for pre-attestation acquisitions, versus `/2`
   attestation from the Attempt store. The helpers are tightly coupled to
   final-polish exception types, data types, constants, JSON/hash helpers, and
   bundle-path rules defined in the same module.

## Decision

`pipeline/final_polish.py` remains **one intentionally deep lifecycle façade**.
The proposed extraction is rejected: it would relocate a private cluster
without creating a second adapter, while retaining substantial coupling to
final-polish internals that a new module would still import from the façade or
duplicate.

**Read cost** is addressed by symbol-scoped anchors (`npm run agents:anchors`,
issue `## Touches` manifests) — not by splitting on line count alone.

**Reconsider extraction only when either:**

1. a second production module needs a stable attestation API; or
2. the shared exception/type boundary is deliberately redesigned.

Until then, attestation and Attempt-ledger logic stays private to final polish.

This ADR cites [ADR 0004](0004-pre-attestation-acquisitions.md) and preserves
`final-polish-bundle/1`, `acquisition-controls/legacy-bundles.json`, and
`attestation.state: "legacy"`. This slice records the boundary only — no runtime
behavior, verdict, schema, reason code, CLI behavior, test behavior, or
checked-in bundle changes.

## Consequences

### Positive

- Future refactors cannot treat `final_polish.py` line count as an automatic
  extraction trigger; the reconsideration gates are explicit.
- The four-function public lifecycle surface is named, so callers and issue
  manifests know where the seam is.
- Symbol-scoped anchors remain the standing response to agent read cost without
  fragmenting a module that has no second consumer.

### Negative

- `pipeline/final_polish.py` stays large (~2,254 lines at measurement) and
  continues to mix lifecycle orchestration with attestation/ledger helpers.
- Agents that ignore anchors still pay whole-file read cost on this module.

### Limit

This ADR does not redesign the attestation type boundary or add a second
production consumer. When either reconsideration trigger fires, a superseding
ADR should record the new module shape; `docs/adr/README.md` forbids editing
history in place.
