import { describe, expect, it, beforeEach } from "vitest";
import { initialSnapshot } from "./mining-engine";
import { SAVE_KEY, loadSave, persistSave } from "./mining-save";
import type { SaveStore } from "./mining-save";
import {
  SETTINGS_KEY,
  defaultSettings,
  loadSettings,
  persistSettings,
} from "./settings-save";

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

describe("settings save seam", () => {
  let store: ReturnType<typeof memoryStore>;

  beforeEach(() => {
    store = memoryStore();
  });

  it("defaults sound to off with schemaVersion 1", () => {
    expect(defaultSettings()).toEqual({
      schemaVersion: 1,
      soundEnabled: false,
    });
  });

  it("returns defaults when the settings key is absent", () => {
    expect(loadSettings(store)).toEqual(defaultSettings());
  });

  it("returns defaults when the settings JSON is unparseable", () => {
    store.setItem(SETTINGS_KEY, "{not-json");
    expect(loadSettings(store)).toEqual(defaultSettings());
  });

  it("returns defaults when schemaVersion is not 1", () => {
    store.setItem(
      SETTINGS_KEY,
      JSON.stringify({ schemaVersion: 2, soundEnabled: true }),
    );
    expect(loadSettings(store)).toEqual(defaultSettings());
  });

  it("returns defaults when soundEnabled is not a boolean", () => {
    store.setItem(
      SETTINGS_KEY,
      JSON.stringify({ schemaVersion: 1, soundEnabled: "yes" }),
    );
    expect(loadSettings(store)).toEqual(defaultSettings());
  });

  it("returns defaults when the payload is not an object", () => {
    store.setItem(SETTINGS_KEY, JSON.stringify("not-an-object"));
    expect(loadSettings(store)).toEqual(defaultSettings());
  });

  it("round-trips soundEnabled through underline-settings-v1", () => {
    persistSettings({ schemaVersion: 1, soundEnabled: true }, store);
    expect(store.data[SETTINGS_KEY]).toBeTruthy();
    expect(loadSettings(store)).toEqual({
      schemaVersion: 1,
      soundEnabled: true,
    });
  });

  it("keeps economy and settings saves independent", () => {
    const snap = { ...initialSnapshot(), ore: 42 };
    persistSettings({ schemaVersion: 1, soundEnabled: true }, store);
    persistSave(snap, 1_700_000_000_000, store);
    const economyPayload = store.getItem(SAVE_KEY)!;

    store.setItem(SAVE_KEY, "{corrupt");
    expect(loadSettings(store)).toEqual({
      schemaVersion: 1,
      soundEnabled: true,
    });

    store.setItem(SAVE_KEY, economyPayload);
    store.setItem(SETTINGS_KEY, "{corrupt");
    expect(loadSave(store)).toEqual({
      snapshot: snap,
      savedAtMs: 1_700_000_000_000,
    });
  });
});
