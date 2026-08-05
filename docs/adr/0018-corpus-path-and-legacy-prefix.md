# ADR 0018: Corpus path and legacy prefix

## Status

Accepted (2026-08-05, issue #493).

## Context

The strip-coherence evidence suite lived under `prototype/strip-coherence/`
while the production gate library shipped in `pipeline/`. The `prototype/` name
implied throwaway exploration, but the corpus and its proof runners are
permanent regression evidence: budgets, separation claims, and adversarial
mutations all cite them. Issue #492 moved the tree to `corpus/strip-coherence/`.

Hash-bound Promotion packets and gate-control records still embed paths from
before the move. ADR 0004 established that frozen acquisition evidence is not
re-signed when a resolver can map recorded paths onto the live tree.

The npm script names `prototype:strip:*` predate the path move. They are frozen
by `pipeline/gate_verification.py`'s `REQUIRED_COMMANDS` and the checked-in
verification records that gate repository health.

## Decision

1. **Live corpus location.** The standing corpus and its proof runners live at
   `corpus/strip-coherence/`. Documentation and operator prose cite this path;
   the old `prototype/strip-coherence/` name is retired for live references.

2. **Frozen recorded paths.** Paths embedded in hash-bound Promotion packets and
   gate-control evidence stay exactly as recorded. `pipeline/corpus_paths.py`
   resolves them through `LEGACY_CORPUS_PREFIXES` (`prototype/strip-coherence`)
   onto `corpus/strip-coherence/` rather than re-signing or rewriting frozen
   artifacts, per ADR 0004.

3. **Frozen script names.** The `prototype:strip:*` npm script names are
   unchanged. `REQUIRED_COMMANDS` and the checked-in verification records match
   on those strings; renaming would require a coordinated verification
   re-baseline without changing what the runners measure.

## Consequences

### Positive

- Documentation matches the filesystem after #492; the corpus is no longer
  labelled as a prototype.
- Frozen gate-control and Promotion evidence stays byte-stable; only the
  resolver bridges old path strings to the live tree.
- Operators keep the same `prototype:strip:*` commands recorded in verification
  manifests.

### Negative

- Two names coexist: `corpus/strip-coherence/` for live work and
  `prototype/strip-coherence` inside frozen records and `LEGACY_CORPUS_PREFIXES`.
  New prose must not cite the legacy prefix except when explaining the resolver.
- The `prototype:strip:*` script prefix remains a historical misnomer until a
  future issue re-baselines `REQUIRED_COMMANDS` and verification records.

## Rejected alternative

**Re-sign every Promotion packet and gate-control record with the new path.**
Rejected because ADR 0004 treats frozen acquisition evidence as immutable; a
path rewrite would invalidate hash-bound packets and force a full promotion
re-audit without changing any measured gate outcome.
