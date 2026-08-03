/** Pane-owned mining session: load, offline catch-up, live advance, Upgrade, persist. */

import {
  OFFLINE_RATE_SCALE,
  advance,
  buyUpgrade,
  type MiningSnapshot,
  type UpgradeId,
} from "./mining-engine";
import {
  browserSaveStore,
  loadSave,
  persistSave,
  type SaveStore,
} from "./mining-save";
import {
  buildOfflineSummary,
  toWireSnapshot,
  type OfflineSummary,
  type WireSnapshot,
} from "./wire-snapshot";
import { MIN_OFFLINE_MS, computeOfflineMs } from "./offline-clock";

export const AUTOSAVE_MS = 10_000;

export interface MiningSession {
  readonly snapshot: MiningSnapshot;
  wireSnapshot(): WireSnapshot;
  advanceLive(dtMs: number): MiningSnapshot;
  tryBuyUpgrade(upgrade: UpgradeId): boolean;
  publish(): void;
  persist(): void;
  clearOfflineSummary(): void;
}

export interface MiningSessionOptions {
  store?: SaveStore;
  now?: () => number;
  /** Skip load; use this Snapshot (tests). */
  snapshot?: MiningSnapshot;
  onPublish?: (wire: WireSnapshot) => void;
}

export function createMiningSession(
  options: MiningSessionOptions = {},
): MiningSession {
  const store = options.store ?? browserSaveStore();
  const now = options.now ?? Date.now;
  const onPublish = options.onPublish;

  let offlineSummary: OfflineSummary | undefined;
  let snapshot: MiningSnapshot;

  if (options.snapshot) {
    snapshot = options.snapshot;
  } else {
    const loaded = loadSave(store);
    const offlineMs = computeOfflineMs(loaded.savedAtMs, now());
    if (offlineMs > 0) {
      const before = loaded.snapshot;
      snapshot = advance(before, offlineMs, { rateScale: OFFLINE_RATE_SCALE });
      if (offlineMs >= MIN_OFFLINE_MS) {
        offlineSummary = buildOfflineSummary({
          before,
          after: snapshot,
          offlineMs,
        });
      }
      persistSave(snapshot, now(), store);
    } else {
      snapshot = loaded.snapshot;
    }
  }

  function wireSnapshot(): WireSnapshot {
    return toWireSnapshot(snapshot, offlineSummary);
  }

  function publish(): void {
    onPublish?.(wireSnapshot());
  }

  function persist(): void {
    persistSave(snapshot, now(), store);
  }

  return {
    get snapshot() {
      return snapshot;
    },
    wireSnapshot,
    advanceLive(dtMs: number) {
      snapshot = advance(snapshot, dtMs);
      return snapshot;
    },
    tryBuyUpgrade(upgrade: UpgradeId) {
      try {
        snapshot = buyUpgrade(snapshot, upgrade);
        persist();
        publish();
        return true;
      } catch {
        publish();
        return false;
      }
    },
    publish,
    persist,
    clearOfflineSummary() {
      offlineSummary = undefined;
    },
  };
}
