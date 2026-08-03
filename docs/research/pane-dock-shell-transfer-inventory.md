# Pane+Dock shell transfer inventory (Nightglass → Underline)

**Issue:** #315  
**Upstream:** Nightglass at `/Users/jakebellamy/VSProjects/games/game_idea/nightglass`  
**Nightglass HEAD:** `7047b2a28565d28598a4420b8762c7f49b1898f5` (2026-07-25 ≈)  
**Tip commit:** `Update vertical-slice-spec for five-encounter Stages and pacing. (#755)`  
**Primary ADRs:** `docs/adr/0002-battle-tile-and-management-dock.md`, `docs/adr/0005-dock-workspace-geometry.md` (also 0003 presentation clock, 0004 native body sprites)  
**Vocabulary:** Underline `CONTEXT.md` — Pane, Dock, Colony, Dwarf, Tunnel, Face, Ore, Smelter, Ingot, Dig Rate, Advance. Never call the always-on-top window a “tile”.

**Method:** Exports, imports, and tests over whole-file reads. Claims cite path + symbol. `UNCERTAIN` marks gaps checked but not decided by source.

**Do not copy Nightglass code into Underline from this research pass** — inventory only. Scaffold vendor work is #316.

---

## Verdict in one screen

| Class | Count | Meaning |
| --- | ---: | --- |
| **vendor clean** | 3 | Copy unchanged |
| **adapt** | 14 | Copy, then reframe (rename / drop combat types / rebind messages) |
| **leave** | 12 | Combat-entangled; rewrite fresh for mining |

Shell transfer is real: two-window geometry, dock window port, BroadcastChannel transport, sim/render pump, frame metrics, tab strip, and pressable keyboard helper are game-agnostic or nearly so. Combat lives in Battle Tile rendering, presentation/SFX/effects, Dock surfaces, Engine offline catch-up, and the bus *command schema*.

**Surprise:** Nightglass has **no multi-frame animation playback** in UI. Bodies are still PNGs; motion is presentation overlays (`lungeOffset`, effect frames). Underline’s Dwarf `idle` / `walk` / `swing` Frame sequences need a **fresh** player — there is nothing to vendor for that.

---

## Recommended vendor set for scaffold (#316)

Copy these Nightglass paths first (then adapt in place under Underline names). Exact upstream paths:

| Priority | Nightglass path | Underline intent |
| --- | --- | --- |
| 1 | `src/ui/keyboard.ts` + `keyboard.test.ts` | unchanged |
| 2 | `src/ui/frame-metrics.ts` + `frame-metrics.test.ts` | unchanged (phase labels optional rename) |
| 3 | `src/ui/tab-strip.ts` + `tab-strip.test.ts` | unchanged; Dock tabs → Colony |
| 4 | `src/ui/dock-geometry.ts` + `dock-geometry.test.ts` | rename `tile*` → `pane*` |
| 5 | `src/ui/pump.ts` + `pump.test.ts` | replace `EngineEvent` with mining event type / opaque `unknown[]` |
| 6 | `src/ui/dock-window.ts` + `dock-window.test.ts` | Pane labels; drop Armory `dragDropEnabled` rationale if unused |
| 7 | `src/ui/bus.ts` (only `createBusEndpoint` + `BusEndpoint`) | new channel name + mining `BusMessage` |
| 8 | `src/ui/battle-tile-layout.ts` | → `pane-layout.ts`; re-derive Pane chrome constants |
| 9 | `src/ui/boot.ts` symbols `computeOfflineMs`, `OFFLINE_CAP_MS`, `MIN_OFFLINE_MS` | wall-clock clamp only |
| 10 | `src/ui/sprites.ts` symbol `geometryFromManifestEntry` + `SpriteGeometry` | Dwarf/cave manifests; drop battlefield roles |
| 11 | `src/ui/native-1x-scaling.test.ts` (pattern) | PNG IHDR ↔ manifest ↔ CSS agreement for Dwarf Frames |
| 12 | `src/ui/geometry-tokens.test.ts` + `:root` tokens in `src/styles.css` | `--pane-*` / `--dock-*` lockstep |
| 13 | `src-tauri/tauri.conf.json` window block + `src-tauri/src/lib.rs` dock denylist | label `pane` not `tile` |
| 14 | `index.html` dual roots + `src/main.ts` `?window=dock` routing | `#pane` / `#dock` |

