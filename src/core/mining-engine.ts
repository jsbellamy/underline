/** Pure mining economy: Dig → Ore → Smelter → Ingots → Upgrade.

Authority: `docs/research/tick-snapshot-save-model.md`,
`docs/research/produce-and-spend-economy.md`.
*/

import type { MiningEvent } from "./mining-events";

export const SCHEMA_VERSION = 5 as const;

/** Face damage capacity at Advance 0 on the exponential curve. */
export const FACE_BASE_HARDNESS = 1000;

/** Per-Advance multiplier on Face Hardness. */
export const HARDNESS_GROWTH = 1.15;

/** Per-Upgrade multiplier on Pick Damage. */
export const PICK_DAMAGE_GROWTH = 1.5;

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

/** Per-Upgrade multiplier on Smelter throughput. */
export const SMELTER_GROWTH = 1.5;

/** Opening Carry Capacity in Loads before Upgrades. */
export const OPENING_CARRY_CAPACITY = 10;

/** Carry Capacity gained per Upgrade (Loads). */
export const UPGRADE_CARRY_CAPACITY = 5;

/** Haul round trip in ms (`2 × leg distance / Haul Speed`; distance and speed owned by the Pane). */
export const HAUL_ROUND_TRIP_MS = 8000;

/** First Upgrade cost in Ingots; doubles each buy. */
export const FIRST_UPGRADE_COST = 5;

/** Ms to lift one Load from the Heap before Haul Speed upgrades. */
export const PICKUP_MS_PER_LOAD = 10_000;

/** Ingots to hire the second Dwarf (Hauler). */
export const HIRE_HAULER_COST = 160;

/** Offline catch-up rate vs live. */
export const OFFLINE_RATE_SCALE = 0.5;

const HAUL_DELIVERY_MS = HAUL_ROUND_TRIP_MS / 2;

export type UpgradeId =
  | "digRate"
  | "smelter"
  | "carryCapacity"
  | "haulSpeed"
  | "hireHauler"
  | "pickDamage";

export interface MiningSnapshot {
  schemaVersion: typeof SCHEMA_VERSION;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  pickDamageUpgradeCount: number;
  smelterUpgradeCount: number;
  carryCapacityUpgradeCount: number;
  /** Dwarves in the Crew: 1 before the Hauler is hired, 2 after. */
  crewSize: number;
  /** Loads waiting at the Face for the Hauler; capped at heapCapacityFor(...). */
  heapLoads: number;
  /** Ore those Loads carry. */
  heapOre: number;
  haulSpeedUpgradeCount: number;
  /** Elapsed ms toward lifting the current Load out of the Heap. */
  pickupProgressMs: number;
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
    pickDamageUpgradeCount: 0,
    smelterUpgradeCount: 0,
    carryCapacityUpgradeCount: 0,
    crewSize: 1,
    heapLoads: 0,
    heapOre: 0,
    haulSpeedUpgradeCount: 0,
    pickupProgressMs: 0,
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
  return SMELTER_THROUGHPUT * SMELTER_GROWTH ** smelterUpgradeCount;
}

export function carryCapacityFor(carryCapacityUpgradeCount: number): number {
  return (
    OPENING_CARRY_CAPACITY + UPGRADE_CARRY_CAPACITY * carryCapacityUpgradeCount
  );
}

export function haulSpeedFor(haulSpeedUpgradeCount: number): number {
  return 1 + 0.25 * haulSpeedUpgradeCount;
}

export function pickupMsPerLoad(haulSpeedUpgradeCount: number): number {
  return PICKUP_MS_PER_LOAD / haulSpeedFor(haulSpeedUpgradeCount);
}

export function nextHaulSpeedUpgradeCost(haulSpeedUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** haulSpeedUpgradeCount;
}

/** The Heap's cap in Loads — the same number as the Bag's. */
export function heapCapacityFor(carryCapacityUpgradeCount: number): number {
  return carryCapacityFor(carryCapacityUpgradeCount);
}

export function nextDigRateUpgradeCost(digRateUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** digRateUpgradeCount;
}

export function nextSmelterUpgradeCost(smelterUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** smelterUpgradeCount;
}

export function pickDamageFor(pickDamageUpgradeCount: number): number {
  return PICK_DAMAGE_GROWTH ** pickDamageUpgradeCount;
}

export function nextPickDamageUpgradeCost(pickDamageUpgradeCount: number): number {
  return FIRST_UPGRADE_COST * 2 ** pickDamageUpgradeCount;
}

export function nextCarryCapacityUpgradeCost(
  carryCapacityUpgradeCount: number,
): number {
  return FIRST_UPGRADE_COST * 2 ** carryCapacityUpgradeCount;
}

