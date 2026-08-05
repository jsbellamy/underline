/** Pure mining economy: Dig → Ore → Smelter → Ingots → Upgrade.

Authority: `docs/research/tick-snapshot-save-model.md`,
`docs/research/produce-and-spend-economy.md`.
*/

import type { MiningEvent } from "./mining-events";
import {
  upgradeCostFor,
  upgradeSpec,
  type UpgradeId,
} from "../data/upgrade-catalogue";

export type { UpgradeId } from "../data/upgrade-catalogue";
export {
  FIRST_UPGRADE_COST,
  HIRE_HAULER_COST,
} from "../data/upgrade-catalogue";

export const SCHEMA_VERSION = 6 as const;

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

/** Opening Heap capacity in Loads before Upgrades. */
export const HEAP_BASE_LOADS = 20;

/** Both Haul legs combined; the Pane sizes its walk speed from this. */
export const HAUL_TRAVEL_MS = 4_000;
/** Fixed dwell at the Cart while the Bag empties. */
export const UNLOAD_MS = 4_000;
/** Haul round trip in ms at zero Unload Speed upgrades (`HAUL_TRAVEL_MS + UNLOAD_MS`). */
export const HAUL_ROUND_TRIP_MS = HAUL_TRAVEL_MS + UNLOAD_MS;
/** Haul countdown at which the Bag is credited — arrival at the Cart (zero Unload Speed upgrades). */
export const HAUL_DELIVERY_MS = UNLOAD_MS + HAUL_TRAVEL_MS / 2;

/** Maximum Loads the Hauler can take in one Lift before Upgrades. */
export const OPENING_GRAB_SIZE = 1;

/** Ms to lift one Load from the Heap before Haul Speed upgrades. */
export const PICKUP_MS_PER_LOAD = 3_000;

/** Offline catch-up rate vs live. */
export const OFFLINE_RATE_SCALE = 0.5;

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
  grabSizeUpgradeCount: number;
  unloadSpeedUpgradeCount: number;
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
    grabSizeUpgradeCount: 0,
    unloadSpeedUpgradeCount: 0,
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

/** Maximum Loads the Hauler can take in one Lift. */
export function grabSizeFor(grabSizeUpgradeCount: number): number {
  return OPENING_GRAB_SIZE + grabSizeUpgradeCount;
}

export function nextGrabSizeUpgradeCost(grabSizeUpgradeCount: number): number {
  return upgradeCostFor("grabSize", grabSizeUpgradeCount);
}

export function unloadSpeedFor(unloadSpeedUpgradeCount: number): number {
  return 1 + 0.5 * unloadSpeedUpgradeCount;
}

export function unloadMsFor(unloadSpeedUpgradeCount: number): number {
  return UNLOAD_MS / unloadSpeedFor(unloadSpeedUpgradeCount);
}

export function nextUnloadSpeedUpgradeCost(unloadSpeedUpgradeCount: number): number {
  return upgradeCostFor("unloadSpeed", unloadSpeedUpgradeCount);
}

export function haulRoundTripMsFor(unloadSpeedUpgradeCount: number): number {
  return HAUL_TRAVEL_MS + unloadMsFor(unloadSpeedUpgradeCount);
}

export function haulDeliveryMsFor(unloadSpeedUpgradeCount: number): number {
  return unloadMsFor(unloadSpeedUpgradeCount) + HAUL_TRAVEL_MS / 2;
}

export function nextHaulSpeedUpgradeCost(haulSpeedUpgradeCount: number): number {
  return upgradeCostFor("haulSpeed", haulSpeedUpgradeCount);
}

/** The Heap's cap in Loads — decoupled from the Bag's Carry Capacity base. */
export function heapCapacityFor(carryCapacityUpgradeCount: number): number {
  return HEAP_BASE_LOADS + UPGRADE_CARRY_CAPACITY * carryCapacityUpgradeCount;
}

export function nextDigRateUpgradeCost(digRateUpgradeCount: number): number {
  return upgradeCostFor("digRate", digRateUpgradeCount);
}

export function nextSmelterUpgradeCost(smelterUpgradeCount: number): number {
  return upgradeCostFor("smelter", smelterUpgradeCount);
}

export function pickDamageFor(pickDamageUpgradeCount: number): number {
  return PICK_DAMAGE_GROWTH ** pickDamageUpgradeCount;
}

export function nextPickDamageUpgradeCost(pickDamageUpgradeCount: number): number {
  return upgradeCostFor("pickDamage", pickDamageUpgradeCount);
}

