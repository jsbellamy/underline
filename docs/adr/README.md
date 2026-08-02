# Architectural decision records

Underline records durable architecture choices here as short ADRs. Each file is
numbered sequentially: `NNNN-kebab-title.md` (for example
`0001-pitch-slicing.md`). Use four-digit zero padding so lexical sort matches
decision order.

Write an ADR when a choice would otherwise be re-litigated in review — when the
code already embodies a trade-off future readers are likely to question, not for
every implementation detail. Keep entries brief: Status, Context, Decision, and
Consequences. If an ADR needs scrolling, the content belongs in a design doc
instead. When a decision changes, add a new ADR that supersedes the old one; do
not delete history.

| ADR | Title |
|-----|-------|
| [0001](0001-two-scale-mining-grid.md) | Two-scale mining grid (16×16 Rendering Tile + 32×32 Mineable Block) |
| [0002](0002-palette-exact-canonical-identity.md) | Palette-exact canonical identity (expand–contract migration, contracted) |
| [0003](0003-swing-action-canvas.md) | Swing action canvas (24×24, canonical origin at column 4) |
| [0004](0004-pre-attestation-acquisitions.md) | Pre-attestation acquisitions (retain `/1` and legacy allowlist) |
| [0005](0005-isolation-sweep-throughput-target.md) | Isolation-sweep throughput target (`wall_s` ≤ 180s on CI, per-file ceiling retired) |

Earlier decisions settled only in `docs/strip-acquisition-contract.md` or
`prototype/strip-coherence/NOTES.md` should be promoted here when they start
being re-argued.
