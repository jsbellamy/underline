/** Pure mining economy: Dig → Ore → Smelter → Ingots → Upgrade.

Authority: `docs/research/tick-snapshot-save-model.md`,
`docs/research/produce-and-spend-economy.md`.
*/

export const SCHEMA_VERSION = 1 as const;

/** Swings per Mineable Block at opening depth (band 0). */
export const HARDNESS = 4;

/** Ore yielded per Face break. */
export const YIELD = 1;

/** Opening Dig Rate (Swing/sec) before Upgrades. */
export const OPENING_DIG_RATE = 1;

/** Dig Rate gained per Upgrade. */
export const UPGRADE_DIG_RATE = 0.25;

/** Opening Smelter Ore→Ingot throughput (Ore/sec). */
export const SMELTER_THROUGHPUT = 0.15;

/** Smelter throughput gained per Smelter Upgrade. */
export const UPGRADE_SMELTER_THROUGHPUT = 0.05;

/** First Upgrade cost in Ingots; doubles each buy. */
export const FIRST_UPGRADE_COST = 5;

/** Offline catch-up rate vs live. */
export const OFFLINE_RATE_SCALE = 0.5;

export type UpgradeId = "digRate" | "smelter";

export interface MiningSnapshot {
  schemaVersion: typeof SCHEMA_VERSION;
  advance: number;
  ore: number;
  ingots: number;
  upgradeCount: number;
  smelterUpgradeCount?: number;
  /** Swings spent on the current Face (`0…Hardness`). */
  faceSwingProgress: number;
  /** Fractional Ore fed toward the next Ingot (`0…1`). */
  smelterProgress: number;
}

export interface AdvanceOptions {
  /** Multiplier on Dig Rate and Smelter throughput (offline = 0.5). */
  rateScale?: number;
}

export function hardnessFor(advance: number): number {
  if (advance < 25) return HARDNESS;
  if (advance < 75) return 5;
  if (advance < 150) return 6;
  return 7;
}

export function initialSnapshot(): MiningSnapshot {
  return {
    schemaVersion: SCHEMA_VERSION,
    advance: 0,
    ore: 0,
    ingots: 0,
    upgradeCount: 0,
    smelterUpgradeCount: 0,
    faceSwingProgress: 0,
    smelterProgress: 0,
  };
}

export function digRateFor(upgradeCount: number): number {
  return OPENING_DIG_RATE + UPGRADE_DIG_RATE * upgradeCount;
}

export function smelterThroughputFor(smelterUpgradeCount: number): number {
  return SMELTER_THROUGHPUT + UPGRADE_SMELTER_THROUGHPUT * smelterUpgradeCount;
}

export function nextUpgradeCost(upgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** upgradeCount;
}

export function nextSmelterUpgradeCost(smelterUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** smelterUpgradeCount;
}

/**
 * Dig-all Face breaks for `dtMs`, then Smelter-drain for the same window.
 * Matches the offline closed-form order in the engine contract.
 */
export function advance(
  snapshot: MiningSnapshot,
  dtMs: number,
  options: AdvanceOptions = {},
): MiningSnapshot {
  if (!(dtMs >= 0)) {
    throw new Error(`dtMs must be non-negative, got ${dtMs}`);
  }
  const rateScale = options.rateScale ?? 1;
  if (!(rateScale >= 0)) {
    throw new Error(`rateScale must be non-negative, got ${rateScale}`);
  }

  const dtSec = (dtMs / 1000) * rateScale;
  let {
    advance: advanceCount,
    ore,
    ingots,
    upgradeCount,
    smelterUpgradeCount,
    faceSwingProgress,
    smelterProgress,
  } = snapshot;

  const digRate = digRateFor(upgradeCount);
  let swings = faceSwingProgress + digRate * dtSec;
  while (swings >= hardnessFor(advanceCount)) {
    const hardness = hardnessFor(advanceCount);
    swings -= hardness;
    advanceCount += 1;
    ore += YIELD;
  }
  faceSwingProgress = swings;

  const throughput = smelterThroughputFor(smelterUpgradeCount ?? 0);
  const fed = Math.min(ore, throughput * dtSec);
  ore -= fed;
  smelterProgress += fed;
  const minted = Math.floor(smelterProgress);
  ingots += minted;
  smelterProgress -= minted;

  const result: MiningSnapshot = {
    schemaVersion: SCHEMA_VERSION,
    advance: advanceCount,
    ore,
    ingots,
    upgradeCount,
    faceSwingProgress,
    smelterProgress,
  };
  if (smelterUpgradeCount !== undefined) {
    result.smelterUpgradeCount = smelterUpgradeCount;
  }
  return result;
}

export function buyUpgrade(
  snapshot: MiningSnapshot,
  upgrade: UpgradeId = "digRate",
): MiningSnapshot {
  const smelterCount = snapshot.smelterUpgradeCount ?? 0;

  if (upgrade === "smelter") {
    const cost = nextSmelterUpgradeCost(smelterCount);
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      smelterUpgradeCount: smelterCount + 1,
    };
  }

  const cost = nextUpgradeCost(snapshot.upgradeCount);
  if (snapshot.ingots < cost) {
    throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
  }
  return {
    ...snapshot,
    schemaVersion: SCHEMA_VERSION,
    ingots: snapshot.ingots - cost,
    upgradeCount: snapshot.upgradeCount + 1,
    smelterUpgradeCount: smelterCount,
  };
}
