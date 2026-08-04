// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { createMiningSession } from "../core/mining-session";
import {
  initialSnapshot,
  HIRE_HAULER_COST,
  nextCarryCapacityUpgradeCost,
  nextDigRateUpgradeCost,
  nextHaulSpeedUpgradeCost,
  nextSmelterUpgradeCost,
} from "../core/mining-engine";
import { createBusEndpoint, type BusMessage } from "./bus";
import { mountDockShell } from "./dock-root";
import { createMinePresenter } from "./mine-presenter";
import { mountPaneShell } from "./pane-root";
import { PUMP_INTERVAL_MS } from "./pump";

function memoryStore(initial: Record<string, string> = {}) {
  const data = { ...initial };
  return {
    getItem(key: string) {
      return data[key] ?? null;
    },
    setItem(key: string, value: string) {
      data[key] = value;
    },
    removeItem(key: string) {
      delete data[key];
    },
  };
}

async function flushBus(): Promise<void> {
  for (let i = 0; i < 3; i += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  }
}

describe("Pane↔Dock close-the-loop bus", () => {
  it("lets the Dock buy an Upgrade and see Dig Rate rise on the next Snapshot", async () => {
    const channel = `underline-loop-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: nextDigRateUpgradeCost(0),
      },
    });

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");
    const commands: BusMessage[] = [];
    const commandSpy = createBusEndpoint(
      {
        command(message) {
          commands.push(message);
        },
      },
      channel,
    );

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    expect(dockRoot.querySelector("[data-ingots]")?.textContent).toBe("5");

    dockRoot.querySelector<HTMLButtonElement>("[data-buy-upgrade]")?.click();
    await flushBus();

    expect(commands).toContainEqual({
      type: "command",
      command: { schemaVersion: 4, name: "buyUpgrade", upgrade: "digRate" },
    });
    expect(session.snapshot.digRateUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(dockRoot.querySelector("[data-dig-rate]")?.textContent).toContain(
      "1.25",
    );

    pane.destroy();
    dock.destroy();
    commandSpy.close();
  });

  it("lets the Dock buy a Smelter Upgrade and reflects live throughput and Hardness", async () => {
    const channel = `underline-smelter-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        advance: 30,
        ingots: nextSmelterUpgradeCost(0),
      },
    });

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");
    const commands: BusMessage[] = [];
    const commandSpy = createBusEndpoint(
      {
        command(message) {
          commands.push(message);
        },
      },
      channel,
    );

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    // Advance 30 → Math.round(1000 × 1.15^30) = 66212
    expect(dockRoot.querySelector("[data-hardness]")?.textContent).toBe("66212");
    expect(dockRoot.querySelector("[data-smelter]")?.textContent).toContain(
      "0.06",
    );

    dockRoot
      .querySelector<HTMLButtonElement>("[data-buy-smelter-upgrade]")
      ?.click();
    await flushBus();

    expect(commands).toContainEqual({
      type: "command",
      command: { schemaVersion: 4, name: "buyUpgrade", upgrade: "smelter" },
    });
    expect(session.snapshot.smelterUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(dockRoot.querySelector("[data-smelter]")?.textContent).toContain(
      "0.08",
    );

    pane.destroy();
    dock.destroy();
    commandSpy.close();
  });

  it("lets the Dock buy a Carry Capacity Upgrade and reflects higher Bag capacity", async () => {
    const channel = `underline-carry-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: nextCarryCapacityUpgradeCost(0),
      },
    });

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");
    const commands: BusMessage[] = [];
    const commandSpy = createBusEndpoint(
      {
        command(message) {
          commands.push(message);
        },
      },
      channel,
    );

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    expect(dockRoot.querySelector("[data-bag]")?.textContent).toBe("0 / 10 loads");

    dockRoot
      .querySelector<HTMLButtonElement>("[data-buy-carry-capacity-upgrade]")
      ?.click();
    await flushBus();

    expect(commands).toContainEqual({
      type: "command",
      command: { schemaVersion: 4, name: "buyUpgrade", upgrade: "carryCapacity" },
    });
    expect(session.snapshot.carryCapacityUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(dockRoot.querySelector("[data-bag]")?.textContent).toBe("0 / 15 loads");

    pane.destroy();
    dock.destroy();
    commandSpy.close();
  });

  it("republishes when Bag loads change so the Dock tracks live play", async () => {
    const channel = `underline-bag-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 0,
      snapshot: initialSnapshot(),
    });

    let clock = 0;
    const rafCallbacks: FrameRequestCallback[] = [];
    const intervalCallbacks: Array<() => void> = [];
    let intervalId = 0;
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
      pumpSchedule: {
        now: () => clock,
        requestAnimationFrame: (callback: FrameRequestCallback) => {
          rafCallbacks.push(callback);
          return rafCallbacks.length;
        },
        cancelAnimationFrame: vi.fn(),
        setInterval: ((callback: TimerHandler) => {
          const fn = typeof callback === "function" ? callback : () => {};
          intervalCallbacks.push(fn as () => void);
          intervalId += 1;
          return intervalId;
        }) as typeof setInterval,
        clearInterval: vi.fn(),
        document: doc,
      },
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    expect(dockRoot.querySelector("[data-bag]")?.textContent).toBe("0 / 10 loads");
    expect(dockRoot.querySelector("[data-ore]")?.textContent).toBe("0");

    pane.startPump();
    for (let tick = 1; tick <= 40; tick += 1) {
      clock = tick * PUMP_INTERVAL_MS;
      for (const callback of [...intervalCallbacks]) {
        callback();
      }
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(clock);
      }
    }
    await flushBus();

    expect(session.snapshot.bagLoads).toBeGreaterThan(0);
    expect(session.snapshot.ore).toBe(0);
    expect(dockRoot.querySelector("[data-bag]")?.textContent).toBe("1 / 10 loads");

    pane.destroy();
    dock.destroy();
  });

  it("republishes when Heap loads change so the Dock tracks live haul play", async () => {
    const channel = `underline-heap-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
      },
    });

    let clock = 0;
    const rafCallbacks: FrameRequestCallback[] = [];
    const intervalCallbacks: Array<() => void> = [];
    let intervalId = 0;
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
      pumpSchedule: {
        now: () => clock,
        requestAnimationFrame: (callback: FrameRequestCallback) => {
          rafCallbacks.push(callback);
          return rafCallbacks.length;
        },
        cancelAnimationFrame: vi.fn(),
        setInterval: ((callback: TimerHandler) => {
          const fn = typeof callback === "function" ? callback : () => {};
          intervalCallbacks.push(fn as () => void);
          intervalId += 1;
          return intervalId;
        }) as typeof setInterval,
        clearInterval: vi.fn(),
        document: doc,
      },
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    expect(dockRoot.querySelector("[data-heap]")?.textContent).toBe("0 / 10 loads");

    pane.startPump();
    for (let tick = 1; tick <= 40; tick += 1) {
      clock = tick * PUMP_INTERVAL_MS;
      for (const callback of [...intervalCallbacks]) {
        callback();
      }
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(clock);
      }
    }
    await flushBus();

    expect(session.snapshot.heapLoads).toBeGreaterThan(0);
    expect(dockRoot.querySelector("[data-heap]")?.textContent).toBe("1 / 10 loads");

    pane.destroy();
    dock.destroy();
  });

  it("lets the Dock buy a Haul Speed Upgrade without resyncing Dig Rate", async () => {
    const channel = `underline-haul-speed-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: nextHaulSpeedUpgradeCost(0),
      },
    });
    const syncDigRate = vi.fn();
    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");
    const commands: BusMessage[] = [];

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      presenter: {
        ...createMinePresenter(session),
        syncDigRate,
      },
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => {
        const endpoint = createBusEndpoint(
          {
            ...handlers,
            command(message) {
              commands.push(message);
              handlers.command?.(message);
            },
          },
          channel,
        );
        return endpoint;
      },
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    dockRoot
      .querySelector<HTMLButtonElement>("[data-buy-haul-speed-upgrade]")
      ?.click();
    await flushBus();

    expect(commands).toContainEqual({
      type: "command",
      command: { schemaVersion: 4, name: "buyUpgrade", upgrade: "haulSpeed" },
    });
    expect(session.snapshot.haulSpeedUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(syncDigRate).not.toHaveBeenCalled();

    pane.destroy();
    dock.destroy();
  });

  it("republishes after a failed Haul Speed Upgrade so disabled state stays in sync", async () => {
    const channel = `underline-haul-speed-fail-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: nextHaulSpeedUpgradeCost(0) - 1,
      },
    });

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    const btn = dockRoot.querySelector<HTMLButtonElement>(
      "[data-buy-haul-speed-upgrade]",
    );
    expect(btn?.disabled).toBe(true);
    btn?.click();
    await flushBus();

    expect(session.snapshot.haulSpeedUpgradeCount).toBe(0);
    expect(session.snapshot.ingots).toBe(nextHaulSpeedUpgradeCost(0) - 1);
    expect(btn?.disabled).toBe(true);

    pane.destroy();
    dock.destroy();
  });

  it("lets the Dock hire a Hauler without resyncing Dig Rate", async () => {
    const channel = `underline-hire-hauler-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: HIRE_HAULER_COST,
      },
    });
    const syncDigRate = vi.fn();
    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");
    const commands: BusMessage[] = [];

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      presenter: {
        ...createMinePresenter(session),
        syncDigRate,
      },
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => {
        const endpoint = createBusEndpoint(
          {
            ...handlers,
            command(message) {
              commands.push(message);
              handlers.command?.(message);
            },
          },
          channel,
        );
        return endpoint;
      },
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    dockRoot.querySelector<HTMLButtonElement>("[data-hire-hauler]")?.click();
    await flushBus();

    expect(commands).toContainEqual({
      type: "command",
      command: { schemaVersion: 4, name: "buyUpgrade", upgrade: "hireHauler" },
    });
    expect(session.snapshot.crewSize).toBe(2);
    expect(session.snapshot.ingots).toBe(0);
    expect(dockRoot.querySelector("[data-crew]")?.textContent).toBe(
      "2 Dwarves — Miner, Hauler",
    );
    expect(syncDigRate).not.toHaveBeenCalled();

    pane.destroy();
    dock.destroy();
  });

  it("republishes after a failed Hire Hauler so disabled state stays in sync", async () => {
    const channel = `underline-hire-hauler-fail-${crypto.randomUUID()}`;
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: {
        ...initialSnapshot(),
        ingots: HIRE_HAULER_COST - 1,
      },
    });

    const paneRoot = document.createElement("main");
    const dockRoot = document.createElement("main");

    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const dock = mountDockShell(dockRoot, {
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    await flushBus();
    const btn = dockRoot.querySelector<HTMLButtonElement>("[data-hire-hauler]");
    expect(btn?.disabled).toBe(true);
    btn?.click();
    await flushBus();

    expect(session.snapshot.crewSize).toBe(1);
    expect(session.snapshot.ingots).toBe(HIRE_HAULER_COST - 1);
    expect(btn?.disabled).toBe(true);

    pane.destroy();
    dock.destroy();
  });

  it("ignores mismatched command schemaVersion", async () => {
    const channel = `underline-ignore-${crypto.randomUUID()}`;
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), ingots: 5 },
    });
    const paneRoot = document.createElement("main");
    const pane = mountPaneShell(paneRoot, {
      session,
      deferPump: true,
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: (handlers) => createBusEndpoint(handlers, channel),
    });

    const rogue = createBusEndpoint({}, channel);
    rogue.publish({
      type: "command",
      command: { schemaVersion: 99, name: "buyUpgrade", upgrade: "digRate" } as never,
    });
    await flushBus();
    expect(session.snapshot.digRateUpgradeCount).toBe(0);

    rogue.close();
    pane.destroy();
  });
});
