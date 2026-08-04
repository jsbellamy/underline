/** Colony Dock surface: Dig Rate, Ore, Ingots, Hardness, Smelter, Upgrades. */

import {
  oreForDrop,
  digRateFor,
  hardnessFor,
  carryCapacityFor,
  heapCapacityFor,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  nextCarryCapacityUpgradeCost,
  nextHaulSpeedUpgradeCost,
  smelterThroughputFor,
  HIRE_HAULER_COST,
  DROPS_PER_FACE,
  type UpgradeId,
} from "../core/mining-engine";
import type { WireSnapshot } from "../core/wire-snapshot";

export interface ColonyView {
  root: HTMLElement;
  render(snapshot: WireSnapshot): void;
  destroy(): void;
}

export interface ColonyViewOptions {
  onBuyUpgrade?: (upgrade: UpgradeId) => void;
  onDismissOffline?: () => void;
}

function formatRate(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

function formatAmount(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

export function mountColonyView(
  host: HTMLElement,
  options: ColonyViewOptions = {},
): ColonyView {
  const root = document.createElement("section");
  root.className = "dock-colony";
  root.dataset["colony"] = "";

  const title = document.createElement("h1");
  title.className = "dock-colony-title";
  title.textContent = "Colony";

  const status = document.createElement("dl");
  status.className = "dock-colony-status";

  const digRateDt = document.createElement("dt");
  digRateDt.textContent = "Dig Rate";
  const digRateDd = document.createElement("dd");
  digRateDd.dataset["digRate"] = "";

  const oreDt = document.createElement("dt");
  oreDt.textContent = "Ore";
  const oreDd = document.createElement("dd");
  oreDd.dataset["ore"] = "";

  const ingotsDt = document.createElement("dt");
  ingotsDt.textContent = "Ingots";
  const ingotsDd = document.createElement("dd");
  ingotsDd.dataset["ingots"] = "";

  const smelterDt = document.createElement("dt");
  smelterDt.textContent = "Smelter";
  const smelterDd = document.createElement("dd");
  smelterDd.dataset["smelter"] = "";

  const hardnessDt = document.createElement("dt");
  hardnessDt.textContent = "Hardness";
  const hardnessDd = document.createElement("dd");
  hardnessDd.dataset["hardness"] = "";

  const bagDt = document.createElement("dt");
  bagDt.textContent = "Bag";
  const bagDd = document.createElement("dd");
  bagDd.dataset["bag"] = "";

  const crewDt = document.createElement("dt");
  crewDt.textContent = "Crew";
  const crewDd = document.createElement("dd");
  crewDd.dataset["crew"] = "";

  const heapDt = document.createElement("dt");
  heapDt.textContent = "Heap";
  const heapDd = document.createElement("dd");
  heapDd.dataset["heap"] = "";

  const faceDt = document.createElement("dt");
  faceDt.textContent = "Face";
  const faceDd = document.createElement("dd");
  faceDd.dataset["face"] = "";

  status.append(
    digRateDt,
    digRateDd,
    oreDt,
    oreDd,
    ingotsDt,
    ingotsDd,
    smelterDt,
    smelterDd,
    hardnessDt,
    hardnessDd,
    bagDt,
    bagDd,
    crewDt,
    crewDd,
    heapDt,
    heapDd,
    faceDt,
    faceDd,
  );

  const upgradeRow = document.createElement("div");
  upgradeRow.className = "dock-colony-upgrade";
  const digRateUpgradeBtn = document.createElement("button");
  digRateUpgradeBtn.type = "button";
  digRateUpgradeBtn.className = "dock-buy-upgrade";
  digRateUpgradeBtn.dataset["buyUpgrade"] = "";
  digRateUpgradeBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("digRate");
  });
  const smelterUpgradeBtn = document.createElement("button");
  smelterUpgradeBtn.type = "button";
  smelterUpgradeBtn.className = "dock-buy-smelter-upgrade";
  smelterUpgradeBtn.dataset["buySmelterUpgrade"] = "";
  smelterUpgradeBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("smelter");
  });
  const carryCapacityUpgradeBtn = document.createElement("button");
  carryCapacityUpgradeBtn.type = "button";
  carryCapacityUpgradeBtn.className = "dock-buy-carry-capacity-upgrade";
  carryCapacityUpgradeBtn.dataset["buyCarryCapacityUpgrade"] = "";
  carryCapacityUpgradeBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("carryCapacity");
  });
  const haulSpeedUpgradeBtn = document.createElement("button");
  haulSpeedUpgradeBtn.type = "button";
  haulSpeedUpgradeBtn.className = "dock-buy-haul-speed-upgrade";
  haulSpeedUpgradeBtn.dataset["buyHaulSpeedUpgrade"] = "";
  haulSpeedUpgradeBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("haulSpeed");
  });
  const hireHaulerBtn = document.createElement("button");
  hireHaulerBtn.type = "button";
  hireHaulerBtn.className = "dock-hire-hauler";
  hireHaulerBtn.dataset["hireHauler"] = "";
  hireHaulerBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("hireHauler");
  });
  upgradeRow.append(
    digRateUpgradeBtn,
    smelterUpgradeBtn,
    carryCapacityUpgradeBtn,
    haulSpeedUpgradeBtn,
    hireHaulerBtn,
  );

  const offline = document.createElement("aside");
  offline.className = "dock-offline-summary";
  offline.hidden = true;
  offline.dataset["offlineSummary"] = "";
  const offlineBody = document.createElement("p");
  offlineBody.dataset["offlineBody"] = "";
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.textContent = "Continue";
  dismiss.dataset["dismissOffline"] = "";
  dismiss.addEventListener("click", () => {
    offline.hidden = true;
    options.onDismissOffline?.();
  });
  offline.append(offlineBody, dismiss);

  const constants = document.createElement("p");
  constants.className = "dock-colony-constants";
  constants.dataset["colonyConstants"] = "";

  root.append(title, status, upgradeRow, offline, constants);
  host.replaceChildren(root);

  function render(snapshot: WireSnapshot): void {
    const digRate = digRateFor(snapshot.digRateUpgradeCount);
    const digCost = nextDigRateUpgradeCost(snapshot.digRateUpgradeCount);
    const smelterCost = nextSmelterUpgradeCost(snapshot.smelterUpgradeCount);
    const carryCapacityCost = nextCarryCapacityUpgradeCost(
      snapshot.carryCapacityUpgradeCount,
    );
    const haulSpeedCost = nextHaulSpeedUpgradeCost(snapshot.haulSpeedUpgradeCount);
    const throughput = smelterThroughputFor(snapshot.smelterUpgradeCount);
    const capacity = carryCapacityFor(snapshot.carryCapacityUpgradeCount);
    const heapCapacity = heapCapacityFor(snapshot.carryCapacityUpgradeCount);
    const facePercent = Math.floor(
      (snapshot.faceSwingProgress / hardnessFor(snapshot.advance)) * 100,
    );
    digRateDd.textContent = `${formatRate(digRate)} Swing/sec`;
    oreDd.textContent = formatAmount(snapshot.ore);
    ingotsDd.textContent = formatAmount(snapshot.ingots);
    smelterDd.textContent = `${formatRate(throughput)} Ore/sec`;
    hardnessDd.textContent = String(Math.round(hardnessFor(snapshot.advance)));
    bagDd.textContent = `${snapshot.bagLoads} / ${capacity} loads`;
    if (snapshot.crewSize === 1) {
      crewDd.textContent = "1 Dwarf";
      heapDd.textContent = "—";
      delete heapDd.dataset["heapFull"];
    } else {
      crewDd.textContent = "2 Dwarves — Miner, Hauler";
      heapDd.textContent = `${snapshot.heapLoads} / ${heapCapacity} loads`;
      if (snapshot.heapLoads >= heapCapacity) {
        heapDd.dataset["heapFull"] = "";
      } else {
        delete heapDd.dataset["heapFull"];
      }
    }
    faceDd.textContent = `${snapshot.advance + 1} — ${facePercent}%`;
    digRateUpgradeBtn.textContent = `Buy Upgrade (+0.25 Dig Rate) — ${digCost} Ingots`;
    digRateUpgradeBtn.disabled = snapshot.ingots < digCost;
    smelterUpgradeBtn.textContent =
      `Buy Smelter Upgrade (+0.02 Ore/sec) — ${smelterCost} Ingots`;
    smelterUpgradeBtn.disabled = snapshot.ingots < smelterCost;
    carryCapacityUpgradeBtn.textContent =
      `Buy Carry Capacity Upgrade (+5 loads) — ${carryCapacityCost} Ingots`;
    carryCapacityUpgradeBtn.disabled = snapshot.ingots < carryCapacityCost;
    haulSpeedUpgradeBtn.textContent =
      `Buy Haul Speed Upgrade (+0.25 Haul Speed) — ${haulSpeedCost} Ingots`;
    haulSpeedUpgradeBtn.disabled = snapshot.ingots < haulSpeedCost;
    if (snapshot.crewSize === 1) {
      hireHaulerBtn.textContent = `Hire a Hauler — ${HIRE_HAULER_COST} Ingots`;
      hireHaulerBtn.disabled = snapshot.ingots < HIRE_HAULER_COST;
    } else {
      hireHaulerBtn.textContent = "Hauler hired";
      hireHaulerBtn.disabled = true;
    }

    constants.textContent =
      `Ore per drop ${formatAmount(oreForDrop(snapshot.advance))} — ${DROPS_PER_FACE} drops per Face`;

    if (snapshot.offlineSummary) {
      const s = snapshot.offlineSummary;
      const hours = (s.offlineMs / 3_600_000).toFixed(2);
      offlineBody.textContent =
        `While away (${hours}h): +${s.advanceGained} Advance, ` +
        `+${formatAmount(s.oreProduced)} Ore dug, ` +
        `+${formatAmount(s.oreSmelted)} Ingots smelted. ` +
        `Ore backlog ${formatAmount(s.oreBacklog)}.`;
      offline.hidden = false;
    }
  }

  return {
    root,
    render,
    destroy() {
      host.replaceChildren();
    },
  };
}
