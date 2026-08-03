// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import {
  initialSnapshot,
  nextSmelterUpgradeCost,
} from "../core/mining-engine";
import { toWireSnapshot } from "../core/wire-snapshot";
import { mountColonyView } from "./colony-view";

describe("Colony Dock surface", () => {
  it("shows Dig Rate, Ore, Ingots, Hardness, live Smelter, and both Upgrade offers", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        advance: 0,
        ore: 2.5,
        ingots: 12,
        digRateUpgradeCount: 1,
        smelterUpgradeCount: 1,
      }),
    );

    expect(host.querySelector("[data-dig-rate]")?.textContent).toContain("1.25");
    expect(host.querySelector("[data-ore]")?.textContent).toBe("2.50");
    expect(host.querySelector("[data-ingots]")?.textContent).toBe("12");
    expect(host.querySelector("[data-hardness]")?.textContent).toBe("1000");
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("0.20");
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("Ore/sec");
    const digBuy = host.querySelector<HTMLButtonElement>("[data-buy-upgrade]");
    expect(digBuy?.textContent).toContain("+0.25 Dig Rate");
    expect(digBuy?.textContent).toContain("10 Ingots");
    expect(digBuy?.disabled).toBe(false);
    const smelterBuy = host.querySelector<HTMLButtonElement>(
      "[data-buy-smelter-upgrade]",
    );
    expect(smelterBuy?.textContent).toContain("+0.05 Ore/sec");
    expect(smelterBuy?.textContent).toContain(
      `${nextSmelterUpgradeCost(1)} Ingots`,
    );
    expect(smelterBuy?.disabled).toBe(false);
    view.destroy();
  });

  it("rounds Hardness for the Dock readout at Advance 10", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        advance: 10,
      }),
    );
    expect(host.querySelector("[data-hardness]")?.textContent).toBe("4046");
    view.destroy();
  });

  it("disables each Upgrade when Ingots cannot cover its cost", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 4 }));
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-upgrade]")?.disabled,
    ).toBe(true);
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-smelter-upgrade]")
        ?.disabled,
    ).toBe(true);
    view.destroy();
  });

  it("shows offlineSummary and dismisses it locally", () => {
    const onDismiss = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onDismissOffline: onDismiss });
    view.render(
      toWireSnapshot(initialSnapshot(), {
        offlineMs: 120_000,
        advanceGained: 2,
        oreProduced: 2,
        oreSmelted: 1,
        oreBacklog: 0.5,
      }),
    );
    const panel = host.querySelector<HTMLElement>("[data-offline-summary]");
    expect(panel?.hidden).toBe(false);
    expect(panel?.textContent).toContain("Advance");
    host.querySelector<HTMLButtonElement>("[data-dismiss-offline]")?.click();
    expect(panel?.hidden).toBe(true);
    expect(onDismiss).toHaveBeenCalledOnce();
    view.destroy();
  });

  it("fires onBuyUpgrade with digRate when the Dig Rate Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    host.querySelector<HTMLButtonElement>("[data-buy-upgrade]")?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("digRate");
    view.destroy();
  });

  it("fires onBuyUpgrade with smelter when the Smelter Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    host
      .querySelector<HTMLButtonElement>("[data-buy-smelter-upgrade]")
      ?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("smelter");
    view.destroy();
  });
});
