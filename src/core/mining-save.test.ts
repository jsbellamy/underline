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

  it("round-trips authoritative v4 fields through underline-save-v1", () => {
    const snap: MiningSnapshot = {
      schemaVersion: SCHEMA_VERSION,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 1,
      carryCapacityUpgradeCount: 1,
      crewSize: 2,
      heapLoads: 3,
      heapOre: 7,
      haulSpeedUpgradeCount: 2,
      pickupProgressMs: 4_200,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
      bagOre: 3.5,
      bagLoads: 4,
      haulRemainingMs: 2000,
    };
    persistSave(snap, 1_700_000_000_000, store);
    expect(store.data[SAVE_KEY]).toBeTruthy();
    const loaded = loadSave(store);
    expect(loaded).toEqual({
      snapshot: snap,
      savedAtMs: 1_700_000_000_000,
    });
  });

  it("migrates schemaVersion 2 to v4 with Bag and Crew fields defaulted to zero", () => {
    store.setItem(
      SAVE_KEY,
      JSON.stringify({
        schemaVersion: 2,
        savedAtMs: 1_700_000_000_000,
        advance: 3,
        ore: 1.5,
        ingots: 7,
        digRateUpgradeCount: 2,
        smelterUpgradeCount: 1,
        faceSwingProgress: 1.25,
        smelterProgress: 0.4,
      }),
    );
    const loaded = loadSave(store);
    expect(loaded.snapshot).toEqual({
      schemaVersion: SCHEMA_VERSION,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 1,
      carryCapacityUpgradeCount: 0,
      crewSize: 1,
      heapLoads: 0,
      heapOre: 0,
      haulSpeedUpgradeCount: 0,
      pickupProgressMs: 0,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
      bagOre: 0,
      bagLoads: 0,
      haulRemainingMs: 0,
    });
    expect(loaded.savedAtMs).toBe(1_700_000_000_000);
  });

  it("migrates schemaVersion 1 upgradeCount through v2 shape to v4", () => {
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
      schemaVersion: SCHEMA_VERSION,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 0,
      carryCapacityUpgradeCount: 0,
      crewSize: 1,
      heapLoads: 0,
      heapOre: 0,
      haulSpeedUpgradeCount: 0,
      pickupProgressMs: 0,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
      bagOre: 0,
      bagLoads: 0,
      haulRemainingMs: 0,
    });
    expect(loaded.savedAtMs).toBe(1_700_000_000_000);
  });

  it("migrates schemaVersion 3 to v4 with one-Dwarf Crew defaults", () => {
    store.setItem(
      SAVE_KEY,
      JSON.stringify({
        schemaVersion: 3,
        savedAtMs: 1_700_000_000_000,
        advance: 3,
        ore: 1.5,
        ingots: 7,
        digRateUpgradeCount: 2,
        smelterUpgradeCount: 1,
        carryCapacityUpgradeCount: 1,
        faceSwingProgress: 1.25,
        smelterProgress: 0.4,
        bagOre: 3.5,
        bagLoads: 4,
        haulRemainingMs: 2000,
      }),
    );
    const loaded = loadSave(store);
    expect(loaded.snapshot).toEqual({
      schemaVersion: SCHEMA_VERSION,
      advance: 3,
      ore: 1.5,
      ingots: 7,
      digRateUpgradeCount: 2,
      smelterUpgradeCount: 1,
      carryCapacityUpgradeCount: 1,
      crewSize: 1,
      heapLoads: 0,
      heapOre: 0,
      haulSpeedUpgradeCount: 0,
      pickupProgressMs: 0,
      faceSwingProgress: 1.25,
      smelterProgress: 0.4,
      bagOre: 3.5,
      bagLoads: 4,
      haulRemainingMs: 2000,
    });
    expect(loaded.savedAtMs).toBe(1_700_000_000_000);
  });

  it("rewrites v4 on persist after loading a v1 save", () => {
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
    expect(raw.schemaVersion).toBe(SCHEMA_VERSION);
    expect(raw.digRateUpgradeCount).toBe(1);
    expect(raw.smelterUpgradeCount).toBe(0);
    expect(raw.carryCapacityUpgradeCount).toBe(0);
    expect(raw.crewSize).toBe(1);
    expect(raw.heapLoads).toBe(0);
    expect(raw.heapOre).toBe(0);
    expect(raw.haulSpeedUpgradeCount).toBe(0);
    expect(raw.pickupProgressMs).toBe(0);
    expect(raw.bagOre).toBe(0);
    expect(raw.bagLoads).toBe(0);
    expect(raw.haulRemainingMs).toBe(0);
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
