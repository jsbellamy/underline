// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot, nextDigRateUpgradeCost } from "../core/mining-engine";
import { createBusEndpoint } from "./bus";
import { mountDockShell } from "./dock-root";
import { mountPaneShell } from "./pane-root";

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

    expect(session.snapshot.digRateUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(dockRoot.querySelector("[data-dig-rate]")?.textContent).toContain(
      "1.25",
    );

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
      command: { schemaVersion: 99, name: "buyUpgrade" } as never,
    });
    await flushBus();
    expect(session.snapshot.digRateUpgradeCount).toBe(0);

    rogue.close();
    pane.destroy();
  });
});
