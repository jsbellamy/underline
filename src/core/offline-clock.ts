/** Wall-clock offline window for mining catch-up. */

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