**Do not vendor for scaffold:** `battle-tile.ts`, `presentation.ts`, `damage-numbers.ts`, `effect-images.ts`, `sfx.ts`, `dock.ts` + `*-surface.ts`, `offline-summary.ts`, `core/engine.ts` offline path, combat `SPRITE_SOURCES` / roles, `applyTileCommand` / `TileCommand*`.

---

## Classification tables

### Must-cover areas

#### 1. Two-window geometry and monitor clamping

| Module | Class | Why |
| --- | --- | --- |
| `src/ui/dock-geometry.ts` (`dockRect`, `DOCK_*`) | **adapt** | Pure geometry; comments/params say Battle Tile |
| `src/ui/battle-tile-layout.ts` | **adapt** | Fixed outer size; names are battlefield chrome |
| `src/ui/dock-window.ts` (`dockRect` consumer, clamp-snap) | **adapt** | Tauri placement; imports tile layout constants |
| `src/ui/geometry-tokens.test.ts` + CSS `:root` | **adapt** | Lockstep tokens for tile/dock sizes |

**ADR authority:** ADR-0002 two windows + bus; ADR-0005 dock 800×480, center on tile, clamp x, snap `tileX`.

##### `dock-geometry.ts` — adapt

- **Paths:** `src/ui/dock-geometry.ts`; tests `src/ui/dock-geometry.test.ts`
- **Why adapt:** Math is domain-free; `tileRect` / `tileX` / “Battle Tile” comments must become Pane vocabulary.
- **Deps:** None (pure TS).
- **Tests assert:** Above/below park from monitor midpoint; 8px gap; dock sized to `DOCK_WIDTH`/`DOCK_HEIGHT` not Pane width; center when room; clamp left/right and snap companion window x; flush-left when monitor narrower than dock.
- **Mining change:** Keep `dockRect(paneRect, monitorRect)`. Dock stays Colony workspace; Pane shows Dwarf digging Tunnel east. Revisit numeric sizes — Underline has **not** declared Pane/Dock px in `CONTEXT.md` (`UNCERTAIN`, checked CONTEXT + docs).

##### `battle-tile-layout.ts` — adapt

- **Paths:** `src/ui/battle-tile-layout.ts`; consumed by dock-window, battle-tile, geometry-tokens, tauri.conf
- **Why adapt:** `TILE_*` / `BATTLEFIELD_HEIGHT` / `STATUS_LINE_HEIGHT` encode combat chrome (24px status + 86px battlefield = 112).
- **Deps:** None.
- **Tests:** Indirect via `geometry-tokens.test.ts`, `battle-tile.test.ts` (480×112 mount).
- **Mining change:** → `pane-layout.ts` with Pane width/height + Dig Rate / Tunnel band split. Do not keep “battlefield” naming.

##### `dock-window.ts` — adapt

- **Paths:** `src/ui/dock-window.ts`; tests `src/ui/dock-window.test.ts`
- **Why adapt:** Window port is shell; labels/`TILE_*`/Armory drag-drop comment are Nightglass-specific.
- **Deps:** `dock-geometry`, `battle-tile-layout`; Tauri `@tauri-apps/api/window`, `webviewWindow`, `dpi`; optional macOS `parent: "tile"`.
- **Tests assert:** `physicalRectToLogical`; open/ready/position/show; reuse hide/reopen; move coalescing; cache scale/monitor; set Pane position only when clamp snaps; child-attach parent probe; `dragDropEnabled: false` for HTML5 DnD.
- **Mining change:** Labels `pane` / `dock`; `?window=dock`; Colony upgrades likely click/press not Armory DnD — revisit `dragDropEnabled` (`UNCERTAIN` until Dock UX exists).

#### 2. Cross-window event bus

| Module | Class | Why |
| --- | --- | --- |
| `createBusEndpoint` / `BusEndpoint` in `bus.ts` | **adapt** | Thin `BroadcastChannel` wrapper |
| `BusMessage` / `TileCommand*` / `applyTileCommand` | **leave** | Engine method mirror + Snapshot/legality |

##### Bus transport — adapt

