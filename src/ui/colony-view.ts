/** Colony Dock surface: Dig Rate, Ore, Ingots, Hardness, Smelter, Upgrades. */

import {
  oreForDrop,
  digRateFor,
  hardnessFor,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  smelterThroughputFor,
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
  upgradeRow.append(digRateUpgradeBtn, smelterUpgradeBtn);

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
    const throughput = smelterThroughputFor(snapshot.smelterUpgradeCount);
    digRateDd.textContent = `${formatRate(digRate)} Swing/sec`;
    oreDd.textContent = formatAmount(snapshot.ore);
    ingotsDd.textContent = formatAmount(snapshot.ingots);
    smelterDd.textContent = `${formatRate(throughput)} Ore/sec`;
    hardnessDd.textContent = String(Math.round(hardnessFor(snapshot.advance)));
    digRateUpgradeBtn.textContent = `Buy Upgrade (+0.25 Dig Rate) — ${digCost} Ingots`;
    digRateUpgradeBtn.disabled = snapshot.ingots < digCost;
    smelterUpgradeBtn.textContent =
      `Buy Smelter Upgrade (+0.02 Ore/sec) — ${smelterCost} Ingots`;
    smelterUpgradeBtn.disabled = snapshot.ingots < smelterCost;

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
