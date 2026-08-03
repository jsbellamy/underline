import type { SaveStore } from "./mining-save";

export const SETTINGS_KEY = "underline-settings-v1";

export interface PlayerSettings {
  schemaVersion: 1;
  soundEnabled: boolean;
}

export function defaultSettings(): PlayerSettings {
  return { schemaVersion: 1, soundEnabled: false };
}

function parseSettings(raw: unknown): PlayerSettings | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const record = raw as { schemaVersion?: unknown; soundEnabled?: unknown };
  if (record.schemaVersion !== 1) {
    return null;
  }
  if (typeof record.soundEnabled !== "boolean") {
    return null;
  }
  return { schemaVersion: 1, soundEnabled: record.soundEnabled };
}

export function loadSettings(store: SaveStore): PlayerSettings {
  const text = store.getItem(SETTINGS_KEY);
  if (text == null) {
    return defaultSettings();
  }
  try {
    const raw = JSON.parse(text) as unknown;
    const settings = parseSettings(raw);
    if (!settings) {
      return defaultSettings();
    }
    return settings;
  } catch {
    return defaultSettings();
  }
}

export function persistSettings(
  settings: PlayerSettings,
  store: SaveStore,
): void {
  store.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
