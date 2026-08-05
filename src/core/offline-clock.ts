/** Adapted from Nightglass.

Source: nightglass/src/ui/boot.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Wall-clock offline window for mining catch-up.
*/

export const OFFLINE_CAP_MS = 8 * 60 * 60 * 1000;
export const MIN_OFFLINE_MS = 60_000;

export function computeOfflineMs(
  savedAtMs: number | undefined,
  nowMs: number,
): number {
  if (savedAtMs === undefined || !Number.isFinite(savedAtMs)) {
    return 0;
  }
  return Math.max(0, Math.min(nowMs - savedAtMs, OFFLINE_CAP_MS));
}
