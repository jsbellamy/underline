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

interface PersistedSaveV6 {
  schemaVersion: 6;
  savedAtMs: number;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  pickDamageUpgradeCount: number;
  smelterUpgradeCount: number;
  carryCapacityUpgradeCount: number;
  crewSize: number;
  heapLoads: number;
  heapOre: number;
  haulSpeedUpgradeCount: number;
  grabSizeUpgradeCount: number;
  unloadSpeedUpgradeCount: number;
  pickupProgressMs: number;
  faceSwingProgress: number;
  smelterProgress: number;
  bagOre: number;
  bagLoads: number;
  haulRemainingMs: number;
}

type SnapshotField = keyof Omit<MiningSnapshot, "schemaVersion">;

type PersistedFieldSpec =
  | { kind: "required"; key: string }
  | { kind: "optional"; key: string; default: number }
  | { kind: "alias"; from: string; to: SnapshotField };

interface VersionSpec {
  schemaVersion: number;
  fields: readonly PersistedFieldSpec[];
  defaults: Readonly<Partial<Record<SnapshotField, number>>>;
}

const ZERO_DEFAULTS: Readonly<Partial<Record<SnapshotField, number>>> = {
  pickDamageUpgradeCount: 0,
  smelterUpgradeCount: 0,
  carryCapacityUpgradeCount: 0,
  crewSize: 1,
  heapLoads: 0,
  heapOre: 0,
  haulSpeedUpgradeCount: 0,
  grabSizeUpgradeCount: 0,
  unloadSpeedUpgradeCount: 0,
  pickupProgressMs: 0,
  bagOre: 0,
  bagLoads: 0,
  haulRemainingMs: 0,
};

const VERSION_TABLE: readonly VersionSpec[] = [
  {
    schemaVersion: 1,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "alias", from: "upgradeCount", to: "digRateUpgradeCount" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
    ],
    defaults: ZERO_DEFAULTS,
  },
  {
    schemaVersion: 2,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "required", key: "digRateUpgradeCount" },
      { kind: "required", key: "smelterUpgradeCount" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
    ],
    defaults: ZERO_DEFAULTS,
  },
  {
    schemaVersion: 3,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "required", key: "digRateUpgradeCount" },
      { kind: "required", key: "smelterUpgradeCount" },
      { kind: "required", key: "carryCapacityUpgradeCount" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
      { kind: "required", key: "bagOre" },
      { kind: "required", key: "bagLoads" },
      { kind: "required", key: "haulRemainingMs" },
    ],
    defaults: {
      pickDamageUpgradeCount: 0,
      crewSize: 1,
      heapLoads: 0,
      heapOre: 0,
      haulSpeedUpgradeCount: 0,
      grabSizeUpgradeCount: 0,
      unloadSpeedUpgradeCount: 0,
      pickupProgressMs: 0,
    },
  },
  {
    schemaVersion: 4,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "required", key: "digRateUpgradeCount" },
      { kind: "required", key: "smelterUpgradeCount" },
      { kind: "required", key: "carryCapacityUpgradeCount" },
      { kind: "required", key: "crewSize" },
      { kind: "required", key: "heapLoads" },
      { kind: "required", key: "heapOre" },
      { kind: "required", key: "haulSpeedUpgradeCount" },
      { kind: "required", key: "pickupProgressMs" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
      { kind: "required", key: "bagOre" },
      { kind: "required", key: "bagLoads" },
      { kind: "required", key: "haulRemainingMs" },
    ],
    defaults: {
      pickDamageUpgradeCount: 0,
      grabSizeUpgradeCount: 0,
      unloadSpeedUpgradeCount: 0,
    },
  },
  {
    schemaVersion: 5,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "required", key: "digRateUpgradeCount" },
      { kind: "required", key: "pickDamageUpgradeCount" },
      { kind: "required", key: "smelterUpgradeCount" },
      { kind: "required", key: "carryCapacityUpgradeCount" },
      { kind: "required", key: "crewSize" },
      { kind: "required", key: "heapLoads" },
      { kind: "required", key: "heapOre" },
      { kind: "required", key: "haulSpeedUpgradeCount" },
      { kind: "required", key: "pickupProgressMs" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
      { kind: "required", key: "bagOre" },
      { kind: "required", key: "bagLoads" },
      { kind: "required", key: "haulRemainingMs" },
    ],
    defaults: {
      grabSizeUpgradeCount: 0,
      unloadSpeedUpgradeCount: 0,
    },
  },
  {
    schemaVersion: 6,
    fields: [
      { kind: "required", key: "advance" },
      { kind: "required", key: "ore" },
      { kind: "required", key: "ingots" },
      { kind: "required", key: "digRateUpgradeCount" },
      { kind: "required", key: "pickDamageUpgradeCount" },
      { kind: "required", key: "smelterUpgradeCount" },
      { kind: "required", key: "carryCapacityUpgradeCount" },
      { kind: "required", key: "crewSize" },
      { kind: "required", key: "heapLoads" },
      { kind: "required", key: "heapOre" },
      { kind: "required", key: "haulSpeedUpgradeCount" },
      { kind: "optional", key: "grabSizeUpgradeCount", default: 0 },
      { kind: "optional", key: "unloadSpeedUpgradeCount", default: 0 },
      { kind: "required", key: "pickupProgressMs" },
      { kind: "required", key: "faceSwingProgress" },
      { kind: "required", key: "smelterProgress" },
      { kind: "required", key: "bagOre" },
      { kind: "required", key: "bagLoads" },
      { kind: "required", key: "haulRemainingMs" },
    ],
    defaults: {},
  },
];

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function readPersistedFields(
  raw: Record<string, unknown>,
  fields: readonly PersistedFieldSpec[],
): Partial<Record<SnapshotField, number>> | null {
  const values: Partial<Record<SnapshotField, number>> = {};
  for (const field of fields) {
    if (field.kind === "required") {
      if (!isFiniteNumber(raw[field.key])) {
        return null;
      }
      values[field.key as SnapshotField] = raw[field.key] as number;
    } else if (field.kind === "optional") {
      values[field.key as SnapshotField] = isFiniteNumber(raw[field.key])
        ? (raw[field.key] as number)
        : field.default;
    } else {
      if (!isFiniteNumber(raw[field.from])) {
        return null;
      }
      values[field.to] = raw[field.from] as number;
    }
  }
  return values;
}

