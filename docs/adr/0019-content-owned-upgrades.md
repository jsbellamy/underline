# ADR 0019: Content-owned Upgrades

## Status

Accepted (2026-08-05)

## Context

Each Upgrade in the mining economy was declared in fragments across
`buyUpgrade` and seven `nextXUpgradeCost` helpers in `src/core/mining-engine.ts`.
Adding an Upgrade required editing the engine: a new `UpgradeId` branch, a cost
function, and a count field bump — seven touch points for content that is not
simulation logic.

`docs/agents/code-style.md` § Layout places content data under `src/data/` and
requires that adding content must not require a core change.

## Decision

- **`src/data/upgrade-catalogue.ts`** is the single declaration of each Upgrade:
  id, Ingot cost curve, and effect (`raiseCount` on a snapshot count field, or
  `hireHauler`).
- **`buyUpgrade`** resolves the catalogue entry, checks Ingots once, and applies
  the declared effect generically — no per-id branch in core.
- **`nextXUpgradeCost` exports** remain on `mining-engine.ts` for existing
  importers but delegate to `upgradeCostFor` from the catalogue.
- **`UpgradeId`, `FIRST_UPGRADE_COST`, and `HIRE_HAULER_COST`** live in the
  catalogue; `mining-engine.ts` re-exports them so `bus.ts`, `mining-session.ts`,
  and `colony-view.ts` need no import-path change in this wave.

## Consequences

### Positive

- A new Upgrade is one catalogue row plus aggregate validation in
  `upgrade-catalogue.test.ts`; core stays unchanged.
- The doubling cost curve and flat Hire Hauler price are written once.
- Economy behavior is unchanged — this is a seam move, not a balance change.

### Negative

- `buyUpgrade` still lives in core because it mutates `MiningSnapshot`; only the
  declaration moved. A later slice may migrate dock and bus to read the catalogue
  directly.

## Rejected alternatives

- **Leave declarations in core** — violates the Layout rule; every new Upgrade
  would keep spreading branches through `mining-engine.ts`.
- **Move `buyUpgrade` into `src/data/`** — the catalogue must not import
  simulation internals; purchase application belongs with the snapshot type.
