import { describe, expect, it, vi } from "vitest";
import {
  OFFLINE_RATE_SCALE,
  advance,
  digRateFor,
  initialSnapshot,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  smelterThroughputFor,
} from "./mining-engine";
import { createMiningSession } from "./mining-session";
import { MIN_OFFLINE_MS } from "./offline-clock";

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
    data,
  };
}

describe("mining session", () => {
  it("boots with offline catch-up at half rate and attaches a summary when away ≥ 60s", () => {
    const store = memoryStore();
    const saved = advance(initialSnapshot(), 0);
    // Seed a save as if the player left with a fresh Colony.
    store.setItem(
      "underline-save-v1",
      JSON.stringify({
        ...saved,
        savedAtMs: 1_000,
      }),
    );
    const now = 1_000 + MIN_OFFLINE_MS;
    const session = createMiningSession({
      store,
      now: () => now,
    });
    expect(session.snapshot.advance).toBe(
      advance(saved, MIN_OFFLINE_MS, { rateScale: OFFLINE_RATE_SCALE }).advance,
    );
    const wire = session.wireSnapshot();
    expect(wire.offlineSummary?.offlineMs).toBe(MIN_OFFLINE_MS);
    expect(wire.offlineSummary?.advanceGained).toBe(wire.advance);
  });

  it("applies buyUpgrade, persists, and raises Dig Rate", () => {
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 5_000,
      snapshot: { ...initialSnapshot(), ingots: nextDigRateUpgradeCost(0) },
    });
    expect(session.tryBuyUpgrade("digRate")).toBe(true);
    expect(session.snapshot.digRateUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(digRateFor(session.snapshot.digRateUpgradeCount)).toBe(1.25);
    expect(store.data["underline-save-v1"]).toContain('"digRateUpgradeCount":1');
  });

  it("applies a Smelter buyUpgrade and raises smelterUpgradeCount", () => {
    const store = memoryStore();
    const session = createMiningSession({
      store,
      now: () => 5_000,
      snapshot: { ...initialSnapshot(), ingots: nextSmelterUpgradeCost(0) },
    });
    expect(session.tryBuyUpgrade("smelter")).toBe(true);
    expect(session.snapshot.smelterUpgradeCount).toBe(1);
    expect(session.snapshot.ingots).toBe(0);
    expect(smelterThroughputFor(session.snapshot.smelterUpgradeCount)).toBe(0.2);
    expect(store.data["underline-save-v1"]).toContain('"smelterUpgradeCount":1');
  });

  it("no-ops buyUpgrade when Ingots cannot cover the cost", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), ingots: 4 },
    });
    expect(session.tryBuyUpgrade("digRate")).toBe(false);
    expect(session.snapshot.digRateUpgradeCount).toBe(0);
    expect(session.snapshot.ingots).toBe(4);
  });

  it("advances live ticks and can publish after economy changes", () => {
    const onPublish = vi.fn();
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      onPublish,
    });
    session.advanceLive(1_000_000);
    expect(session.snapshot.advance).toBe(1);
    session.publish();
    expect(onPublish).toHaveBeenCalledOnce();
    expect(onPublish.mock.calls[0]?.[0].advance).toBe(1);
  });
});
