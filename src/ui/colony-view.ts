/** Colony Dock surface: Dig Rate, Ore, Ingots, Hardness, Smelter, Upgrades. */

import {
  oreForDrop,
  digRateFor,
  hardnessFor,
  carryCapacityFor,
  heapCapacityFor,
  pickDamageFor,
  smelterThroughputFor,
  DROPS_PER_FACE,
  type UpgradeId,
} from "../core/mining-engine";
import {
  UPGRADE_CATALOGUE,
  upgradeCostFor,
  type UpgradeSpec,
} from "../data/upgrade-catalogue";
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

const DOCK_UPGRADE_PRESENTATION: Record<
  UpgradeId,
  { readonly className: string; readonly datasetKey: string }
> = {
  digRate: { className: "dock-buy-upgrade", datasetKey: "buyUpgrade" },
  pickDamage: {
    className: "dock-buy-pick-damage-upgrade",
    datasetKey: "buyPickDamageUpgrade",
  },
  smelter: { className: "dock-buy-smelter-upgrade", datasetKey: "buySmelterUpgrade" },
  carryCapacity: {
    className: "dock-buy-carry-capacity-upgrade",
    datasetKey: "buyCarryCapacityUpgrade",
  },
  haulSpeed: {
    className: "dock-buy-haul-speed-upgrade",
    datasetKey: "buyHaulSpeedUpgrade",
  },
  grabSize: { className: "dock-buy-grab-size-upgrade", datasetKey: "buyGrabSizeUpgrade" },
  unloadSpeed: {
    className: "dock-buy-unload-speed-upgrade",
    datasetKey: "buyUnloadSpeedUpgrade",
  },
  hireHauler: { className: "dock-hire-hauler", datasetKey: "hireHauler" },
};

function ownedCount(snapshot: WireSnapshot, spec: UpgradeSpec): number {
  if (spec.effect.kind === "raiseCount") {
    return snapshot[spec.effect.field];
  }
  return 0;
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

  const pickDamageDt = document.createElement("dt");
  pickDamageDt.textContent = "Pick Damage";
  const pickDamageDd = document.createElement("dd");
  pickDamageDd.dataset["pickDamage"] = "";

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
    pickDamageDt,
    pickDamageDd,
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
  const upgradeButtons = new Map<UpgradeId, HTMLButtonElement>();
  for (const spec of UPGRADE_CATALOGUE) {
    const presentation = DOCK_UPGRADE_PRESENTATION[spec.id];
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = presentation.className;
    btn.dataset[presentation.datasetKey] = "";
    btn.addEventListener("click", () => {
      options.onBuyUpgrade?.(spec.id);
    });
    upgradeButtons.set(spec.id, btn);
    upgradeRow.append(btn);
  }

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
    const throughput = smelterThroughputFor(snapshot.smelterUpgradeCount);
    const capacity = carryCapacityFor(snapshot.carryCapacityUpgradeCount);
    const heapCapacity = heapCapacityFor(snapshot.carryCapacityUpgradeCount);
    const facePercent = Math.floor(
      (snapshot.faceSwingProgress / hardnessFor(snapshot.advance)) * 100,
    );
    digRateDd.textContent = `${formatRate(digRate)} Swing/sec`;
    pickDamageDd.textContent = `${formatRate(pickDamageFor(snapshot.pickDamageUpgradeCount))} damage/Swing`;
    oreDd.textContent = formatAmount(snapshot.ore);
    ingotsDd.textContent = formatAmount(snapshot.ingots);
    smelterDd.textContent = `${formatRate(throughput)} Ore/sec`;
    hardnessDd.textContent = String(Math.round(hardnessFor(snapshot.advance)));
    if (snapshot.crewSize === 1) {
      if (!bagDt.isConnected) {
        status.insertBefore(bagDt, crewDt);
        status.insertBefore(bagDd, crewDt);
      }
      bagDd.textContent = `${snapshot.bagLoads} / ${capacity} loads`;
      crewDd.textContent = "1 Dwarf";
      heapDd.textContent = "—";
      delete heapDd.dataset["heapFull"];
    } else {
      bagDt.remove();
      bagDd.remove();
      crewDd.textContent = "2 Dwarves — Miner, Hauler";
      heapDd.textContent = `${snapshot.heapLoads} / ${heapCapacity} loads`;
      if (snapshot.heapLoads >= heapCapacity) {
        heapDd.dataset["heapFull"] = "";
      } else {
        delete heapDd.dataset["heapFull"];
      }
    }
    faceDd.textContent = `${snapshot.advance + 1} — ${facePercent}%`;
    for (const spec of UPGRADE_CATALOGUE) {
      const btn = upgradeButtons.get(spec.id);
      if (!btn) {
        continue;
      }
      const cost = upgradeCostFor(spec.id, ownedCount(snapshot, spec));
      btn.hidden = !spec.offeredAtCrewSize.includes(snapshot.crewSize);
      if (spec.id === "hireHauler" && snapshot.crewSize >= 2) {
        btn.textContent = "Hauler hired";
        btn.disabled = true;
      } else {
        btn.textContent = `${spec.label} — ${cost} Ingots`;
        btn.disabled = snapshot.ingots < cost;
      }
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
