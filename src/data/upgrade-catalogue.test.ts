import { describe, expect, it } from "vitest";
import type { MiningSnapshot } from "../core/mining-engine";
import {
  FIRST_UPGRADE_COST,
  HIRE_HAULER_COST,
  isUpgradeId,
  UPGRADE_CATALOGUE,
  upgradeCostFor,
  upgradeSpec,
  type CountField,
  type UpgradeId,
} from "./upgrade-catalogue";

const ALL_UPGRADE_IDS: UpgradeId[] = [
  "digRate",
  "pickDamage",
  "smelter",
  "carryCapacity",
  "haulSpeed",
  "grabSize",
  "unloadSpeed",
  "hireHauler",
];

describe("upgrade catalogue", () => {
  it("pins the opening Upgrade and Hire Hauler costs", () => {
    expect(FIRST_UPGRADE_COST).toBe(5);
    expect(HIRE_HAULER_COST).toBe(160);
  });

  it("doubles counted Upgrade cost from the owned count", () => {
    expect(upgradeCostFor("digRate", 0)).toBe(5);
    expect(upgradeCostFor("digRate", 1)).toBe(10);
    expect(upgradeCostFor("digRate", 2)).toBe(20);
    expect(upgradeCostFor("digRate", 3)).toBe(40);
  });

  it("charges a flat Ingot price to hire the Hauler", () => {
    expect(upgradeCostFor("hireHauler", 0)).toBe(160);
    expect(upgradeCostFor("hireHauler", 1)).toBe(160);
  });

  it("throws for an unknown Upgrade id", () => {
    expect(() => upgradeSpec("missing" as UpgradeId)).toThrow(
      "Unknown Upgrade: missing",
    );
  });

  it("declares eight Upgrades in catalogue order with unique ids and count fields", () => {
    expect(UPGRADE_CATALOGUE).toHaveLength(8);
    expect(UPGRADE_CATALOGUE.map((entry) => entry.id)).toEqual(ALL_UPGRADE_IDS);

    const ids = new Set<UpgradeId>();
    const countFields = new Set<CountField>();
    const snapshotKeys = new Set(
      Object.keys({
        schemaVersion: 0,
        advance: 0,
        ore: 0,
        ingots: 0,
        digRateUpgradeCount: 0,
        pickDamageUpgradeCount: 0,
        smelterUpgradeCount: 0,
        carryCapacityUpgradeCount: 0,
        crewSize: 0,
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
      } satisfies Record<keyof MiningSnapshot, number>),
    );

    for (const entry of UPGRADE_CATALOGUE) {
      expect(ids.has(entry.id)).toBe(false);
      ids.add(entry.id);

      if (entry.effect.kind === "raiseCount") {
        expect(countFields.has(entry.effect.field)).toBe(false);
        countFields.add(entry.effect.field);
        expect(snapshotKeys.has(entry.effect.field)).toBe(true);
      } else {
        expect(entry.effect.kind).toBe("hireHauler");
      }
    }

    for (const id of ALL_UPGRADE_IDS) {
      expect(ids.has(id)).toBe(true);
      expect(upgradeSpec(id).id).toBe(id);
    }
  });

  it("declares Dock labels and crew-size visibility for every Upgrade", () => {
    const labels: Record<UpgradeId, string> = {
      digRate: "Buy Upgrade (+0.25 Dig Rate)",
      pickDamage: "Buy Pick Damage Upgrade (×1.5 Pick Damage)",
      smelter: "Buy Smelter Upgrade (×1.5 Ore/sec)",
      carryCapacity: "Buy Carry Capacity Upgrade (+5 loads)",
      haulSpeed: "Buy Haul Speed Upgrade (+0.25 Haul Speed)",
      grabSize: "Buy Grab Size Upgrade (+1 Grab Size)",
      unloadSpeed: "Buy Unload Speed Upgrade (+0.5 Unload Speed)",
      hireHauler: "Hire a Hauler",
    };
    const offeredAtCrewSize: Record<UpgradeId, readonly number[]> = {
      digRate: [1, 2],
      pickDamage: [1, 2],
      smelter: [1, 2],
      carryCapacity: [1, 2],
      haulSpeed: [1, 2],
      grabSize: [2],
      unloadSpeed: [2],
      hireHauler: [1, 2],
    };

    for (const entry of UPGRADE_CATALOGUE) {
      expect(entry.label).toBe(labels[entry.id]);
      expect(entry.offeredAtCrewSize).toEqual(offeredAtCrewSize[entry.id]);
    }
  });

  it("accepts catalogue Upgrade ids and rejects unknown values", () => {
    for (const id of ALL_UPGRADE_IDS) {
      expect(isUpgradeId(id)).toBe(true);
    }
    expect(isUpgradeId("hardness")).toBe(false);
    expect(isUpgradeId(null)).toBe(false);
  });
});
