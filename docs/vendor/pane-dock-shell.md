# Vendored Pane+Dock shell (Nightglass → Underline)

**Nightglass commit:** `7047b2a28565d28598a4420b8762c7f49b1898f5`  
**Vendored:** 2026-08-03  
**Inventory:** `docs/research/pane-dock-shell-transfer-inventory.md`  
**Decision:** `docs/adr/0009-vendored-pane-dock-shell.md`

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit vendored copies in place to diverge. Adapted files may rename or
retype for Underline vocabulary, but geometry/timing logic still re-vendors
from the listed Nightglass source before further edits.

| Underline path | Nightglass source | Class |
| --- | --- | --- |
| `src/ui/keyboard.ts` | `src/ui/keyboard.ts` | vendor clean |
| `src/ui/frame-metrics.ts` | `src/ui/frame-metrics.ts` | vendor clean |
| `src/ui/tab-strip.ts` | `src/ui/tab-strip.ts` | vendor clean |
| `src/ui/dock-geometry.ts` | `src/ui/dock-geometry.ts` | adapt (pane vocab) |
| `src/ui/pane-layout.ts` | `src/ui/battle-tile-layout.ts` | adapt (Pane chrome names) |
| `src/ui/pump.ts` | `src/ui/pump.ts` | adapt (`unknown[]` events) |
| `src/ui/dock-window.ts` | `src/ui/dock-window.ts` | adapt (pane labels) |
| `src/ui/bus.ts` | `src/ui/bus.ts` | adapt (transport only) |
| `src/ui/offline-clock.ts` | `src/ui/boot.ts` (`computeOfflineMs` + caps) | adapt |
| `src/ui/sprite-geometry.ts` | `src/ui/sprites.ts` (`geometryFromManifestEntry`) | adapt |
| `src/main.ts` | `src/main.ts` | adapt (`#pane` / `#dock`) |
| `index.html` | `index.html` | adapt |
| `src-tauri/tauri.conf.json` | `src-tauri/tauri.conf.json` | adapt (label `pane`) |
| `src-tauri/src/lib.rs` | `src-tauri/src/lib.rs` | adapt (dock denylist) |
| `src-tauri/capabilities/default.json` | `src-tauri/capabilities/default.json` | adapt |

Empty shell roots (`pane-root.ts`, `dock-root.ts`) and minimal `src/styles.css`
are Underline-authored scaffolds, not Nightglass copies.