function collectMiningEvents(
  events: MiningEvent[],
  progress0: number,
  damageDelta: number,
  hardness: number,
  segmentStartAtMs: number,
  damagePerSec: number,
  pickDamage: number,
  rateScale: number,
): void {
  const endProgress = Math.min(progress0 + damageDelta, hardness);
  const breaking = endProgress >= hardness - 1e-9;
  const maxSwing = breaking
    ? Math.floor((hardness - 1e-9) / pickDamage)
    : Math.floor(endProgress / pickDamage + 1e-9);
  const minSwing = Math.floor(progress0 / pickDamage + 1e-9) + 1;
  for (let swing = minSwing; swing <= maxSwing; swing += 1) {
    const progressAtSwing = swing * pickDamage;
    const gameMsToSwing = ((progressAtSwing - progress0) / damagePerSec) * 1000;
    events.push({
      type: "swing",
      atMs: segmentStartAtMs + gameMsToSwing / rateScale,
    });
  }
  if (breaking) {
    const gameMsToBreak = (damageDelta / damagePerSec) * 1000;
    events.push({
      type: "faceBroken",
      atMs: segmentStartAtMs + gameMsToBreak / rateScale,
    });
  }
}

/**
 * Event-jump mining for `dtMs` with per-segment Smelter drain (ADR 0012).
 * One-Dwarf Crew: Ore drops fill the Bag; a full Bag suspends mining for a Haul.
 * Two-Dwarf Crew: Miner drops into the capped Heap; Hauler picks Loads into the
 * Bag and departs only when full (ADR 0014).
 */
export function advanceWithEvents(
  snapshot: MiningSnapshot,
  dtMs: number,
  options: AdvanceOptions = {},
): { snapshot: MiningSnapshot; events: MiningEvent[] } {
  if (!(dtMs >= 0)) {
    throw new Error(`dtMs must be non-negative, got ${dtMs}`);
  }
  const rateScale = options.rateScale ?? 1;
  if (!(rateScale >= 0)) {
    throw new Error(`rateScale must be non-negative, got ${rateScale}`);
  }

  const events: MiningEvent[] = [];
  let windowRealMs = 0;
  let gameMs = dtMs * rateScale;
  let {
    advance: advanceCount,
    ore,
    ingots,
    digRateUpgradeCount,
    pickDamageUpgradeCount,
    smelterUpgradeCount,
    carryCapacityUpgradeCount,
    crewSize,
    heapLoads,
    heapOre,
    haulSpeedUpgradeCount,
    pickupProgressMs,
    faceSwingProgress,
    smelterProgress,
    bagOre,
    bagLoads,
    haulRemainingMs,
  } = snapshot;

  const digRate = digRateFor(digRateUpgradeCount);
  const pickDamage = pickDamageFor(pickDamageUpgradeCount);
  const damagePerSec = digRate * pickDamage;
  const throughput = smelterThroughputFor(smelterUpgradeCount);
  const capacity = carryCapacityFor(carryCapacityUpgradeCount);
  const heapCapacity = heapCapacityFor(carryCapacityUpgradeCount);
  const pickupMs = pickupMsPerLoad(haulSpeedUpgradeCount);
  const isTwoDwarf = crewSize === 2;

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

  const consumeGameMs = (segmentGameMs: number): void => {
    windowRealMs += segmentGameMs / rateScale;
  };

  const startHaulIfBagFull = (): void => {
    if (bagLoads >= capacity) {
      haulRemainingMs = HAUL_ROUND_TRIP_MS;
    }
  };

  const creditDrop = (orePerDrop: number): void => {
    if (isTwoDwarf) {
      heapOre += orePerDrop;
      heapLoads += 1;
    } else {
      bagOre += orePerDrop;
      bagLoads += 1;
      startHaulIfBagFull();
    }
  };

  const transferHeapLoadToBag = (): void => {
    const orePerLoad = heapOre / heapLoads;
    heapOre -= orePerLoad;
    heapLoads -= 1;
    bagOre += orePerLoad;
    bagLoads += 1;
    pickupProgressMs = 0;
    startHaulIfBagFull();
  };

  const miningAllowed = (): boolean => {
    if (damagePerSec <= 0) {
      return false;
    }
    if (isTwoDwarf) {
      return heapLoads < heapCapacity;
    }
    return haulRemainingMs === 0 && bagLoads < capacity;
  };

  const pickupAllowed = (): boolean => {
    return (
      isTwoDwarf &&
      haulRemainingMs === 0 &&
      heapLoads > 0 &&
      bagLoads < capacity
    );
  };

  while (gameMs > 0) {
    if (!isTwoDwarf && bagLoads >= capacity && haulRemainingMs === 0) {
      haulRemainingMs = HAUL_ROUND_TRIP_MS;
      continue;
    }

    const candidates: number[] = [gameMs];

    if (haulRemainingMs > 0) {
      const msToHaulEvent =
        haulRemainingMs > HAUL_DELIVERY_MS
          ? haulRemainingMs - HAUL_DELIVERY_MS
          : haulRemainingMs;
      candidates.push(msToHaulEvent);
    }

    if (pickupAllowed()) {
      candidates.push(pickupMs - pickupProgressMs);
    }

    let miningEventMs: number | null = null;
    let miningEventDamage = 0;
    let miningHardness = 0;
    let miningDropsSoFar = 0;
    let miningDropDamage = 0;

    if (miningAllowed()) {
      miningHardness = hardnessFor(advanceCount);
      miningDropDamage = dropDamageFor(advanceCount);
      miningDropsSoFar = Math.min(
        DROPS_PER_FACE,
        Math.floor(faceSwingProgress / miningDropDamage + 1e-9),
      );
      const nextDropAt = (miningDropsSoFar + 1) * miningDropDamage;
      const damageToNextDrop = nextDropAt - faceSwingProgress;
      const damageToBreak = miningHardness - faceSwingProgress;
      miningEventDamage = Math.min(damageToNextDrop, damageToBreak);
      miningEventMs = (miningEventDamage / damagePerSec) * 1000;
      candidates.push(miningEventMs);
    }

    const segmentMs = Math.min(...candidates);

    if (segmentMs <= 0) {
      break;
    }

    const atMiningBoundary =
      miningEventMs !== null && segmentMs >= miningEventMs - 1e-9;
    const atPickupBoundary =
      pickupAllowed() && segmentMs >= pickupMs - pickupProgressMs - 1e-9;
    const hauling = haulRemainingMs > 0;
    const wasAboveDelivery = hauling && haulRemainingMs > HAUL_DELIVERY_MS;

    if (miningAllowed()) {
      if (atMiningBoundary) {
        collectMiningEvents(
          events,
          faceSwingProgress,
          miningEventDamage,
          miningHardness,
          windowRealMs,
          damagePerSec,
          pickDamage,
          rateScale,
        );
      } else {
        const partialDamage = damagePerSec * (segmentMs / 1000);
        collectMiningEvents(
          events,
          faceSwingProgress,
          partialDamage,
          miningHardness,
          windowRealMs,
          damagePerSec,
          pickDamage,
          rateScale,
        );
        faceSwingProgress += partialDamage;
      }
    }

    feedSmelter(segmentMs / 1000);

    if (pickupAllowed()) {
      pickupProgressMs += segmentMs;
    }

    if (hauling) {
      haulRemainingMs -= segmentMs;
      if (wasAboveDelivery && haulRemainingMs <= HAUL_DELIVERY_MS) {
        deliverBag();
      }
    }

    consumeGameMs(segmentMs);
    gameMs -= segmentMs;

    if (atPickupBoundary) {
      transferHeapLoadToBag();
      if (!atMiningBoundary) {
        continue;
      }
    }

    if (atMiningBoundary) {
      const orePerDrop = oreForDrop(advanceCount);
      creditDrop(orePerDrop);
      events.push({ type: "loadDropped", atMs: windowRealMs });
      const landedDrop = miningDropsSoFar + 1;
      faceSwingProgress = Math.min(
        landedDrop * miningDropDamage,
        miningHardness,
      );
      if (faceSwingProgress >= miningHardness) {
        advanceCount += 1;
        faceSwingProgress = 0;
      }
      continue;
    }

    if (!miningAllowed() && !pickupAllowed() && haulRemainingMs === 0) {
      break;
    }
  }

  const minted = Math.floor(smelterProgress);
  ingots += minted;
  smelterProgress -= minted;

  events.sort((a, b) => a.atMs - b.atMs);

  return {
    snapshot: {
      schemaVersion: SCHEMA_VERSION,
      advance: advanceCount,
      ore,
      ingots,
      digRateUpgradeCount,
      pickDamageUpgradeCount,
      smelterUpgradeCount,
      carryCapacityUpgradeCount,
      crewSize,
      heapLoads,
      heapOre,
      haulSpeedUpgradeCount,
      pickupProgressMs,
      faceSwingProgress,
      smelterProgress,
      bagOre,
      bagLoads,
      haulRemainingMs,
    },
    events,
  };
}

