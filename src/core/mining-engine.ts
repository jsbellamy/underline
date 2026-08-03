/** Pure mining economy: Dig → Ore → Smelter → Ingots → Upgrade.

Authority: `docs/research/tick-snapshot-save-model.md`,
`docs/research/produce-and-spend-economy.md`.
*/

export const SCHEMA_VERSION = 3 as const;

/** Face damage capacity at Advance 0 on the exponential curve. */
export const FACE_BASE_HARDNESS = 1000;

/** Per-Advance multiplier on Face Hardness. */
export const HARDNESS_GROWTH = 1.15;

/** Damage dealt per Swing (Pick). */
export const PICK_DAMAGE = 1;

/** Ore drops credited per Face before it breaks. */
export const DROPS_PER_FACE = 100;

/** Ore per drop at Advance 0 before the Hardness growth multiplier. */
export const BASE_ORE_PER_DROP = 1;

/** Opening Dig Rate (Swing/sec) before Upgrades. */
export const OPENING_DIG_RATE = 1;

/** Dig Rate gained per Upgrade. */
export const UPGRADE_DIG_RATE = 0.25;

/** Opening Smelter Ore→Ingot throughput (Ore/sec). */
export const SMELTER_THROUGHPUT = 0.06;

/** Smelter throughput gained per Smelter Upgrade. */
export const UPGRADE_SMELTER_THROUGHPUT = 0.02;

/** Opening Carry Capacity in Loads before Upgrades. */
export const OPENING_CARRY_CAPACITY = 10;

/** Carry Capacity gained per Upgrade (Loads). */
export const UPGRADE_CARRY_CAPACITY = 5;

/** Haul round trip in ms (`2 × leg distance / Haul Speed`; distance and speed owned by the Pane). */
export const HAUL_ROUND_TRIP_MS = 8000;

/** First Upgrade cost in Ingots; doubles each buy. */
export const FIRST_UPGRADE_COST = 5;

/** Offline catch-up rate vs live. */
export const OFFLINE_RATE_SCALE = 0.5;

const HAUL_DELIVERY_MS = HAUL_ROUND_TRIP_MS / 2;

export type UpgradeId = "digRate" | "smelter" | "carryCapacity";

export interface MiningSnapshot {
  schemaVersion: typeof SCHEMA_VERSION;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  smelterUpgradeCount: number;
  carryCapacityUpgradeCount: number;
  /** Damage dealt to the current Face (`0…hardnessFor(advance)`); equals Swings spent when Pick Damage is 1. */
  faceSwingProgress: number;
  /** Fractional Ore fed toward the next Ingot (`0…1`). */
  smelterProgress: number;
  /** Ore held in the Bag awaiting Haul delivery. */
  bagOre: number;
  /** Drops currently in the Bag (Load count, not Ore). */
  bagLoads: number;
  /** Remaining Haul countdown in ms; mining suspends while `> 0`. */
  haulRemainingMs: number;
}

export interface AdvanceOptions {
  /** Multiplier on Dig Rate, Smelter throughput, and Haul countdown (offline = 0.5). */
  rateScale?: number;
}

export function hardnessFor(advance: number): number {
  return FACE_BASE_HARDNESS * HARDNESS_GROWTH ** advance;
}

export function dropDamageFor(advance: number): number {
  return hardnessFor(advance) / DROPS_PER_FACE;
}

export function oreForDrop(advance: number): number {
  return BASE_ORE_PER_DROP * HARDNESS_GROWTH ** advance;
}

export function initialSnapshot(): MiningSnapshot {
  return {
    schemaVersion: SCHEMA_VERSION,
    advance: 0,
    ore: 0,
    ingots: 0,
    digRateUpgradeCount: 0,
    smelterUpgradeCount: 0,
    carryCapacityUpgradeCount: 0,
    faceSwingProgress: 0,
    smelterProgress: 0,
    bagOre: 0,
    bagLoads: 0,
    haulRemainingMs: 0,
  };
}

export function digRateFor(digRateUpgradeCount: number): number {
  return OPENING_DIG_RATE + UPGRADE_DIG_RATE * digRateUpgradeCount;
}

export function smelterThroughputFor(smelterUpgradeCount: number): number {
  return SMELTER_THROUGHPUT + UPGRADE_SMELTER_THROUGHPUT * smelterUpgradeCount;
}

export function carryCapacityFor(carryCapacityUpgradeCount: number): number {
  return (
    OPENING_CARRY_CAPACITY + UPGRADE_CARRY_CAPACITY * carryCapacityUpgradeCount
  );
}

export function nextDigRateUpgradeCost(digRateUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** digRateUpgradeCount;
}

export function nextSmelterUpgradeCost(smelterUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** smelterUpgradeCount;
}

export function nextCarryCapacityUpgradeCost(
  carryCapacityUpgradeCount: number,
): number {
  return FIRST_UPGRADE_COST * 2 ** carryCapacityUpgradeCount;
}

