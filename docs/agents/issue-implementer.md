# Issue implementer

Implement exactly one Underline GitHub issue end to end and open a pull request.
Pass the issue number to this agent. Work in an isolated worktree when the
runtime supports worktrees.

## Process

1. Read `AGENTS.md` and `CONTEXT.md`. Follow their pointers only where they apply
   to the issue; do not load every doc by default. Use the glossary's vocabulary
   in code, tests, commits, and the pull request.
2. Fetch the issue with `gh issue view <N>` (use `/opt/homebrew/bin/gh` if `gh`
   is not on `PATH`). Require `## Slice type`, `## Delta`, `## Contract`,
   `## Touches`, `## Proof`, and `## Blocked by`; `## Invariants` is optional.
   If a required section is missing, stop with a blocked report. Use Delta as the
   current → target hypothesis, Contract claims as the complete scope, Proof
   mappings as the required evidence, and Invariants as preserved boundaries. The
   `## Touches` `read:` lines are the bounded context set: read each named anchor
   before editing, treating `authority` as normative, `seam` as the interface to
   join, and `pattern` as an example rather than a specification. Expand beyond an
   anchor only when required. The manifest is expected scope, not a
   straitjacket: justify each out-of-manifest file in the PR body.

   Resolve the manifest with one command rather than opening the files:

   ```bash
   npm run --silent agents:anchors -- --issue <N>
   ```

   It prints each anchored symbol as numbered source and reports unanchored
   directories and binary assets for the appropriate inspection tool. A named
   text anchor that does not resolve is a manifest defect; return a structured
   blocker so the orchestrator can repair it rather than opening the whole file.
   `AGENTS.md` § Reading discipline governs: a whole-file read of a core module
   is a deliberate choice that belongs in the PR body, not a default.

   Audit the manifest's catch sites once before editing. For every modified
   public pipeline entry point that can raise, trace its callers; when a CLI
   reaches it, the read/write set includes that handler and its test module even
   when the exception type itself is unchanged. Finding either at review time
   means reworking at peak context.
3. Create `issue-<N>-<slug>` from `main`.
   For every before/after Polish Bundle Proof, record the exact starting revision
   with `git rev-parse HEAD`, then run this read-only baseline in the worktree:

   ```bash
   npm run --silent strip:polish -- check <bundle> --summary-json
   ```

   Keep the revision and complete summary output as authoritative pre-slice
   evidence.
4. Implement test-first at the seams in `docs/agents/code-style.md` (that doc is
   the standing seam agreement). **Cursor:** read `.cursor/skills/tdd/SKILL.md`
   and follow its blocking loop before any production or asset edit. **Other
   runtimes:** invoke `/tdd`, or read `~/.claude/skills/tdd/SKILL.md`. Run
   focused test files during implementation; run
   `npm run test:changed` before publishing — it selects the tests the diff
   against `main` actually touches (`scripts/select_changed_tests.py`) and
   widens to the whole suite whenever the mapping is ambiguous. CI
   (`.github/workflows/ci.yml`) owns the full suite and the per-file isolation
   sweep on every PR, so `test:changed` is the local gate, not a substitute for
   CI passing.
   - **TypeScript changes** — `npm run typecheck` green before publishing. No
     TypeScript exists yet, so the script does not exist either: the slice that
     lands `src/` adds it to `package.json`. Keep
     the event vocabulary append-only, the snapshot serializable, and randomness
     in seeded streams so a pinned seed reproduces exact numbers.
   - **Asset pipeline changes** to gates, slicing, or budgets are governed by
     `docs/strip-acquisition-contract.md`. A number in `MOTION_CLASSES` and the
     same number in the contract move together, in the same commit, or the change
     is incomplete. Re-derive with `npm run prototype:strip:alpha-budgets` — the
     runtime oracle — and cite its output; never hand-edit a measured table.
     `npm run prototype:strip:derive-budgets` is the historical pre-α baseline
     only, not evidence for a production Budget change.
   - **Characterization diffs** (`tests/test_gates_characterization.py`) are
     never silently re-baselined. If your change moves a pinned number, explain
     which change moved it and why, in the PR body.
   - **New gates** arrive with the `adversarial.py` mutation that proves they
     fire, and with the negative control they separate against.
   - Do not add good corpus strips to strengthen a separation claim; under the
     current derivation rule they can only widen budgets toward the fixed
     controls.
   - **Discovery checkpoint** — within 10 tool-call round trips after loading the
     issue, either run the first red-capable command or return a structured
     discovery blocker. The blocker names the missing seam or prerequisite,
     evidence inspected, and the smallest next issue or issue edit that would
     unblock the slice. Do not continue open-ended grep/read loops past this
     checkpoint.
