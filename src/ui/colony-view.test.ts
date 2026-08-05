// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import {
  carryCapacityFor,
  HIRE_HAULER_COST,
  initialSnapshot,
  nextCarryCapacityUpgradeCost,
  nextGrabSizeUpgradeCost,
  nextHaulSpeedUpgradeCost,
  nextPickDamageUpgradeCost,
  nextSmelterUpgradeCost,
  nextUnloadSpeedUpgradeCost,
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
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("0.09");
    expect(host.querySelector("[data-smelter]")?.textContent).toContain("Ore/sec");
    const digBuy = host.querySelector<HTMLButtonElement>("[data-buy-upgrade]");
    expect(digBuy?.textContent).toContain("+0.25 Dig Rate");
    expect(digBuy?.textContent).toContain("10 Ingots");
    expect(digBuy?.disabled).toBe(false);
    const smelterBuy = host.querySelector<HTMLButtonElement>(
      "[data-buy-smelter-upgrade]",
    );
    expect(smelterBuy?.textContent).toContain("×1.5 Ore/sec");
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

  it("shows Ore per drop and drops per Face from the live Advance", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        advance: 10,
      }),
    );
    expect(host.querySelector("[data-colony-constants]")?.textContent).toBe(
      "Ore per drop 4.05 — 100 drops per Face",
    );
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

  it("shows Bag loads against Carry Capacity", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot(initialSnapshot()));
    expect(host.querySelector("[data-bag]")?.textContent).toBe("0 / 10 loads");
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        bagLoads: 3,
        carryCapacityUpgradeCount: 1,
      }),
    );
    expect(host.querySelector("[data-bag]")?.textContent).toBe(
      `3 / ${carryCapacityFor(1)} loads`,
    );
    view.destroy();
  });

  it("shows Face progress as advance plus one and percent complete", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot(initialSnapshot()));
    expect(host.querySelector("[data-face]")?.textContent).toBe("1 — 0%");
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        advance: 0,
        faceSwingProgress: 430,
      }),
    );
    expect(host.querySelector("[data-face]")?.textContent).toBe("1 — 43%");
    view.destroy();
  });

  it("shows the Carry Capacity Upgrade offer and disables it when Ingots are short", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 4 }));
    const carryBuy = host.querySelector<HTMLButtonElement>(
      "[data-buy-carry-capacity-upgrade]",
    );
    expect(carryBuy?.textContent).toBe(
      `Buy Carry Capacity Upgrade (+5 loads) — ${nextCarryCapacityUpgradeCost(0)} Ingots`,
    );
    expect(carryBuy?.disabled).toBe(true);
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    expect(carryBuy?.disabled).toBe(false);
    view.destroy();
  });

  it("fires onBuyUpgrade with carryCapacity when the Carry Capacity Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    host
      .querySelector<HTMLButtonElement>("[data-buy-carry-capacity-upgrade]")
      ?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("carryCapacity");
    view.destroy();
  });
});

