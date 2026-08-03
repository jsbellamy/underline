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

interface PersistedSaveV2 {
  schemaVersion: 2;
  savedAtMs: number;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  smelterUpgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
}

interface PersistedSaveV1 {
  schemaVersion: 1;
  savedAtMs: number;
  advance: number;
  ore: number;
  ingots: number;
  upgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
}

type PersistedSave = PersistedSaveV2 | PersistedSaveV1;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parseV2Fields(raw: {
  advance: unknown;
  ore: unknown;
  ingots: unknown;
  digRateUpgradeCount: unknown;
  smelterUpgradeCount: unknown;
  faceSwingProgress: unknown;
  smelterProgress: unknown;
}): MiningSnapshot | null {
  if (
    !isFiniteNumber(raw.advance) ||
    !isFiniteNumber(raw.ore) ||
    !isFiniteNumber(raw.ingots) ||
    !isFiniteNumber(raw.digRateUpgradeCount) ||
    !isFiniteNumber(raw.smelterUpgradeCount) ||
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
    digRateUpgradeCount: raw.digRateUpgradeCount,
    smelterUpgradeCount: raw.smelterUpgradeCount,
    faceSwingProgress: raw.faceSwingProgress,
    smelterProgress: raw.smelterProgress,
  };
}

function parseSnapshot(raw: PersistedSave): MiningSnapshot | null {
  if (raw.schemaVersion === 1) {
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
      digRateUpgradeCount: raw.upgradeCount,
      smelterUpgradeCount: 0,
      faceSwingProgress: raw.faceSwingProgress,
      smelterProgress: raw.smelterProgress,
    };
  }
  if (raw.schemaVersion !== SCHEMA_VERSION) {
    return null;
  }
  return parseV2Fields(raw);
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
  const payload: PersistedSaveV2 = {
    schemaVersion: SCHEMA_VERSION,
    savedAtMs,
    advance: snapshot.advance,
    ore: snapshot.ore,
    ingots: snapshot.ingots,
    digRateUpgradeCount: snapshot.digRateUpgradeCount,
    smelterUpgradeCount: snapshot.smelterUpgradeCount,
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
