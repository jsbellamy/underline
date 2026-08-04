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
| [0003](0003-swing-action-canvas.md) | Swing action canvas (24×24, canonical origin at column 1) |
| [0004](0004-pre-attestation-acquisitions.md) | Pre-attestation acquisitions (retain `/1` and legacy allowlist) |
| [0005](0005-isolation-sweep-throughput-target.md) | Isolation-sweep throughput target (`wall_s` ≤ 180s on CI, per-file ceiling retired) |
| [0006](0006-final-polish-lifecycle-boundary.md) | Final-polish lifecycle boundary |
| [0007](0007-swing-cell-author-acquisition.md) | Swing Cell-author acquisition |
| [0008](0008-anatomy-first-character-acquisition.md) | Anatomy-first character acquisition (compile/pose seam; amends 0007 for walk) |
| [0009](0009-vendored-pane-dock-shell.md) | Vendored Pane+Dock shell from Nightglass |
| [0010](0010-mining-engine-tick-and-save.md) | Mining engine tick, Snapshot, and Pane-owned save |
| [0011](0011-audio-without-gates.md) | Audio without gates (CC0 clips under `src/audio/`) |
| [0012](0012-event-jump-advance-and-haul-duty-cycle.md) | Event-jump advance and haul duty cycle |
| [0013](0013-interpolated-presentation-clock.md) | Interpolated presentation clock (two clocks; swing phase from engine) |

Earlier decisions settled only in `docs/strip-acquisition-contract.md` or
`prototype/strip-coherence/NOTES.md` should be promoted here when they start
being re-argued.
