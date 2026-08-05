/** Upgrade catalogue — one declaration per Upgrade (id, Ingot cost curve, effect).

Content data only: no simulation imports. The mining engine resolves entries
and applies declared effects.
*/

export const FIRST_UPGRADE_COST = 5;

/** Ingots to hire the second Dwarf (Hauler). */
export const HIRE_HAULER_COST = 160;

export type UpgradeId =
  | "digRate"
  | "pickDamage"
  | "smelter"
  | "carryCapacity"
  | "haulSpeed"
  | "grabSize"
  | "unloadSpeed"
  | "hireHauler";

export type CountField =
  | "digRateUpgradeCount"
  | "pickDamageUpgradeCount"
  | "smelterUpgradeCount"
  | "carryCapacityUpgradeCount"
  | "haulSpeedUpgradeCount"
  | "grabSizeUpgradeCount"
  | "unloadSpeedUpgradeCount";

export type UpgradeEffect =
  | { readonly kind: "raiseCount"; readonly field: CountField }
  | { readonly kind: "hireHauler" };

export interface UpgradeSpec {
  readonly id: UpgradeId;
  readonly effect: UpgradeEffect;
  /** Ingot cost of the next purchase, given the count already owned. */
  cost(owned: number): number;
}

function doublingCost(owned: number): number {
  return FIRST_UPGRADE_COST * 2 ** owned;
}

function countedUpgrade(
  id: UpgradeId,
  field: CountField,
): UpgradeSpec {
  return {
    id,
    effect: { kind: "raiseCount", field },
    cost: doublingCost,
  };
}

export const UPGRADE_CATALOGUE: readonly UpgradeSpec[] = [
  countedUpgrade("digRate", "digRateUpgradeCount"),
  countedUpgrade("pickDamage", "pickDamageUpgradeCount"),
  countedUpgrade("smelter", "smelterUpgradeCount"),
  countedUpgrade("carryCapacity", "carryCapacityUpgradeCount"),
  countedUpgrade("haulSpeed", "haulSpeedUpgradeCount"),
  countedUpgrade("grabSize", "grabSizeUpgradeCount"),
  countedUpgrade("unloadSpeed", "unloadSpeedUpgradeCount"),
  {
    id: "hireHauler",
    effect: { kind: "hireHauler" },
    cost: () => HIRE_HAULER_COST,
  },
];

const byId = new Map(UPGRADE_CATALOGUE.map((spec) => [spec.id, spec]));

export function upgradeSpec(id: UpgradeId): UpgradeSpec {
  const spec = byId.get(id);
  if (!spec) {
    throw new Error(`Unknown Upgrade: ${id}`);
  }
  return spec;
}

export function upgradeCostFor(id: UpgradeId, owned: number): number {
  return upgradeSpec(id).cost(owned);
}