- **Paths:** `src/ui/bus.ts` (`NIGHTGLASS_BUS_CHANNEL`, `createBusEndpoint`); round-trip tests in `bus.test.ts`
- **Why adapt:** Transport is agnostic; channel name and payload types are not.
- **Deps:** Browser `BroadcastChannel` only (for endpoint factory).
- **Tests assert:** Dock command → tile Snapshot broadcast; pump batches reach dock listeners (`bus.test.ts`).
- **Mining change:** Channel e.g. `underline`; messages for Pane↔Dock: Snapshot (Advance, Dig Rate, Ore, Ingots, Smelter, upgrades), commands (buy Upgrade, open/close Dock), pump batches. Drop talent/equip/stage commands.

##### Bus command schema — leave

- **Paths:** `TileCommand`, `TileCommandName`, `applyTileCommand`, `bus-dispatch.test.ts`
- **Why leave:** Exhaustive map over combat `Engine` methods (`setLoadout`, `equip`, `allocateTalent`, …) via `snapshot-view` / `core/engine`.

#### 3. Pane and Dock roots and boot path

| Module | Class | Why |
| --- | --- | --- |
| `tile-root.ts` structure (`mountTileShell`, pump+bus+dock wiring) | **adapt** | Shell orchestration; mounts Battle Tile + combat Engine |
| `dock-root.ts` (`mountDockShell`, rAF coalesce) | **adapt** | Shell orchestration; mounts Management Dock |
| `boot.ts` wall-clock offline helpers | **adapt** | Cap/min helpers reusable |
| `boot.ts` `runOfflineBoot` / save / icons | **leave** / rewrite | Combat save + Engine offline |
| `main.ts` / `index.html` dual-root routing | **adapt** | `?window=dock` pattern |
| `tile-shell-types.ts` | **adapt** | Tiny; rename Tile→Pane |

##### `tile-root.ts` — adapt (structure only)

- **Paths:** `src/ui/tile-root.ts` (`startTileRoot`, `mountTileShell`); types `tile-shell-types.ts`
- **Why adapt:** Pattern = boot → mount scene → bus ↔ dock window → `startPump` + presentation-clock clamp (ADR-0003). Bodies call `mountBattleTile`, `createEngine`, `buildContent`.
- **Deps:** boot, bus, battle-tile, dock-window, pump, frame-metrics, engine-legality, snapshot-view, data content.
- **Tests:** Wiring covered indirectly (`boot.test.ts`, `main.test.ts` — not fully re-read; `UNCERTAIN` exact main.test coverage).
- **Mining change:** `mountPaneShell`: Engine = mining sim; scene = Dwarf at Face digging east; Dock toggle unchanged in spirit.

##### `dock-root.ts` — adapt (structure only)

- **Paths:** `src/ui/dock-root.ts`
- **Why adapt:** Bus subscribe + coalesce pump Snapshot onto dock via rAF is reusable; `mountManagementDock` / equipment icon assert are not.
- **Deps:** bus, dock, engine-legality, content.
- **Tests:** Indirect via dock / boot tests.
- **Mining change:** Mount Colony surface(s); coalesce Dig Rate / Ore / Ingot Snapshot updates.

##### `boot.ts` — split

| Symbol | Class |
| --- | --- |
| `computeOfflineMs`, `OFFLINE_CAP_MS`, `MIN_OFFLINE_MS` | **adapt** (near-clean extract) |
| `SAVE_KEY`, `persistSave`, `runOfflineBoot`, `bootTile`, `DEFAULT_LOOT_SEED`, icon asserts | **leave** / rewrite |

- **Tests:** `boot.test.ts` — 8h clamp; autosave/pagehide; offline awards no equipment; summary mount ordering.
- **Mining change:** Persist mining Snapshot; offline Advance / Ore / Smelter / Ingots (fresh engine API). Keep 8h cap / 60s minimum as starting policy unless Underline decides otherwise (`UNCERTAIN`).

##### Entry routing — adapt

- **Paths:** `src/main.ts` (`isDockWindow`), `index.html` (`#tile`, `#dock`)
- **Why adapt:** Dual `<main>` + query flag is the two-window boot.
- **Mining change:** `#pane` / `#dock`; drop evidence-fixture branch.

