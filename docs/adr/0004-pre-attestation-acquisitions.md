# ADR 0004: Pre-attestation acquisitions

## Status

Accepted (2026-08-01, issue #254).

## Context

Four checked-in Polish Bundles remain on manifest schema `final-polish-bundle/1`
because their provider bytes were acquired before attested intake existed. The
never-shipped legacy-0 manifest schema is deleted in #254; `/1` and the
digest-pinned allowlist are retained deliberately.

### Findings

1. **No production Attempt store.** `acquisition-controls/` holds only
   `.gitkeep` and `legacy-bundles.json`. There is no `attempts.jsonl` or raw
   Attempt archive. Bundles on the allowlist report `attestation.state: legacy`
   from `_legacy_bundle_allowed`; idle, walk, and lantern are listed today.

2. **`/2` requires `animation-strip-provenance/0`.** Reaching `/2` needs a
   provenance sidecar on that schema. The four shipped sidecars are
   `gate-control-provenance/0` (dwarf idle, walk, swing) and
   `provider-provenance/0` (lantern). Every one lacks the fields `/2` init
   validates — including `model` and `generation_mode`; lantern also lacks
   `specification_id` and `attempt_id`.

3. **`model` was never recorded.** The provider model that produced the art is
   not present in any sidecar and cannot be recovered by inspection of the
   bytes.

4. **`record_asset_attempt` derives every attested field.** The intake function
   in `pipeline/asset_acquire.py` derives `attempt_id`, timestamps, hashes, and
   dimensions from bytes observed at call time. Backfilling historical Attempts
   through it would require widening the signature against its stated invariant.

## Decision

Retain `final-polish-bundle/1` and `acquisition-controls/legacy-bundles.json`
for Polish Bundles that cannot be re-acquired under attested intake. The
allowlist shrinks only when a bundle is re-acquired and its entry is deleted —
never by backfill or synthetic provenance.

**Exit path for walk and swing:** issue **#126** replaces dwarf walk with a `/2`
Bundle; issue **#127** replaces dwarf swing with a `/2` cell-author Bundle
recorded through attested intake. When each lands, that bundle leaves `/1` and
its allowlist entry is deleted by that issue.

**No replacement issue yet for dwarf idle and lantern.** Those two bundles are
what this ADR is actually about: they cannot reach `/2` without fabricating
provenance nobody observed.

Delete the legacy-0 manifest schema from `BUNDLE_SCHEMAS`; manifests declaring it
are rejected as unknown schema.

## Consequences

### Positive

- The accepted schema set matches what exists: `{/1, /2}` only.
- A proposal to delete `/1` or the allowlist must first show dwarf idle and
  lantern have been re-acquired under attested intake — not that the code paths
  look vestigial.
- Walk and swing have named exit issues; idle and lantern carry an explicit
  retention record until re-acquisition is scoped.

### Negative

- `check` and `finalize` keep dual paths: `/2` attestation versus `/1` legacy
  rules.
- `acquisition-controls/legacy-bundles.json` remains a manual, digest-pinned
  surface until bundles graduate through re-acquisition.

### Limit

This ADR does not migrate any checked-in bundle bytes. Moving walk or swing to
`/2` is #126/#127; idle and lantern stay on `/1` until separately re-acquired.
