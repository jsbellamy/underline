# Domain Docs

How engineering skills should consume this project's domain documentation.

## Before exploring, read these

- `CONTEXT.md` at the project root
- `docs/strip-acquisition-contract.md` — the authority for motion classes,
  gates, and budgets
- Relevant decisions under `docs/adr/`

If a file or directory does not exist, proceed silently. Domain-modeling
workflows create documentation lazily when terms or decisions are resolved.

## Layout

This is a single-context project:

```text
/
├── CONTEXT.md
├── docs/adr/
├── docs/strip-acquisition-contract.md
├── src/          # the game (TypeScript)
└── pipeline/     # the asset pipeline (Python)
```

`src/` does not exist yet, and the pipeline currently lives at
`prototype/strip-coherence/` with its tests in `tests/`.

## Use the glossary's vocabulary

Use terms as defined in `CONTEXT.md` in issues, proposals, tests, and code. Do
not drift to synonyms the glossary explicitly avoids. A missing term may indicate
either unsuitable language or a gap to resolve through domain modeling.

## Flag ADR conflicts

Surface any proposal that contradicts an existing ADR rather than silently
overriding the earlier decision.

## Do not import a sibling project's domain

The pipeline temporarily shares recovery *code* with a sibling checkout. It does
not share vocabulary or contracts, and that project's contracts do not govern
here. Define terms in `CONTEXT.md` rather than deferring to another repo.