#### 4. Native 1× scaling and frame metrics

| Module | Class | Why |
| --- | --- | --- |
| `frame-metrics.ts` | **vendor clean** | No domain imports |
| `native-1x-scaling.test.ts` | **adapt** | Evidence pattern; combat sprite registry |
| `geometryFromManifestEntry` in `sprites.ts` | **adapt** | Manifest geometry validation reusable |
| ADR-0004 / role ceilings in `layout.json` | **leave** | Party/opponent/boss opaque maxima |

##### `frame-metrics.ts` — vendor clean

- **Paths:** `src/ui/frame-metrics.ts`; tests `frame-metrics.test.ts`
- **Why clean:** Rolling p50/p95/max for render + tick phases; injectable `now`.
- **Deps:** None.
- **Tests assert:** Percentiles, window cap 120, phase attribution, error still records duration, reset.
- **Mining change:** Optional rename of phase keys (`applyEvents`/`legality`) to mining tick phases — not required to vendor.

##### Native 1× evidence — adapt

- **Paths:** `src/ui/native-1x-scaling.test.ts`; ADR-0004
- **Why adapt:** Asserts PNG IHDR = manifest `frame_size` = resolved geometry; no CSS size tiers / mirror hacks.
- **Deps:** `SPRITE_SOURCES`, `spriteBattlefieldRole`, `layout.json` roles.
- **Mining change:** Same IHDR↔manifest contract for `assets/characters/dwarf/**` Frames; drop battlefield roles; CSS vars for Dwarf frame size not `--combatant-frame-w`.

#### 5. Sprite loading and animation playback

| Module | Class | Why |
| --- | --- | --- |
| `SpriteGeometry` / `geometryFromManifestEntry` | **adapt** | Shared manifest shape |
| `SPRITE_SOURCES` / `resolveSprite` / roles | **leave** | Combat cast registry |
| Multi-frame walk/swing playback | **leave** (rewrite) | **No Nightglass UI equivalent** |
| `presentation.ts` body motion | **leave** | Combat lunge/hurt/effects |

##### Loading — adapt extract

- **Paths:** `src/ui/sprites.ts` (`geometryFromManifestEntry`, `SpriteGeometry`); tests in `sprites.test.ts` (malformed geometry cases)
- **Deps for extract:** Manifest JSON shape only.
- **Mining change:** Resolve Dwarf Motion-class Frame URLs + cave Rendering Tiles; foot-anchor rule may differ for Tunnel floor (`UNCERTAIN` — Nightglass requires bottom-centre foot_anchor).

##### Animation playback — leave / rewrite

- Checked: `src/ui/sprites.ts`, `battle-tile.ts`, `presentation.ts` — stills + presentation overlays, not Frame-sequence players.
- **Mining need:** Play `idle` / `walk` / `swing` east/west Frame lists at Dig Rate–linked cadence while Advance progresses. Fresh module.

#### 6. Render pump

| Module | Class | Why |
| --- | --- | --- |
| `pump.ts` (`startPump`) | **adapt** | Logic agnostic; typed to `EngineEvent[]` |

##### `pump.ts` — adapt

- **Paths:** `src/ui/pump.ts`; tests `pump.test.ts`
- **Why adapt:** Visible 250ms sim tick, rAF render, hidden 5s heartbeat, unhide catch-up chunking (`MAX_CATCH_UP_CHUNK_MS` 60s, budget 8ms) are shell. Import of `../core/events` `EngineEvent` is combat-typed.
- **Deps:** `frame-metrics` (optional); `Document.hidden`; timers/rAF injectable.
- **Tests assert:** 250ms live pump; hidden stops render / 5s heartbeat; rAF render cadence; stop cancels; catch-up chunking/yielding; early-interval uses elapsed not nominal interval.
- **Mining change:** `advanceBy` advances mining sim (Swings, Face break → Advance, Ore, Smelter). Keep catch-up so AFK-in-background Pane stays honest.

#### 7. Offline-progress computation

| Module | Class | Why |
| --- | --- | --- |
| `computeOfflineMs` (+ caps) | **adapt** | Wall-clock clamp only |
| `engine.advanceOffline` / `advanceOfflineSummary` | **leave** | Combat schedule catch-up |
| `offline-summary.ts` | **leave** | Stages / XP / Drops UI |
| `offline-progress.perf.test.ts` | **leave** | Times combat 8h advance |

