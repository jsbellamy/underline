/** Adapted from Nightglass.

Source: nightglass/src/ui/boot.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Wall-clock offline helpers — re-export from core so UI callers keep working.
*/

export {
  OFFLINE_CAP_MS,
  MIN_OFFLINE_MS,
  computeOfflineMs,
} from "../core/offline-clock";