function snapshotFromVersionSpec(
  spec: VersionSpec,
  raw: Record<string, unknown>,
): MiningSnapshot | null {
  const values = readPersistedFields(raw, spec.fields);
  if (!values) {
    return null;
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    advance: values.advance!,
    ore: values.ore!,
    ingots: values.ingots!,
    digRateUpgradeCount: values.digRateUpgradeCount!,
    pickDamageUpgradeCount:
      values.pickDamageUpgradeCount ?? spec.defaults.pickDamageUpgradeCount ?? 0,
    smelterUpgradeCount:
      values.smelterUpgradeCount ?? spec.defaults.smelterUpgradeCount ?? 0,
    carryCapacityUpgradeCount:
      values.carryCapacityUpgradeCount ??
      spec.defaults.carryCapacityUpgradeCount ??
      0,
    crewSize: values.crewSize ?? spec.defaults.crewSize ?? 1,
    heapLoads: values.heapLoads ?? spec.defaults.heapLoads ?? 0,
    heapOre: values.heapOre ?? spec.defaults.heapOre ?? 0,
    haulSpeedUpgradeCount:
      values.haulSpeedUpgradeCount ?? spec.defaults.haulSpeedUpgradeCount ?? 0,
    grabSizeUpgradeCount:
      values.grabSizeUpgradeCount ?? spec.defaults.grabSizeUpgradeCount ?? 0,
    unloadSpeedUpgradeCount:
      values.unloadSpeedUpgradeCount ??
      spec.defaults.unloadSpeedUpgradeCount ??
      0,
    pickupProgressMs:
      values.pickupProgressMs ?? spec.defaults.pickupProgressMs ?? 0,
    faceSwingProgress: values.faceSwingProgress!,
    smelterProgress: values.smelterProgress!,
    bagOre: values.bagOre ?? spec.defaults.bagOre ?? 0,
    bagLoads: values.bagLoads ?? spec.defaults.bagLoads ?? 0,
    haulRemainingMs:
      values.haulRemainingMs ?? spec.defaults.haulRemainingMs ?? 0,
  };
}

function parseSnapshot(raw: Record<string, unknown>): MiningSnapshot | null {
  const schemaVersion = raw["schemaVersion"];
  if (!isFiniteNumber(schemaVersion)) {
    return null;
  }
  const spec = VERSION_TABLE.find((entry) => entry.schemaVersion === schemaVersion);
  if (!spec) {
    return null;
  }
  return snapshotFromVersionSpec(spec, raw);
}

export function loadSave(store: SaveStore): LoadedSave {
  const text = store.getItem(SAVE_KEY);
  if (text == null) {
    return { snapshot: initialSnapshot(), savedAtMs: undefined };
  }
  try {
    const raw = JSON.parse(text) as Record<string, unknown>;
    const snapshot = parseSnapshot(raw);
    if (!snapshot || !isFiniteNumber(raw["savedAtMs"])) {
      return { snapshot: initialSnapshot(), savedAtMs: undefined };
    }
    return { snapshot, savedAtMs: raw["savedAtMs"] };
  } catch {
    return { snapshot: initialSnapshot(), savedAtMs: undefined };
  }
}

export function persistSave(
  snapshot: MiningSnapshot,
  savedAtMs: number,
  store: SaveStore,
): void {
  const payload: PersistedSaveV6 = {
    schemaVersion: SCHEMA_VERSION,
    savedAtMs,
    advance: snapshot.advance,
    ore: snapshot.ore,
    ingots: snapshot.ingots,
    digRateUpgradeCount: snapshot.digRateUpgradeCount,
    pickDamageUpgradeCount: snapshot.pickDamageUpgradeCount,
    smelterUpgradeCount: snapshot.smelterUpgradeCount,
    carryCapacityUpgradeCount: snapshot.carryCapacityUpgradeCount,
    crewSize: snapshot.crewSize,
    heapLoads: snapshot.heapLoads,
    heapOre: snapshot.heapOre,
    haulSpeedUpgradeCount: snapshot.haulSpeedUpgradeCount,
    grabSizeUpgradeCount: snapshot.grabSizeUpgradeCount,
    unloadSpeedUpgradeCount: snapshot.unloadSpeedUpgradeCount,
    pickupProgressMs: snapshot.pickupProgressMs,
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
