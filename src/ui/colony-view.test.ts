// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { initialSnapshot } from "../core/mining-engine";
import { toWireSnapshot } from "../core/wire-snapshot";
import { mountColonyView } from "./colony-view";

describe("Colony Dock surface", () => {
  it("shows Dig Rate, Ore, Ingots, Smelter throughput, and the Upgrade offer", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        ore: 2.5,
        ingots: 12,
        digRateUpgradeCount: 1,
      }),
    );

    expect(host.querySelector("[data-dig-rate]")?.textContent).toContain("1.25");
    expect(host.querySelector("[data-ore]")?.textContent).toBe("2.50");
    expect(host.querySelector("[data-ingots]")?.textContent).toBe("12");
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("0.15");
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("Ore/sec");
    const buy = host.querySelector<HTMLButtonElement>("[data-buy-upgrade]");
    expect(buy?.textContent).toContain("10 Ingots");
    expect(buy?.disabled).toBe(false);
    view.destroy();
  });

  it("disables the Upgrade when Ingots cannot cover the cost", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 4 }));
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-upgrade]")?.disabled,
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

  it("fires onBuyUpgrade when the Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    host.querySelector<HTMLButtonElement>("[data-buy-upgrade]")?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    view.destroy();
  });
});
