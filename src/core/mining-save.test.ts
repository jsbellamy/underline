import { describe, expect, it, beforeEach } from "vitest";
import { initialSnapshot, SCHEMA_VERSION, type MiningSnapshot } from "./mining-engine";
import {
  SAVE_KEY,
  clearSave,
  loadSave,
  persistSave,
  type SaveStore,
} from "./mining-save";

function memoryStore(initial: Record<string, string> = {}): SaveStore & {
  data: Record<string, string>;
} {
  const data = { ...initial };
  return {
    data,
    getItem(key) {
      return data[key] ?? null;
    },
    setItem(key, value) {
      data[key] = value;
    },
    removeItem(key) {
      delete data[key];
    },
  };
}

describe("mining save seam", () => {
  let store: ReturnType<typeof memoryStore>;

  beforeEach(() => {
    store = memoryStore();
  });

  it("round-trips authoritative v2 fields through underline-save-v1", () => {
    const snap: MiningSnapshot = {
      schemaVersion: SCHEMA_VERSION,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 1,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
    };
    persistSave(snap, 1_700_000_000_000, store);
    expect(store.data[SAVE_KEY]).toBeTruthy();
    const loaded = loadSave(store);
    expect(loaded).toEqual({
      snapshot: snap,
      savedAtMs: 1_700_000_000_000,
    });
  });

  it("migrates schemaVersion 1 upgradeCount to v2 upgrade counts in memory", () => {
    store.setItem(
      SAVE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        savedAtMs: 1_700_000_000_000,
        advance: 3,
        ore: 1.5,
        ingots: 7,
        upgradeCount: 2,
        faceSwingProgress: 1.25,
        smelterProgress: 0.4,
      }),
    );
    const loaded = loadSave(store);
    expect(loaded.snapshot).toEqual({
      schemaVersion: 2,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 0,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
    });
    expect(loaded.savedAtMs).toBe(1_700_000_000_000);
  });

  it("rewrites v2 on persist after loading a v1 save", () => {
    store.setItem(
      SAVE_KEY,
      JSON.stringify({
        schemaVersion: 1,
        savedAtMs: 100,
        advance: 0,
        ore: 0,
        ingots: 0,
        upgradeCount: 1,
        faceSwingProgress: 0,
        smelterProgress: 0,
      }),
    );
    const { snapshot } = loadSave(store);
    persistSave(snapshot, 200, store);
    const raw = JSON.parse(store.data[SAVE_KEY]!);
    expect(raw.schemaVersion).toBe(2);
    expect(raw.digRateUpgradeCount).toBe(1);
    expect(raw.smelterUpgradeCount).toBe(0);
    expect(raw.upgradeCount).toBeUndefined();
  });

  it("resets to a fresh Snapshot when the save is missing or unreadable", () => {
    expect(loadSave(store)).toEqual({
      snapshot: initialSnapshot(),
      savedAtMs: undefined,
    });
    store.setItem(SAVE_KEY, "{not-json");
    expect(loadSave(store).snapshot).toEqual(initialSnapshot());
    expect(loadSave(store).savedAtMs).toBeUndefined();
  });

  it("discards a mismatched schemaVersion and keeps a fresh Snapshot", () => {
    store.setItem(
      SAVE_KEY,
      JSON.stringify({
        schemaVersion: 99,
        savedAtMs: 123,
        advance: 9,
        ore: 9,
        ingots: 9,
        digRateUpgradeCount: 9,
        smelterUpgradeCount: 0,
        faceSwingProgress: 1,
        smelterProgress: 0.5,
      }),
    );
    const loaded = loadSave(store);
    expect(loaded.snapshot).toEqual(initialSnapshot());
    expect(loaded.savedAtMs).toBeUndefined();
  });

  it("clears the save key", () => {
    persistSave(initialSnapshot(), 1, store);
    clearSave(store);
    expect(store.getItem(SAVE_KEY)).toBeNull();
  });
});
