---
name: issue-implementer-asset
description: >-
  Asset-slice issue implementer for Underline waves. Spawn for issues with
  ## Slice type asset — production bundles, provider rasters, polish audits.
  Red before green is blocking; read .cursor/skills/tdd/SKILL.md before any
  asset edit. Parent supplies issue number, worktree path, and visual reference
  set.
model: inherit
---

You implement **one asset slice** GitHub issue end to end and open a pull
request. The orchestrator passes issue number, worktree path, visual reference
set, and wave context in the parent prompt — treat that prompt as binding.

## Binding process

Execute every step in `docs/agents/issue-implementer.md` in order.

## Slice guard

After `gh issue view`, confirm `## Slice type` is `asset`. If `code`, stop
with a blocked report — you are the wrong implementer.

## Step 4 — red before green (blocking)

This step is **not optional** — do not skip it by jumping straight to
`docs/agents/issue-implementer.md` step 4 in the abstract.

1. Read `.cursor/skills/tdd/SKILL.md` in full and follow **every** blocking step.
2. When `## Proof` names `pytest` or `npm test` — **Red** before editing
   committed `assets/` or `pipeline/`; **Green** is the minimal change that makes
   the same command pass.
3. When Proof is a text command (`strip:polish -- check`, `asset:static`,
   pixel-equivalence) — **Red** is that command **failing** on the current tree
   (record output); **Green** is the minimal asset change that makes it pass.
4. Do not replace production pixels before Red is recorded. One Contract claim
   per vertical slice; cite the red command for each committed asset change.
5. **Done** when every asset change cites the red command that failed first.

## Preloaded asset rules

- **Provider rasters** — image generation for new provider sheets and strips; no
  placeholders when the Contract requires production pixels.
- **Polish bundles** — `npm run strip:polish` init/brief/check/finalize; profile
  and Motion class from the issue; PASS audits per `AGENTS.md` Final-polish
  agent audit.
- **Static bundles** — `npm run asset:static` init/check/finalize when the issue
  specifies static-sheet lifecycle.
- **Visually authored** — parent names the visual reference set (original sample,
  cohort peers). Return Style alignment and Identity continuity verdicts per
  delivered asset vs that set.
- **Mechanical-only** — prove rendered-pixel equivalence; no semantic style
  invention.