describe("mountColonyView", () => {
  it("shows Pick Damage between Dig Rate and Ore", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        pickDamageUpgradeCount: 2,
      }),
    );
    expect(host.querySelector("[data-pick-damage]")?.textContent).toBe(
      "2.25 damage/Swing",
    );
    const status = host.querySelector(".dock-colony-status");
    const children = Array.from(status?.children ?? []);
    const pickDamageIndex = children.findIndex(
      (el) => el.matches("dd[data-pick-damage]"),
    );
    const digRateIndex = children.findIndex((el) => el.matches("dd[data-dig-rate]"));
    const oreIndex = children.findIndex((el) => el.matches("dd[data-ore]"));
    expect(pickDamageIndex).toBeGreaterThan(digRateIndex);
    expect(pickDamageIndex).toBeLessThan(oreIndex);
    view.destroy();
  });

  it("shows the Pick Damage Upgrade offer and disables it when Ingots are short", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        pickDamageUpgradeCount: 0,
        ingots: 4,
      }),
    );
    const btn = host.querySelector<HTMLButtonElement>(
      "[data-buy-pick-damage-upgrade]",
    );
    expect(btn?.textContent).toBe(
      `Buy Pick Damage Upgrade (×1.5 Pick Damage) — ${nextPickDamageUpgradeCost(0)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        pickDamageUpgradeCount: 0,
        ingots: 5,
      }),
    );
    expect(btn?.disabled).toBe(false);
    view.destroy();
  });

  it("fires onBuyUpgrade with pickDamage when the Pick Damage Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), ingots: 5 }));
    host
      .querySelector<HTMLButtonElement>("[data-buy-pick-damage-upgrade]")
      ?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("pickDamage");
    view.destroy();
  });

  it("hides the Bag row for a two-Dwarf Crew and shows it for a solo Dwarf", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2 }));
    expect(host.querySelector("[data-bag]")).toBeNull();
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 1 }));
    expect(host.querySelector("[data-bag]")?.textContent).toBe("0 / 10 loads");
    view.destroy();
  });

  it("shows Crew as 1 Dwarf or 2 Dwarves with roles", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 1 }));
    expect(host.querySelector("[data-crew]")?.textContent).toBe("1 Dwarf");
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2 }));
    expect(host.querySelector("[data-crew]")?.textContent).toBe(
      "2 Dwarves — Miner, Hauler",
    );
    view.destroy();
  });

  it("shows Heap loads against capacity or em dash for a solo Dwarf", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 3,
        carryCapacityUpgradeCount: 0,
      }),
    );
    expect(host.querySelector("[data-heap]")?.textContent).toBe("3 / 20 loads");
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 1 }));
    expect(host.querySelector("[data-heap]")?.textContent).toBe("—");
    view.destroy();
  });

  it("marks the Heap row when capacity is full", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 20,
        carryCapacityUpgradeCount: 0,
      }),
    );
    expect(host.querySelector("[data-heap-full]")).not.toBeNull();
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 19,
        carryCapacityUpgradeCount: 0,
      }),
    );
    expect(host.querySelector("[data-heap-full]")).toBeNull();
    view.destroy();
  });

  it("shows the Haul Speed Upgrade offer and disables it when Ingots are short", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        haulSpeedUpgradeCount: 0,
        ingots: 4,
      }),
    );
    const btn = host.querySelector<HTMLButtonElement>("[data-buy-haul-speed-upgrade]");
    expect(btn?.textContent).toBe(
      `Buy Haul Speed Upgrade (+0.25 Haul Speed) — ${nextHaulSpeedUpgradeCost(0)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        haulSpeedUpgradeCount: 0,
        ingots: 5,
      }),
    );
    expect(btn?.disabled).toBe(false);
    view.destroy();
  });

  it("shows Grab Size and Unload Speed upgrades only for a two-Dwarf Crew", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 1 }));
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-grab-size-upgrade]")?.hidden,
    ).toBe(true);
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-unload-speed-upgrade]")?.hidden,
    ).toBe(true);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2 }));
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-grab-size-upgrade]")?.hidden,
    ).toBe(false);
    expect(
      host.querySelector<HTMLButtonElement>("[data-buy-unload-speed-upgrade]")?.hidden,
    ).toBe(false);
    view.destroy();
  });

  it("shows the Grab Size Upgrade offer and disables it when Ingots are short", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        grabSizeUpgradeCount: 0,
        ingots: 4,
      }),
    );
    const btn = host.querySelector<HTMLButtonElement>("[data-buy-grab-size-upgrade]");
    expect(btn?.textContent).toBe(
      `Buy Grab Size Upgrade (+1 Grab Size) — ${nextGrabSizeUpgradeCost(0)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        grabSizeUpgradeCount: 0,
        ingots: 5,
      }),
    );
    expect(btn?.disabled).toBe(false);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        grabSizeUpgradeCount: 1,
        ingots: 9,
      }),
    );
    expect(btn?.textContent).toBe(
      `Buy Grab Size Upgrade (+1 Grab Size) — ${nextGrabSizeUpgradeCost(1)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.destroy();
  });

  it("shows the Unload Speed Upgrade offer and disables it when Ingots are short", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        unloadSpeedUpgradeCount: 0,
        ingots: 4,
      }),
    );
    const btn = host.querySelector<HTMLButtonElement>(
      "[data-buy-unload-speed-upgrade]",
    );
    expect(btn?.textContent).toBe(
      `Buy Unload Speed Upgrade (+0.5 Unload Speed) — ${nextUnloadSpeedUpgradeCost(0)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        unloadSpeedUpgradeCount: 0,
        ingots: 5,
      }),
    );
    expect(btn?.disabled).toBe(false);
    view.render(
      toWireSnapshot({
        ...initialSnapshot(),
        crewSize: 2,
        unloadSpeedUpgradeCount: 1,
        ingots: 9,
      }),
    );
    expect(btn?.textContent).toBe(
      `Buy Unload Speed Upgrade (+0.5 Unload Speed) — ${nextUnloadSpeedUpgradeCost(1)} Ingots`,
    );
    expect(btn?.disabled).toBe(true);
    view.destroy();
  });

  it("shows Hire a Hauler and disables it once hired", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(
      toWireSnapshot({ ...initialSnapshot(), crewSize: 1, ingots: HIRE_HAULER_COST - 1 }),
    );
    const btn = host.querySelector<HTMLButtonElement>("[data-hire-hauler]");
    expect(btn?.textContent).toBe(`Hire a Hauler — ${HIRE_HAULER_COST} Ingots`);
    expect(btn?.disabled).toBe(true);
    view.render(
      toWireSnapshot({ ...initialSnapshot(), crewSize: 1, ingots: HIRE_HAULER_COST }),
    );
    expect(btn?.disabled).toBe(false);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2 }));
    expect(btn?.textContent).toBe("Hauler hired");
    expect(btn?.disabled).toBe(true);
    view.destroy();
  });

  it("orders upgrade buttons Dig Rate, Pick Damage, Smelter, Carry Capacity, Haul Speed, Grab Size, Unload Speed, Hire Hauler", () => {
    const host = document.createElement("div");
    const view = mountColonyView(host);
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2 }));
    const row = host.querySelector(".dock-colony-upgrade");
    const selectors = [
      "[data-buy-upgrade]",
      "[data-buy-pick-damage-upgrade]",
      "[data-buy-smelter-upgrade]",
      "[data-buy-carry-capacity-upgrade]",
      "[data-buy-haul-speed-upgrade]",
      "[data-buy-grab-size-upgrade]",
      "[data-buy-unload-speed-upgrade]",
      "[data-hire-hauler]",
    ];
    const children = Array.from(row?.children ?? []);
    expect(children.map((el) => el.matches(selectors.join(", ")))).toEqual([
      true,
      true,
      true,
      true,
      true,
      true,
      true,
      true,
    ]);
    for (let i = 0; i < selectors.length; i += 1) {
      expect(children[i]?.matches(selectors[i]!)).toBe(true);
    }
    view.destroy();
  });

  it("fires onBuyUpgrade with haulSpeed when the Haul Speed Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2, ingots: 5 }));
    host.querySelector<HTMLButtonElement>("[data-buy-haul-speed-upgrade]")?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("haulSpeed");
    view.destroy();
  });

  it("fires onBuyUpgrade with grabSize when the Grab Size Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2, ingots: 5 }));
    host.querySelector<HTMLButtonElement>("[data-buy-grab-size-upgrade]")?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("grabSize");
    view.destroy();
  });

  it("fires onBuyUpgrade with unloadSpeed when the Unload Speed Upgrade is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(toWireSnapshot({ ...initialSnapshot(), crewSize: 2, ingots: 5 }));
    host
      .querySelector<HTMLButtonElement>("[data-buy-unload-speed-upgrade]")
      ?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("unloadSpeed");
    view.destroy();
  });

  it("fires onBuyUpgrade with hireHauler when Hire a Hauler is pressed", () => {
    const onBuy = vi.fn();
    const host = document.createElement("div");
    const view = mountColonyView(host, { onBuyUpgrade: onBuy });
    view.render(
      toWireSnapshot({ ...initialSnapshot(), ingots: HIRE_HAULER_COST }),
    );
    host.querySelector<HTMLButtonElement>("[data-hire-hauler]")?.click();
    expect(onBuy).toHaveBeenCalledOnce();
    expect(onBuy).toHaveBeenCalledWith("hireHauler");
    view.destroy();
  });
});