export function advance(
  snapshot: MiningSnapshot,
  dtMs: number,
  options: AdvanceOptions = {},
): MiningSnapshot {
  return advanceWithEvents(snapshot, dtMs, options).snapshot;
}

export function buyUpgrade(
  snapshot: MiningSnapshot,
  upgrade: UpgradeId = "digRate",
): MiningSnapshot {
  if (upgrade === "hireHauler") {
    if (snapshot.crewSize >= 2) {
      throw new Error("Hauler already hired; crewSize is already 2");
    }
    const cost = HIRE_HAULER_COST;
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      crewSize: 2,
    };
  }

  if (upgrade === "haulSpeed") {
    const cost = nextHaulSpeedUpgradeCost(snapshot.haulSpeedUpgradeCount);
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      haulSpeedUpgradeCount: snapshot.haulSpeedUpgradeCount + 1,
    };
  }

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

  if (upgrade === "pickDamage") {
    const cost = nextPickDamageUpgradeCost(snapshot.pickDamageUpgradeCount);
    if (snapshot.ingots < cost) {
      throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
    }
    return {
      ...snapshot,
      schemaVersion: SCHEMA_VERSION,
      ingots: snapshot.ingots - cost,
      pickDamageUpgradeCount: snapshot.pickDamageUpgradeCount + 1,
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
