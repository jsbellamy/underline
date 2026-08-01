---
name: tdd
description: >-
  Test-driven development for Underline code slices. Use when implementing a
  code issue, following issue-implementer step 4, or when red-green-refactor is
  required. Enforces one failing test before any production or asset edit.
---

# TDD (Underline code slices)

Red → green in **vertical slices**. Seams are fixed in `docs/agents/code-style.md` —
no per-session seam negotiation; issue implementers never ask the user.

## Blocking rule

**Do not edit** `pipeline/`, `src/`, or committed paths under `assets/` until
step **Red** below has a recorded failing `pytest` (or `npm test` for TS-only
slices). Reading code and writing tests is allowed before Red completes.

Exploration scripts (`python3 <<`, one-off probes) are allowed only to choose
the seam and expected value — delete them before Green; they are not the
implementation.

## Loop (repeat per Contract claim or vertical slice)

### Red

1. Pick **one** seam from `docs/agents/code-style.md` that proves the next claim.
2. Write **one** test that reads as a behavior spec in `CONTEXT.md` vocabulary.
3. Run it in isolation:

   ```bash
   PYTHONPATH=. python3 -m pytest -q path/to/test_file.py::test_name
   ```

4. **Stop if it passes** — wrong seam, tautological assertion, or scope already
   done. Fix the test before continuing.
5. Record the failing command and the assertion message (commit message or PR
   notes). This is the **red evidence** for the slice.

### Green

1. Change only `pipeline/`, `src/`, or `assets/` needed for **this** test.
2. Re-run the same pytest command until green.
3. Do not start the next slice until this test passes.

### Next slice

Return to **Red** for the next Contract claim. Do not batch-write tests or
batch-edit production code.

## Rules

- **One test, one minimal change** per cycle — no horizontal slicing.
- **Independent expected values** — literals, worked examples, or pre-slice
  fixtures; never recompute the assertion with the code under test.
- **Characterization** (`tests/test_gates_characterization.py`) — never
  re-baseline silently; explain diffs in the PR body.
- **Done** when every production/asset change in the PR cites the red command
  that failed first for its slice.

## Asset-heavy code slices

When the Contract proof is bundle bytes or `strip:polish -- check`, the first
Red test still comes **before** editing those bytes — assert the defect (e.g.
off-palette cells, failing gate, wrong hash) against the **current** tree. Green
is the migration or pipeline fix that makes that test pass.

## Before publish

Run `npm run test:changed` (or `npm test` when the mapping is ambiguous). CI
owns the full suite on the PR.
