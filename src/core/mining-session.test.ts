import { describe, expect, it, vi } from "vitest";
import {
  OFFLINE_RATE_SCALE,
  advance,
  advanceWithEvents,
  digRateFor,
  initialSnapshot,
  nextDigRateUpgradeCost,
  nextSmelterUpgradeCost,
  smelterThroughputFor,
} from "./mining-engine";
import { createMiningSession } from "./mining-session";
import { buildOfflineSummary } from "./wire-snapshot";
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

  it("counts Bag Ore in offline oreProduced across a Haul", () => {
    const before = advance(initialSnapshot(), 50_000);
    const after = advance(before, MIN_OFFLINE_MS, {
      rateScale: OFFLINE_RATE_SCALE,
    });
    const summary = buildOfflineSummary({
      before,
      after,
      offlineMs: MIN_OFFLINE_MS,
    });
    expect(summary.oreProduced).toBeCloseTo(
      after.ore -
        before.ore +
        (after.bagOre - before.bagOre) +
        (after.ingots - before.ingots),
      10,
    );
    expect(after.bagOre + after.ore).toBeGreaterThan(before.bagOre + before.ore);
  });

  it("offline catch-up over a Haul matches live advance at half rate", () => {
    const before = advance(initialSnapshot(), 95_000);
    const offline = advance(before, 28_800_000, { rateScale: 0.5 });
    const live = advance(before, 14_400_000);
    expect(offline).toEqual(live);
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
    expect(smelterThroughputFor(session.snapshot.smelterUpgradeCount)).toBe(0.08);
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
    const result = session.advanceLive(1_080_000);
    expect(result.snapshot).toBe(session.snapshot);
    expect(result.events.length).toBeGreaterThan(0);
    expect(session.snapshot.advance).toBe(1);
    session.publish();
    expect(onPublish).toHaveBeenCalledOnce();
    expect(onPublish.mock.calls[0]?.[0].advance).toBe(1);
  });

  it("advanceLive returns snapshot and events without offline boot events", () => {
    const store = memoryStore();
    const saved = advance(initialSnapshot(), 0);
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
    const afterBoot = session.snapshot;
    const { events } = session.advanceLive(0);
    expect(events).toEqual([]);
    expect(session.advanceLive(2_500).events).toEqual(
      advanceWithEvents(afterBoot, 2_500).events,
    );
  });
});
