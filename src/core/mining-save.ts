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

interface PersistedSaveV3 {
  schemaVersion: 3;
  savedAtMs: number;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  smelterUpgradeCount: number;
  carryCapacityUpgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
  bagOre: number;
  bagLoads: number;
  haulRemainingMs: number;
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

type PersistedSave = PersistedSaveV3 | PersistedSaveV2 | PersistedSaveV1;

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function parseV3Fields(raw: {
  advance: unknown;
  ore: unknown;
  ingots: unknown;
  digRateUpgradeCount: unknown;
  smelterUpgradeCount: unknown;
  carryCapacityUpgradeCount: unknown;
  faceSwingProgress: unknown;
  smelterProgress: unknown;
  bagOre: unknown;
  bagLoads: unknown;
  haulRemainingMs: unknown;
}): MiningSnapshot | null {
  if (
    !isFiniteNumber(raw.advance) ||
    !isFiniteNumber(raw.ore) ||
    !isFiniteNumber(raw.ingots) ||
    !isFiniteNumber(raw.digRateUpgradeCount) ||
    !isFiniteNumber(raw.smelterUpgradeCount) ||
    !isFiniteNumber(raw.carryCapacityUpgradeCount) ||
    !isFiniteNumber(raw.faceSwingProgress) ||
    !isFiniteNumber(raw.smelterProgress) ||
    !isFiniteNumber(raw.bagOre) ||
    !isFiniteNumber(raw.bagLoads) ||
    !isFiniteNumber(raw.haulRemainingMs)
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
    carryCapacityUpgradeCount: raw.carryCapacityUpgradeCount,
    crewSize: 1,
    heapLoads: 0,
    heapOre: 0,
    haulSpeedUpgradeCount: 0,
    pickupProgressMs: 0,
    faceSwingProgress: raw.faceSwingProgress,
    smelterProgress: raw.smelterProgress,
    bagOre: raw.bagOre,
    bagLoads: raw.bagLoads,
    haulRemainingMs: raw.haulRemainingMs,
  };
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
    carryCapacityUpgradeCount: 0,
    crewSize: 1,
    heapLoads: 0,
    heapOre: 0,
    haulSpeedUpgradeCount: 0,
    pickupProgressMs: 0,
    faceSwingProgress: raw.faceSwingProgress,
    smelterProgress: raw.smelterProgress,
    bagOre: 0,
    bagLoads: 0,
    haulRemainingMs: 0,
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
      carryCapacityUpgradeCount: 0,
      crewSize: 1,
      heapLoads: 0,
      heapOre: 0,
      haulSpeedUpgradeCount: 0,
      pickupProgressMs: 0,
      faceSwingProgress: raw.faceSwingProgress,
      smelterProgress: raw.smelterProgress,
      bagOre: 0,
      bagLoads: 0,
      haulRemainingMs: 0,
    };
  }
  if (raw.schemaVersion === 2) {
    return parseV2Fields(raw);
  }
  if (raw.schemaVersion !== SCHEMA_VERSION) {
    return null;
  }
  return parseV3Fields(raw);
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
  const payload: PersistedSaveV3 = {
    schemaVersion: SCHEMA_VERSION,
    savedAtMs,
    advance: snapshot.advance,
    ore: snapshot.ore,
    ingots: snapshot.ingots,
    digRateUpgradeCount: snapshot.digRateUpgradeCount,
    smelterUpgradeCount: snapshot.smelterUpgradeCount,
    carryCapacityUpgradeCount: snapshot.carryCapacityUpgradeCount,
    faceSwingProgress: snapshot.faceSwingProgress,
    smelterProgress: snapshot.smelterProgress,
    bagOre: snapshot.bagOre,
    bagLoads: snapshot.bagLoads,
    haulRemainingMs: snapshot.haulRemainingMs,
  };
  store.setItem(SAVE_KEY, JSON.stringify(payload));
}

export function clearSave(store: SaveStore): void {
  store.removeItem(SAVE_KEY);
}

export function browserSaveStore(): SaveStore {
  return window.localStorage;
}
