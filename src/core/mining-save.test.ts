import { describe, expect, it, beforeEach } from "vitest";
import { initialSnapshot } from "./mining-engine";
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

  it("round-trips authoritative fields through underline-save-v1", () => {
    const snap = {
      ...initialSnapshot(),
      advance: 3,
      ore: 1.5,
      ingots: 7,
      upgradeCount: 2,
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
        upgradeCount: 9,
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
