/** Pane-owned JSON save for the mining Snapshot (`underline-save-v1`). */

import {
  SCHEMA_VERSION,
  initialSnapshot,
  type MiningSnapshot,
} from "./mining-engine";

export const SAVE_KEY = "underline-save-v1";

export interface SaveStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface LoadedSave {
  snapshot: MiningSnapshot;
  savedAtMs: number | undefined;
}

interface PersistedSave {
  schemaVersion: number;
  savedAtMs: number;
  advance: number;
  ore: number;
  ingots: number;
  upgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parseSnapshot(raw: PersistedSave): MiningSnapshot | null {
  if (raw.schemaVersion !== SCHEMA_VERSION) {
    return null;
  }
  if (
    !isFiniteNumber(raw.advance) ||
    !isFiniteNumber(raw.ore) ||
    !isFiniteNumber(raw.ingots) ||
    !isFiniteNumber(raw.upgradeCount) ||
    !isFiniteNumber(raw.faceSwingProgress) ||
    !isFiniteNumber(raw.smelterProgress)
  ) {
    return null;
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    advance: raw.advance,
    ore: raw.ore,
    ingots: raw.ingots,
    upgradeCount: raw.upgradeCount,
    faceSwingProgress: raw.faceSwingProgress,
    smelterProgress: raw.smelterProgress,
  };
}

export function loadSave(store: SaveStore): LoadedSave {
  const text = store.getItem(SAVE_KEY);
  if (text == null) {
    return { snapshot: initialSnapshot(), savedAtMs: undefined };
  }
  try {
    const raw = JSON.parse(text) as PersistedSave;
    const snapshot = parseSnapshot(raw);
    if (!snapshot || !isFiniteNumber(raw.savedAtMs)) {
      return { snapshot: initialSnapshot(), savedAtMs: undefined };
    }
    return { snapshot, savedAtMs: raw.savedAtMs };
  } catch {
    return { snapshot: initialSnapshot(), savedAtMs: undefined };
  }
}

export function persistSave(
  snapshot: MiningSnapshot,
  savedAtMs: number,
  store: SaveStore,
): void {
  const payload: PersistedSave = {
    schemaVersion: SCHEMA_VERSION,
    savedAtMs,
    advance: snapshot.advance,
    ore: snapshot.ore,
    ingots: snapshot.ingots,
    upgradeCount: snapshot.upgradeCount,
    faceSwingProgress: snapshot.faceSwingProgress,
    smelterProgress: snapshot.smelterProgress,
  };
  store.setItem(SAVE_KEY, JSON.stringify(payload));
}

export function clearSave(store: SaveStore): void {
  store.removeItem(SAVE_KEY);
}

export function browserSaveStore(): SaveStore {
  return window.localStorage;
}