/**
 * Event-jump mining for `dtMs` with per-segment Smelter drain (ADR 0012).
 * Ore drops fill the Bag; a full Bag suspends mining for a rate-scaled Haul
 * round trip and delivers at the midpoint.
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

  let gameMs = dtMs * rateScale;
  let {
    advance: advanceCount,
    ore,
    ingots,
    digRateUpgradeCount,
    smelterUpgradeCount,
    carryCapacityUpgradeCount,
    faceSwingProgress,
    smelterProgress,
    bagOre,
    bagLoads,
    haulRemainingMs,
  } = snapshot;

  const digRate = digRateFor(digRateUpgradeCount);
  const damagePerSec = digRate * PICK_DAMAGE;
  const throughput = smelterThroughputFor(smelterUpgradeCount);
  const capacity = carryCapacityFor(carryCapacityUpgradeCount);

  const feedSmelter = (segmentSec: number): void => {
    const fed = Math.min(ore, throughput * segmentSec);
    ore -= fed;
    smelterProgress += fed;
  };

  const deliverBag = (): void => {
    ore += bagOre;
    bagOre = 0;
    bagLoads = 0;
  };

  while (gameMs > 0) {
    if (haulRemainingMs > 0) {
      const msToDelivery =
        haulRemainingMs > HAUL_DELIVERY_MS
          ? haulRemainingMs - HAUL_DELIVERY_MS
          : haulRemainingMs;
      const segmentMs = Math.min(msToDelivery, gameMs);
      feedSmelter(segmentMs / 1000);
      const wasAboveDelivery = haulRemainingMs > HAUL_DELIVERY_MS;
      haulRemainingMs -= segmentMs;
      gameMs -= segmentMs;
      if (wasAboveDelivery && haulRemainingMs <= HAUL_DELIVERY_MS) {
        deliverBag();
      }
      continue;
    }

    if (bagLoads >= capacity) {
      haulRemainingMs = HAUL_ROUND_TRIP_MS;
      continue;
    }

    if (damagePerSec <= 0) {
      feedSmelter(gameMs / 1000);
      gameMs = 0;
      break;
    }

    const hardness = hardnessFor(advanceCount);
    const dropDamage = dropDamageFor(advanceCount);
    const orePerDrop = oreForDrop(advanceCount);

    const dropsSoFar = Math.min(
      DROPS_PER_FACE,
      Math.floor(faceSwingProgress / dropDamage + 1e-9),
    );
    const nextDropAt = (dropsSoFar + 1) * dropDamage;
    const damageToNextDrop = nextDropAt - faceSwingProgress;
    const damageToBreak = hardness - faceSwingProgress;
    const eventDamage = Math.min(damageToNextDrop, damageToBreak);
    const timeToEventSec = eventDamage / damagePerSec;
    const timeToEventMs = timeToEventSec * 1000;

    if (timeToEventMs > gameMs) {
      feedSmelter(gameMs / 1000);
      faceSwingProgress += damagePerSec * (gameMs / 1000);
      gameMs = 0;
      continue;
    }

    feedSmelter(timeToEventMs / 1000);
    gameMs -= timeToEventMs;
    bagOre += orePerDrop;
    bagLoads += 1;
    const landedDrop = dropsSoFar + 1;
    faceSwingProgress = Math.min(landedDrop * dropDamage, hardness);

    if (faceSwingProgress >= hardness) {
      advanceCount += 1;
      faceSwingProgress = 0;
    }

    if (bagLoads >= capacity) {
      haulRemainingMs = HAUL_ROUND_TRIP_MS;
    }
  }

  const minted = Math.floor(smelterProgress);
  ingots += minted;
  smelterProgress -= minted;

  return {
    schemaVersion: SCHEMA_VERSION,
    advance: advanceCount,
    ore,
    ingots,
    digRateUpgradeCount,
    smelterUpgradeCount,
    carryCapacityUpgradeCount,
    faceSwingProgress,
    smelterProgress,
    bagOre,
    bagLoads,
    haulRemainingMs,
  };
}

export function buyUpgrade(
  snapshot: MiningSnapshot,
  upgrade: UpgradeId = "digRate",
): MiningSnapshot {
  if (upgrade === "smelter") {
    const cost = nextSmelterUpgradeCost(snapshot.smelterUpgradeCount);
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      smelterUpgradeCount: snapshot.smelterUpgradeCount + 1,
    };
  }

  if (upgrade === "carryCapacity") {
    const cost = nextCarryCapacityUpgradeCost(snapshot.carryCapacityUpgradeCount);
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      carryCapacityUpgradeCount: snapshot.carryCapacityUpgradeCount + 1,
    };
  }

  const cost = nextDigRateUpgradeCost(snapshot.digRateUpgradeCount);
  if (snapshot.ingots < cost) {
    throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
  }
  return {
    ...snapshot,
    schemaVersion: SCHEMA_VERSION,
    ingots: snapshot.ingots - cost,
    digRateUpgradeCount: snapshot.digRateUpgradeCount + 1,
  };
}
