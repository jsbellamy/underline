/** Colony Dock surface: Dig Rate, Ore, Ingots, Smelter throughput, Upgrade. */

import {
  HARDNESS,
  SMELTER_THROUGHPUT,
  YIELD,
  digRateFor,
  nextDigRateUpgradeCost,
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
  smelterDd.textContent = `${formatRate(SMELTER_THROUGHPUT)} Ore/sec`;

  status.append(
    digRateDt,
    digRateDd,
    oreDt,
    oreDd,
    ingotsDt,
    ingotsDd,
    smelterDt,
    smelterDd,
  );

  const upgradeRow = document.createElement("div");
  upgradeRow.className = "dock-colony-upgrade";
  const upgradeBtn = document.createElement("button");
  upgradeBtn.type = "button";
  upgradeBtn.className = "dock-buy-upgrade";
  upgradeBtn.dataset["buyUpgrade"] = "";
  upgradeBtn.addEventListener("click", () => {
    options.onBuyUpgrade?.("digRate");
  });
  upgradeRow.append(upgradeBtn);

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

  // Constants stay visible for the slice so Hardness / Yield are legible.
  const constants = document.createElement("p");
  constants.className = "dock-colony-constants";
  constants.textContent = `Hardness ${HARDNESS} · Yield ${YIELD}`;

  root.append(title, status, upgradeRow, offline, constants);
  host.replaceChildren(root);

  function render(snapshot: WireSnapshot): void {
    const digRate = digRateFor(snapshot.digRateUpgradeCount);
    const cost = nextDigRateUpgradeCost(snapshot.digRateUpgradeCount);
    digRateDd.textContent = `${formatRate(digRate)} Swing/sec`;
    oreDd.textContent = formatAmount(snapshot.ore);
    ingotsDd.textContent = formatAmount(snapshot.ingots);
    upgradeBtn.textContent = `Buy Upgrade (+0.25 Dig Rate) — ${cost} Ingots`;
    upgradeBtn.disabled = snapshot.ingots < cost;

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
