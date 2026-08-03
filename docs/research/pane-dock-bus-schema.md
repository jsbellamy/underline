# Pane↔Dock bus message schema

**Issue:** [Define the Pane↔Dock bus message schema](https://github.com/jsbellamy/underline/issues/323)  
**Vocabulary:** `CONTEXT.md` § Game language — Pane, Dock, Colony, Dig Rate, Ore, Ingot, Advance, Upgrade, Smelter.  
**Authority:** [Decide the tick, snapshot, and save model](https://github.com/jsbellamy/underline/issues/320) — Pane owns engine + save; Dock is Snapshot/command client only.  
**Save fields:** [`docs/research/tick-snapshot-save-model.md`](./tick-snapshot-save-model.md)  
**Numbers:** [`docs/research/produce-and-spend-economy.md`](./produce-and-spend-economy.md)  
**Transport:** vendored `createBusEndpoint` in `src/ui/bus.ts` (BroadcastChannel).

This is the message contract [Close the loop: spend Ore in the dock and accrue it offline](https://github.com/jsbellamy/underline/issues/322) implements against.

---

## Channel

- Name: **`underline`** (`UNDERLINE_BUS_CHANNEL`).
- Breaking schema later may rename to `underline-v2` (map fog); v1 does not rename the channel.

## Versioning

- Every Snapshot and every command carries **`schemaVersion: 1`** (same integer as the save).
- Dock **ignores** Snapshots with missing or mismatched `schemaVersion`.
- Pane **ignores** commands with missing/mismatched `schemaVersion` or unknown `name`.
- Dock tags outbound commands `1`; it may send `requestSnapshot` before the first compatible Snapshot (Pane answers with a v1 Snapshot).

## Closed `BusMessage` set

| Type | Direction | Role |
| --- | --- | --- |
| `snapshot` | Pane → Dock | Authoritative Colony state |
| `command` | Dock → Pane | `buyUpgrade` \| `requestSnapshot` |
| `dock-opened` | Dock → Pane | Lifecycle only |
| `dock-closed` | Dock → Pane | Lifecycle only |

**Not on the bus:** `pump` event batches. Presentation (Swing, walk, Face crack) and sim event lists stay **Pane-local**. The Dock coalesces successive Snapshots; it never subscribes to dig events.

Combat leftovers (`TileCommand*`, `setLoadout`, `equip`, talents, …) stay rejected.

---

## Snapshot payload (authoritative on the wire)

Persist-aligned fields only — Dock derives the rest.

| Field | Role |
| --- | --- |
| `schemaVersion` | `1` |
| `advance` | Mineable Blocks broken |
| `ore` | Smelter backlog (fractional OK) |
| `ingots` | Spendable |
| `upgradeCount` | Buys completed |
| `faceSwingProgress` | Swings spent on current Face (`0…Hardness`) |
| `smelterProgress` | Fractional Ore toward next Ingot (`0…1`) |
| `offlineSummary?` | Present after boot catch-up when `offlineMs ≥ MIN_OFFLINE_MS` (60s); Dock shows then clears locally |

`savedAtMs` is save-boundary only — **not** on the wire.

### Dock derives (slice constants + `upgradeCount`)

| Derived | Formula |
| --- | --- |
| Dig Rate | `1.0 + 0.25 × upgradeCount` |
| Next Upgrade cost | `5 × 2^upgradeCount` |
| Hardness | `4` |
| Yield | `1` |
| Smelter throughput | `0.15` Ore/sec |

### When the Pane publishes `snapshot`

- After sim steps that change economy fields
- After a successful (or attempted-and-applied) `buyUpgrade`
- On `requestSnapshot`
- After offline catch-up at boot (with `offlineSummary` when the ≥60s rule holds)

---

## Commands

```ts
type DockCommand =
  | { schemaVersion: 1; name: "buyUpgrade" }
  | { schemaVersion: 1; name: "requestSnapshot" };
```

Envelope: `{ type: "command"; command: DockCommand }`.

| Name | Pane behaviour |
| --- | --- |
| `buyUpgrade` | Apply if Ingots ≥ next cost; deduct; bump `upgradeCount`; persist; broadcast Snapshot. No-op (still may rebroadcast) if unaffordable. |
| `requestSnapshot` | Broadcast current Snapshot immediately. |

No `dismissOfflineSummary` on the bus — dismiss is Dock-local UI until the offline surface needs otherwise.

---

## Envelope sketch

```ts
type BusMessage =
  | { type: "snapshot"; snapshot: WireSnapshot }
  | { type: "command"; command: DockCommand }
  | { type: "dock-opened" }
  | { type: "dock-closed" };

type WireSnapshot = {
  schemaVersion: 1;
  advance: number;
  ore: number;
  ingots: number;
  upgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
  offlineSummary?: {
    offlineMs: number;
    advanceGained: number;
    oreProduced: number;
    oreSmelted: number;
    oreBacklog: number;
  };
};
```

---

## Deferred

- Channel rename on schema break (`underline-v2`).
- Extra Dock-chrome commands beyond the two above.
- Pump/event feed if a future Dock activity surface needs it.