##### Wall-clock clamp — adapt

- **Paths:** `boot.ts` `computeOfflineMs`, `OFFLINE_CAP_MS` (8h), `MIN_OFFLINE_MS` (60s)
- **Tests:** `boot.test.ts` clamp case.
- **Mining change:** Same helper feeding a mining `advanceOffline(ms)` that resolves Advance, Ore stockpile, Smelter→Ingot, Dig Rate upgrades already owned — **not** stages/loot.

##### Engine + summary — leave

- **Paths:** `src/core/engine.ts` (`advanceOffline`, `advanceOfflineSummary`); `src/ui/offline-summary.ts` + tests; perf test
- **Why leave:** Offline = combat `advanceElapsed` without drops; summary = stages cleared, character XP, armory drops.

---

### Related shell pieces

| Module | Class | One-line why | Tests |
| --- | --- | --- | --- |
| `tab-strip.ts` | **vendor clean** | Generic ARIA tablist | `tab-strip.test.ts` — arrows/Home/End, aria-selected, onReactivate |
| `keyboard.ts` `bindPressable` | **vendor clean** | Click/Enter/Space once | `keyboard.test.ts` |
| `surface-shell.ts` `el` helper | **adapt** | DOM helper clean; `mountSurfaceShell` bound to Snapshot/legality | `surface-shell.test.ts` — el, scroll/focus preserve, reconcile |
| `surface-shell.ts` `mountSurfaceShell` | **adapt** | Rebuild/reconcile pattern useful for Colony; drop Wave/pending-edit combat copy | same |
| `dock.ts` + `DOCK_SURFACES` | **leave** | Armory / Character / Stage | `dock.test.ts` |
| `*-surface.ts` (armory, character, stage, talents, loadout, stats) | **leave** | Combat management | per-file `*.test.ts` |
| `battle-tile.ts` | **leave** | Battlefield renderer | `battle-tile.test.ts` |
| `presentation.ts` | **leave** | Combat presentation clock consumers | `presentation.test.ts` |
| `battle-tile-anchors.ts` | **leave** | Formation foot anchors | `battle-tile-anchors.test.ts` |
| `damage-numbers.ts` / `effect-images.ts` / `sfx.ts` | **leave** | Combat VFX/audio | matching tests |
| `engine-legality.ts` | **leave** | Talent/equip legality views for Dock | `engine-legality.test.ts` |
| `tauri.conf.json` window `label: "tile"` | **adapt** | Fixed always-on-top undecorated Pane | (config; covered by dock-window manual checks) |
| `src-tauri/src/lib.rs` window-state denylist `dock` | **adapt** | Persist Pane position; dock owned by `dockRect` | `dock-window.test.ts` “geometry-not-persisted” |

---

### Count roll-up (inventory rows)

**Vendor clean (3):** `keyboard.ts`, `frame-metrics.ts`, `tab-strip.ts`

**Adapt (14):** `dock-geometry.ts`, `battle-tile-layout.ts`→pane-layout, `dock-window.ts`, geometry CSS tokens + `geometry-tokens.test.ts`, bus transport (`createBusEndpoint`), `pump.ts`, `tile-root.ts` structure, `dock-root.ts` structure, `boot.ts` offline clamp symbols, `main.ts`/`index.html` routing, `tauri.conf.json`+`lib.rs`, `geometryFromManifestEntry`, `native-1x-scaling.test.ts` pattern, `surface-shell.ts` (`el` + shell pattern)

**Leave (12):** bus `TileCommand`/`applyTileCommand`, `battle-tile.ts`, `presentation.ts`, `battle-tile-anchors.ts`, `dock.ts`+surfaces, `offline-summary.ts`, engine offline APIs, combat sprite registry/roles, `damage-numbers.ts`, `effect-images.ts`, `sfx.ts`, `engine-legality.ts`  
(+ **rewrite:** multi-frame animation playback — no upstream module)

---

## Appendix A — Draft vendor manifest (for #316 scaffolding)

Style matches Underline `pipeline/recovery.py` header. One section per vendored unit; expand when files land.