5. Before publishing, create the canonical **completion matrix** as a scratch file in the
   worktree (for example `tmp/completion-matrix.md`, untracked) with columns
   `Claim`, `Verdict`, and `Evidence`, containing one row per Contract claim ID
   without paraphrasing the claim or copying its Proof mapping. This path is the
   single source of truth: the Spec reviewer updates its provisional rows in
   step 8, and steps 9–11 consume that exact file rather than authoring another
   table. For each row, satisfy the
   issue's Proof mapping with specific evidence: a command and the row of its
   output that shows the fact, or a code location. Every claim in this repo is
   provable by a command that emits text — `npm test`,
   `npm run prototype:strip:corpus`, `:adversarial`, `:alpha-budgets`,
   `:derive-budgets`, `:displacement`, `:sharpness`. If a claim is not visible to any of them, say so
   in the row rather than substituting a weaker proof.
   If a claim cannot be evidenced at all, or is falsified by what you found
   while implementing, mark its row `unmet` (or `needs manual`) — never `met`,
   and never `PARTIAL`; that is not a matrix verdict, the vocabulary stays
   exactly `met` / `unmet` / `needs manual`, and a claim that is only partly
   satisfied is `unmet`. A claim that is not `met` has exactly one outcome
   available: return a structured blocked report to the calling orchestrator,
   or open a **draft** pull request whose title is prefixed `Diagnostic:` and
   that does not carry `Closes #<N>`. "Editorial disposition" is what the
   orchestrator or a human decides after receiving that blocked report or
   draft — it is never a reason for this agent to continue toward a completion
   PR.
6. Commit only the issue's changes. Let any commit hooks run; never bypass them.
   For every before/after Polish Bundle Proof, record the resulting revision with
   `git rev-parse HEAD`, rerun the same `check <bundle> --summary-json` command,
   and preserve that SHA/payload pair beside the pre-slice evidence. Verify the
   observed delta against the issue's expected post-slice delta before review.
7. When the issue requires Promotion-verification gate audits, **before**
   `/code-review`:
   - Build `packet.png` and `packet.json` mechanically for each promotion review
     directory; do not write `review--*.json` yet.
   - **Cursor:** invoke the `gate-blind-review` subagent once per promotion for
     review 1 (pass only `packet.png` and the §10 question/panel/metric/Budget/C
     from the issue or spec). Write `review--01.json` from its output via
     `write_audit_record`.
   - Build `review-input--02.json` mechanically with
     `blinded_packet_for_second_review` / `write_second_review_input` (not
     delegated to the review subagent).
   - **Cursor:** invoke `gate-blind-review` again in a **fresh** session for
     review 2 (only `review-input--02.json` and `packet.png`). Write
     `review--02.json` and run `validate_review_dir` until `"ok": true`.
   - **Non-Cursor:** spawn an equivalent isolated visual reviewer per audit at
     the pin in `.claude/CLAUDE.md`; same blindness rules.
   Never author both audits in one subagent session.
8. Review your own work before publishing: run `/code-review` with `main` as the
   fixed point (`git diff main...HEAD`) and the live issue body as the Spec
   source, passing the completion matrix file in. The Spec reviewer owns that
   file during review: it updates every row to its reviewed `met` / `unmet` /
   `needs manual` verdict and evidence pointer satisfying the Proof mapping. The
   Standards reviewer never writes it. If the runtime does not expose `/code-review`,
   run the equivalent Standards and Spec reviews as parallel sub-agents. On
   Cursor, use `code-review-standards` and `code-review-spec` (not
   `generalPurpose`).
   Have each reviewer **write its report to a file** under the worktree and
   return only that path and compact finding IDs; the Spec reviewer also returns
   the unchanged completion-matrix path. Read only the matrix rows and the report
   sections named by blocking finding IDs during rework. Step 10 posts the files;
   report prose never has to enter this agent's context, and a report that is
   never retyped cannot stop being verbatim.
   Rework every Spec finding, every `unmet` row, and every hard Standards
   violation (a documented repo-standard breach), then commit and re-run the
   review until those are clear. Judgement-call Standards smells need no rework —
   carry them into the verdict table for the merge decision.
