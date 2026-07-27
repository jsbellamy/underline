# Underline — Claude Code

**`AGENTS.md` is the source of truth. Read it first.** This file only adds the
Claude-Code-specific layer; everything not restated here is governed by
`AGENTS.md`. When you change shared guidance (domain, architecture, conventions,
workflow), edit `AGENTS.md` or the docs it routes to, not this file.

## Skills

- **`/tdd`** — invoke explicitly for every code change, TypeScript or pipeline,
  then work test-first at the seams in `docs/agents/code-style.md` (that doc is
  the standing seam agreement, so the skill's seam question is already answered).

## Subagents

- For issue implementation, spawn a general-purpose subagent pinned to
  **Sonnet at high effort** and tell it to read and follow
  `.agents/issue-implementer.md`. Never override the model upward and never run
  it above high effort. The provider-neutral file is the single source of truth
  for the workflow; the model pin exists only in this Claude-only instruction
  layer so other runtimes cannot discover a Sonnet-pinned agent definition.
- **Blinded gate reviews** (issue-implementer step 7): each Promotion-verification
  audit spawn is a **fresh** general-purpose subagent at **Sonnet, reasoning ≤
  high** — same bar as `/code-review` Spec reviewers, not the implementer's model
  pin. Match the blindness rules in `.cursor/agents/gate-blind-review.md` (that
  file is the prompt spec; Claude does not use its Cursor `model` frontmatter).


## Toolchain notes

- If `gh` is not on `PATH`, it is at `/opt/homebrew/bin/gh`.
- The asset pipeline needs Python 3 with Pillow and NumPy (`requirements.txt`).
  Until it is promoted under `pipeline/`, it also resolves recovery primitives
  from a sibling checkout, so it will not run from a standalone clone.