```text
"""Vendored Pane+Dock shell primitives from Nightglass.

Source: nightglass/src/ui/<module>.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: <YYYY-MM-DD>

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit this copy in place.
"""
```

### Planned units (scaffold checklist)

| Underline target (proposed) | Nightglass source | Class | Notes |
| --- | --- | --- | --- |
| `src/ui/keyboard.ts` | `src/ui/keyboard.ts` | vendor clean | Full file |
| `src/ui/frame-metrics.ts` | `src/ui/frame-metrics.ts` | vendor clean | Full file |
| `src/ui/tab-strip.ts` | `src/ui/tab-strip.ts` | vendor clean | Full file (+ keyboard dep) |
| `src/ui/dock-geometry.ts` | `src/ui/dock-geometry.ts` | adapt | Rename tile→pane in API/comments |
| `src/ui/pump.ts` | `src/ui/pump.ts` | adapt | Decouple `EngineEvent` |
| `src/ui/dock-window.ts` | `src/ui/dock-window.ts` | adapt | Pane labels; Tauri deps |
| `src/ui/bus.ts` | `src/ui/bus.ts` | adapt | Transport only; new messages |
| `src/ui/pane-layout.ts` | `src/ui/battle-tile-layout.ts` | adapt | New constants for mining chrome |
| `src/ui/offline-clock.ts` (or boot slice) | `boot.ts` clamp symbols | adapt | No Engine |
| `src/ui/sprite-geometry.ts` | `sprites.ts` geometry helpers | adapt | No combat registry |

Each shipped file should carry the header block above with its exact source path and the same Nightglass SHA until a re-vendor bumps it.

---

## Appendix B — Fog → map tickets

| Fog | Why it matters | Suggested ticket shape |
| --- | --- | --- |
| Pane / Dock pixel sizes undeclared in Underline | Cannot copy 480×112 / 800×480 blindly | Decide Pane chrome (Dig Rate line + Tunnel band) and Dock Colony size; update pane-layout + tauri.conf |
| No upstream Frame-sequence player | Dwarf walk/swing is core Pane feel | Spec + implement animation playback against `assets/characters/dwarf` manifests |
| Offline = Engine combat loop | AFK Advance/Ore/Smelter needs a mining offline API | Spec mining `advanceOffline` (Dig Rate × elapsed → Swings → Face breaks → Advance/Ore; Smelter throughput) |
| Bus message schema | Dock Colony upgrades need a closed command set | Define Underline `BusMessage` before wiring roots |
| macOS `parent: "tile"` + window-state denylist | Labels must move with rename | Tauri config issue: `pane` label, denylist `dock` |
| `dragDropEnabled: false` | Armory-only rationale | Confirm Colony UX; default may flip |
| Presentation clock (ADR-0003) | Smooth motion between 250ms ticks | Decide if Dig Rate / Swing animation needs interpolated `nowMs` in Pane root |
| Foot-anchor bottom-centre hard rule | Tunnel floor placement may differ | Validate against Dwarf Release Frames before adopting `geometryFromManifestEntry` unchanged |

---

## Appendix C — Source index (quick)

| Concern | Authority |
| --- | --- |
| Two windows + bus | ADR-0002; `bus.ts`, `tile-root.ts`, `dock-root.ts`, `main.ts` |
| Dock size / clamp | ADR-0005; `dock-geometry.ts`, `dock-window.ts` |
| Sim vs presentation clocks | ADR-0003; `pump.ts`, `tile-root.ts` presentationNowMs clamp, `presentation.ts` |
| Native 1× bodies | ADR-0004; `sprites.ts`, `native-1x-scaling.test.ts` |
| Offline wall clock | `boot.ts` `computeOfflineMs` |
| Offline sim | `engine.ts` `advanceOffline*` |
| Tauri Pane window | `src-tauri/tauri.conf.json` `windows[0]`; dock created in JS |

---

## Decisions-so-far gist (for map)

Nightglass Pane+Dock shell geometry, dock window port, BroadcastChannel transport, pump, frame metrics, and tab/keyboard helpers transfer with rename/retype; Battle Tile presentation, combat Dock surfaces, Engine offline, and sprite cast stay behind — and multi-frame Dwarf animation has no upstream player to vendor.
