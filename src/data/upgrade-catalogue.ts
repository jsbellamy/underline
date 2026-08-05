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
  /** Dock button text, without the trailing cost clause. */
  readonly label: string;
  /** Crew sizes at which the Dock offers this Upgrade. */
  readonly offeredAtCrewSize: readonly number[];
  /** Ingot cost of the next purchase, given the count already owned. */
  cost(owned: number): number;
}

function doublingCost(owned: number): number {
  return FIRST_UPGRADE_COST * 2 ** owned;
}

function countedUpgrade(
  id: UpgradeId,
  field: CountField,
  label: string,
  offeredAtCrewSize: readonly number[],
): UpgradeSpec {
  return {
    id,
    effect: { kind: "raiseCount", field },
    label,
    offeredAtCrewSize,
    cost: doublingCost,
  };
}

export const UPGRADE_CATALOGUE: readonly UpgradeSpec[] = [
  countedUpgrade("digRate", "digRateUpgradeCount", "Buy Upgrade (+0.25 Dig Rate)", [1, 2]),
  countedUpgrade(
    "pickDamage",
    "pickDamageUpgradeCount",
    "Buy Pick Damage Upgrade (×1.5 Pick Damage)",
    [1, 2],
  ),
  countedUpgrade(
    "smelter",
    "smelterUpgradeCount",
    "Buy Smelter Upgrade (×1.5 Ore/sec)",
    [1, 2],
  ),
  countedUpgrade(
    "carryCapacity",
    "carryCapacityUpgradeCount",
    "Buy Carry Capacity Upgrade (+5 loads)",
    [1, 2],
  ),
  countedUpgrade(
    "haulSpeed",
    "haulSpeedUpgradeCount",
    "Buy Haul Speed Upgrade (+0.25 Haul Speed)",
    [1, 2],
  ),
  countedUpgrade(
    "grabSize",
    "grabSizeUpgradeCount",
    "Buy Grab Size Upgrade (+1 Grab Size)",
    [2],
  ),
  countedUpgrade(
    "unloadSpeed",
    "unloadSpeedUpgradeCount",
    "Buy Unload Speed Upgrade (+0.5 Unload Speed)",
    [2],
  ),
  {
    id: "hireHauler",
    effect: { kind: "hireHauler" },
    label: "Hire a Hauler",
    offeredAtCrewSize: [1, 2],
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

const upgradeIds = new Set(UPGRADE_CATALOGUE.map((spec) => spec.id));

export function isUpgradeId(value: unknown): value is UpgradeId {
  return typeof value === "string" && upgradeIds.has(value as UpgradeId);
}