9. This step applies only when the reviewed completion matrix has no `unmet`
   and no `needs manual` rows. If any row is `unmet` or `needs manual`, follow
   step 5's diagnostic path instead — a structured blocked report, or a
   `Diagnostic:`-prefixed draft PR that does not carry `Closes #<N>` — and stop
   here rather than proceeding with the rest of this step. Otherwise, push with
   `git push -u origin <branch>`, then create a pull request whose body
   includes a summary, verification details, the reviewed completion matrix file,
   and `Closes #<N>`. Assemble the body as a file and pass it with
   `gh pr create --body-file`, concatenating the matrix file rather than
   retyping its rows.
10. Post the review to the PR with `gh pr comment <N> --body-file <path>`: the
   **verbatim** Standards and Spec sub-agent output under separate headings, plus
   the reworked findings and the commits that resolved them. Build that file by
   concatenating the report files the reviewers wrote in step 8, followed by the
   canonical completion-matrix file — never by retyping them. Post what the
   reviewers wrote: never a summary of your own review, and never a report
   rewritten to read better than the one you received.
11. Report the PR URL, what was built, test results, and the exact contents of
    the canonical **verdict table**: one row per Contract claim ID
    with its `met` / `unmet` / `needs manual` verdict and evidence pointer
    satisfying the Proof mapping, the count of blocking findings before and after
    rework, any unreworked judgement-call smells, the comment URL, and anything
    deliberately left out of scope. The full reports stay in the PR comment — the
    report you return is the table, not the reviews.

## Constraints

- An **asset slice** may not modify pipeline code, gate code, or checked-in
  characterization tests — the directories `pipeline/`, `gate-controls/`, and
  `tests/`. The one exception is a test that exists solely to characterize the
  new asset's own Bundle, declared in the issue's `## Touches` manifest as a
  `create:` entry. If an asset slice cannot pass without touching one of those
  directories outside that exception, that is a finding: stop, report it as a
  blocked slice, and name the smallest code issue that would unblock it. The
  asset slice resumes after that issue merges. A slice that edits the
  mechanism judging its own artifact has not been judged.
- This agent has no direct user-interaction channel. Never ask the user a
  question or wait for user approval. Resolve routine decisions from the issue
  and repository contracts. When progress is impossible, stop and return a
  structured blocked report to the calling orchestrator with the blocking
  condition, evidence, attempts made, and recommended next choice; the
  orchestrator owns any human interaction.
- The worktree root is the only writable tree. Use absolute paths under that root
  for every Write/StrReplace/edit — a relative path resolves against the primary
  multi-root root, not your worktree. Set shell `cwd` to the worktree root. Never
  write under a sibling checkout or the primary multi-root workspace root when it
  is not this worktree.
- Grid-recovery primitives are vendored in `pipeline/recovery.py`; the repo needs
  no sibling checkout to run. Never edit that copy in place — behaviour changes
  belong upstream in Nightglass and are re-vendored. If a primitive needs to
  change, stop and report it as a cross-repo blocker.
- Simulation and gates stay deterministic: same input, same output. Time and RNG
  are injected; no wall-clock and no ordering-dependent results.
- An issue body labeled **interim** is deliberate: build the interim as specified
  and leave the replacement to the named later issue.
- Do not modify another issue's scope, work directly on `main`, or merge the pull
  request yourself.
- On **Cursor**, blind gate reviews use the `gate-blind-review` subagent (model
  pinned in `.cursor/agents/gate-blind-review.md`). On other runtimes, follow
  `.claude/CLAUDE.md` for the blind-review pin.