export function nextCarryCapacityUpgradeCost(
  carryCapacityUpgradeCount: number,
): number {
  return upgradeCostFor("carryCapacity", carryCapacityUpgradeCount);
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
 * Two-Dwarf Crew: Miner drops into the capped Heap; Hauler lifts one Load per
 * Trip, travels, unloads at the Cart, and returns (ADR 0017).
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
    grabSizeUpgradeCount,
    unloadSpeedUpgradeCount,
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
  const grabSize = grabSizeFor(grabSizeUpgradeCount);
  const haulRoundTripMs = haulRoundTripMsFor(unloadSpeedUpgradeCount);
  const haulDeliveryMs = haulDeliveryMsFor(unloadSpeedUpgradeCount);
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

  const startOneDwarfHaulIfBagFull = (): void => {
    if (bagLoads >= capacity) {
      haulRemainingMs = haulRoundTripMs;
    }
  };

  const creditDrop = (orePerDrop: number): boolean => {
    if (!isTwoDwarf) {
      bagOre += orePerDrop;
      bagLoads += 1;
      startOneDwarfHaulIfBagFull();
      return false;
    }
    if (heapLoads >= heapCapacity) {
      return true;
    }
    heapOre += orePerDrop;
    heapLoads += 1;
    return false;
  };

  const transferHeapGrabToBag = (): void => {
    const grabbedLoads = Math.min(heapLoads, grabSize - bagLoads);
    const orePerLoad = heapOre / heapLoads;
    heapOre -= orePerLoad * grabbedLoads;
    heapLoads -= grabbedLoads;
    bagOre += orePerLoad * grabbedLoads;
    bagLoads += grabbedLoads;
    pickupProgressMs = 0;
    haulRemainingMs = haulRoundTripMs;
  };

  const miningAllowed = (): boolean => {
    if (damagePerSec <= 0) {
      return false;
    }
    if (isTwoDwarf) {
      return true;
    }
    return haulRemainingMs === 0 && bagLoads < capacity;
  };

  const pickupAllowed = (): boolean => {
    const bagRoom = isTwoDwarf ? grabSize : capacity;
    return (
      isTwoDwarf &&
      haulRemainingMs === 0 &&
      heapLoads > 0 &&
      bagLoads < bagRoom
    );
  };

  while (gameMs > 0) {
    // A carried two-Dwarf Grab always departs; Grab Size is a maximum, not a
    // fill threshold. A one-Dwarf Crew still waits for its Bag to fill.
    const bagReadyToDepart = isTwoDwarf
      ? bagLoads > 0
      : bagLoads >= capacity;
    if (bagReadyToDepart && haulRemainingMs === 0) {
      haulRemainingMs = haulRoundTripMs;
      continue;
    }

    const candidates: number[] = [gameMs];

    if (haulRemainingMs > 0) {
      const msToHaulEvent =
        haulRemainingMs > haulDeliveryMs
          ? haulRemainingMs - haulDeliveryMs
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
    const wasAboveDelivery = hauling && haulRemainingMs > haulDeliveryMs;

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
      if (wasAboveDelivery && haulRemainingMs <= haulDeliveryMs) {
        deliverBag();
      }
    }

    consumeGameMs(segmentMs);
    gameMs -= segmentMs;

    if (atPickupBoundary) {
      transferHeapGrabToBag();
      if (!atMiningBoundary) {
        continue;
      }
    }

    if (atMiningBoundary) {
      const orePerDrop = oreForDrop(advanceCount);
      const spilled = creditDrop(orePerDrop);
      events.push({
        type: spilled ? "loadSpilled" : "loadDropped",
        atMs: windowRealMs,
      });
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
      grabSizeUpgradeCount,
      unloadSpeedUpgradeCount,
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
  const spec = upgradeSpec(upgrade);

  if (spec.effect.kind === "hireHauler") {
    if (snapshot.crewSize >= 2) {
      throw new Error("Hauler already hired; crewSize is already 2");
    }
  }

  const owned =
    spec.effect.kind === "raiseCount" ? snapshot[spec.effect.field] : 0;
  const cost = spec.cost(owned);

  if (snapshot.ingots < cost) {
    throw new Error(`Upgrade costs ${cost} Ingots; have ${snapshot.ingots}`);
  }

  const base = {
    ...snapshot,
    schemaVersion: SCHEMA_VERSION,
    ingots: snapshot.ingots - cost,
  };

  if (spec.effect.kind === "hireHauler") {
    return { ...base, crewSize: 2 };
  }

  const field = spec.effect.field;
  return { ...base, [field]: snapshot[field] + 1 };
}
