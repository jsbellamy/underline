import { describe, expect, it, vi } from "vitest";
import { createMiningSession } from "../core/mining-session";
import {
  advance as advanceEngine,
  advanceWithEvents,
  carryCapacityFor,
  HAUL_ROUND_TRIP_MS,
  heapCapacityFor,
  initialSnapshot,
  pickupMsPerLoad,
} from "../core/mining-engine";
import {
  persistSettings,
} from "../core/settings-save";
import type { MiningEvent } from "../core/mining-events";
import { createMinePresenter, FACE_SLIDE_MS } from "./mine-presenter";
import type { MiningAudio } from "./mining-audio";
import { ORE_FALL_MS } from "./pane-layout";
import { PUMP_INTERVAL_MS } from "./pump";

function memoryStore() {
  const data: Record<string, string> = {};
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

function spyMiningAudio(): MiningAudio & {
  queuedBatches: {
    events: readonly MiningEvent[];
    baseMs: number;
    dtMs: number;
  }[];
  releasedAt: number[];
} {
  const queuedBatches: {
    events: readonly MiningEvent[];
    baseMs: number;
    dtMs: number;
  }[] = [];
  const releasedAt: number[] = [];
  return {
    queuedBatches,
    releasedAt,
    handleEvents(events, baseMs, dtMs) {
      queuedBatches.push({ events, baseMs, dtMs });
    },
    releaseDueTo(nowMs) {
      releasedAt.push(nowMs);
    },
    setEnabled() {},
    isEnabled() {
      return true;
    },
    destroy() {},
  };
}

function swingCueTimes(audio: ReturnType<typeof spyMiningAudio>): number[] {
  const times: number[] = [];
  for (const batch of audio.queuedBatches) {
    for (const event of batch.events) {
      if (event.type === "swing") {
        times.push(batch.baseMs + event.atMs);
      }
    }
  }
  return times;
}

describe("mine presenter", () => {
  it("starts simNowMs at 0 and sums advanceMs deltas", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    expect(presenter.simNowMs).toBe(0);
    presenter.start();
    presenter.advanceMs(250);
    expect(presenter.simNowMs).toBe(250);
    presenter.advanceMs(100);
    expect(presenter.simNowMs).toBe(350);
    presenter.advanceMs(50);
    expect(presenter.simNowMs).toBe(400);
  });

  it("defaults snapshot to simNowMs when nowMs is omitted", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(250);
    expect(presenter.snapshot()).toEqual(presenter.snapshot(presenter.simNowMs));
  });

  it("backward-interpolated snapshot before the first swing completes stays near fraction 0, not near 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(100);
    const snap = presenter.snapshot(presenter.simNowMs - PUMP_INTERVAL_MS);
    expect(snap.swingFraction).toBeGreaterThanOrEqual(0);
    expect(snap.swingFraction).toBeLessThan(1);
    expect(snap.swingFraction).toBeLessThan(0.5);
  });

  it("does not change frameIndex on tick when presentation clock is held", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    const at500 = presenter.snapshot(500);
    presenter.advanceMs(250);
    const stillAt500 = presenter.snapshot(500);
    expect(stillAt500.frameIndex).toBe(at500.frameIndex);
  });

  it("draws every swing frame index across a cycle at Dig Rate 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();

    const seen = new Set<number>();
    const order: number[] = [];
    for (let t = 0; t <= 1000; t += 16) {
      const frame = presenter.snapshot(t).frameIndex;
      if (!seen.has(frame)) {
        seen.add(frame);
        order.push(frame);
      }
    }
    expect(seen.size).toBe(9);
    expect([...seen].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
    expect(order).toEqual([5, 6, 7, 8, 0, 1, 2, 3, 4]);
  });

  it("draws every swing frame index across a cycle at Dig Rate 2", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), digRateUpgradeCount: 4 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.syncDigRate();

    const seen = new Set<number>();
    for (let t = 0; t <= 500; t += 16) {
      seen.add(presenter.snapshot(t).frameIndex);
    }
    expect(seen.size).toBe(9);
    expect([...seen].sort((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("keeps impact frame cadence when Pick Damage exceeds 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), pickDamageUpgradeCount: 1 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(1000);

    const sessionBase = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenterBase = createMinePresenter(sessionBase);
    presenterBase.start();
    presenterBase.advanceMs(1000);

    const upgradedAtBoundary = presenter.snapshot(presenter.simNowMs);
    const baseAtBoundary = presenterBase.snapshot(presenterBase.simNowMs);

    expect(upgradedAtBoundary.swingFraction).toBeCloseTo(0, 5);
    expect(upgradedAtBoundary.frameIndex).toBe(baseAtBoundary.frameIndex);
    expect(upgradedAtBoundary.swingFraction).toBeCloseTo(
      baseAtBoundary.swingFraction,
      5,
    );
  });

  it("freezes swing fraction during a Haul", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(100_000);
    const atHaulStart = presenter.snapshot(presenter.simNowMs);
    const midHaul = presenter.snapshot(presenter.simNowMs + 200);
    presenter.advanceMs(4_000);
    const laterHaul = presenter.snapshot(presenter.simNowMs + 500);
    expect(midHaul.swingFraction).toBe(atHaulStart.swingFraction);
    expect(laterHaul.swingFraction).toBe(atHaulStart.swingFraction);
  });

  it("syncDigRate mirrors digRateUpgradeCount into the anim Dig Rate", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), ingots: 5 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.anim.digRate).toBe(1);
    expect(session.tryBuyUpgrade("digRate")).toBe(true);
    presenter.syncDigRate();
    expect(presenter.anim.digRate).toBe(1.25);
    expect(presenter.snapshot().digRate).toBe(1.25);
  });

  it("grows Advance on the Tunnel snapshot as Faces break", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    // Live pump steps are 250ms; 4320 ticks = 1_080_000ms breaks the opening Face.
    for (let i = 0; i < 4320; i += 1) {
      presenter.advanceMs(250);
    }
    expect(presenter.snapshot().advance).toBe(1);
    expect(presenter.snapshot().animation).toBe("swing");
  });

  it("queues swing cues at exact sim times on tick without releasing audio", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    for (let i = 0; i < 12; i += 1) {
      presenter.advanceMs(250);
    }

    expect(swingCueTimes(audio)).toEqual([1000, 2000, 3000]);
    expect(audio.releasedAt).toEqual([]);
  });

  it("is chunk-neutral for queued swing cue times", () => {
    const sessionA = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audioA = spyMiningAudio();
    const presenterA = createMinePresenter(sessionA, { audio: audioA });
    presenterA.start();
    for (let i = 0; i < 100; i += 1) {
      presenterA.advanceMs(10);
    }

    const sessionB = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audioB = spyMiningAudio();
    const presenterB = createMinePresenter(sessionB, { audio: audioB });
    presenterB.start();
    presenterB.advanceMs(1000);

    expect(swingCueTimes(audioA)[0]).toBeCloseTo(1000, 5);
    expect(swingCueTimes(audioB)[0]).toBeCloseTo(1000, 5);
  });

  it("queues a faceBroken cue from engine events instead of advance delta", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    const dtMs = 1_080_000;
    const { events: expectedEvents } = advanceWithEvents(initialSnapshot(), dtMs);
    const expectedBreakAtMs = expectedEvents.find(
      (e) => e.type === "faceBroken",
    )!.atMs;

    presenter.advanceMs(dtMs);

    const breakCues = audio.queuedBatches.flatMap((b) =>
      b.events
        .filter((e) => e.type === "faceBroken")
        .map((e) => b.baseMs + e.atMs),
    );
    expect(breakCues).toEqual([expectedBreakAtMs]);
    expect(audio.releasedAt).toEqual([]);
  });

  it("queues cues with the advance window length on each tick", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    presenter.advanceMs(250);
    expect(audio.queuedBatches[0]?.dtMs).toBe(250);

    presenter.advanceMs(100);
    expect(audio.queuedBatches[1]?.dtMs).toBe(100);
  });

  it("releases queued audio when the caller supplies a presentation time", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.releaseAudioDueTo(1500);
    expect(audio.releasedAt).toEqual([1500]);
  });

  it("constructs audio enabled from persisted settings", () => {
    const store = memoryStore();
    persistSettings({ schemaVersion: 1, soundEnabled: true }, store);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      })),
    );
    const createAudioContext = vi.fn(
      () =>
        ({
          decodeAudioData: vi.fn(async () => ({} as AudioBuffer)),
          createBufferSource: vi.fn(() => ({
            connect: vi.fn(),
            start: vi.fn(),
          })),
          destination: {},
          close: vi.fn(),
        }) as unknown as AudioContext,
    );
    const session = createMiningSession({ store, now: () => 0 });
    createMinePresenter(session, { store, createAudioContext });
    expect(createAudioContext).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("defaults audio off when settings are absent", () => {
    const store = memoryStore();
    const createAudioContext = vi.fn();
    const session = createMiningSession({ store, now: () => 0 });
    createMinePresenter(session, { store, createAudioContext });
    expect(createAudioContext).not.toHaveBeenCalled();
  });

  it("delegates setSoundEnabled to mining audio", () => {
    const store = memoryStore();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        arrayBuffer: async () => new ArrayBuffer(8),
      })),
    );
    const createAudioContext = vi.fn(
      () =>
        ({
          decodeAudioData: vi.fn(async () => ({} as AudioBuffer)),
          createBufferSource: vi.fn(() => ({
            connect: vi.fn(),
            start: vi.fn(),
          })),
          destination: {},
          close: vi.fn(),
        }) as unknown as AudioContext,
    );
    const session = createMiningSession({ store, now: () => 0 });
    const presenter = createMinePresenter(session, { store, createAudioContext });
    presenter.setSoundEnabled(true);
    expect(createAudioContext).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("advances normally without injectable audio", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(250);
    expect(presenter.snapshot().faceSwingProgress).toBeGreaterThanOrEqual(0);
  });

  it("derives haul phase and progress from haulRemainingMs", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();

    presenter.advanceMs(100_000);
    const atHaulStart = presenter.snapshot();
    expect(atHaulStart.haulPhase).toBe("out");
    expect(atHaulStart.haulProgress).toBe(0);
    expect(atHaulStart.animation).toBe("walk");
    expect(atHaulStart.facing).toBe("west");

    presenter.advanceMs(4_000);
    const atMidpoint = presenter.snapshot();
    expect(atMidpoint.haulProgress).toBeCloseTo(0.5, 5);

    presenter.advanceMs(3_000);
    const onReturnLeg = presenter.snapshot();
    expect(onReturnLeg.haulPhase).toBe("back");
    expect(onReturnLeg.haulProgress).toBeCloseTo(0.875, 5);
    expect(onReturnLeg.facing).toBe("east");
  });

  it("exposes haulPhase none and zero progress when not hauling", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(1000);
    const snap = presenter.snapshot();
    expect(snap.haulPhase).toBe("none");
    expect(snap.haulProgress).toBe(0);
  });

  it("queues no swing cues during a Haul and keeps exact spacing before and after", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    const haulStartMs = 100_000;
    const haulEndMs = 108_000;

    presenter.advanceMs(99_000);
    const beforeHaul = swingCueTimes(audio).filter((t) => t <= 99_000);
    expect(beforeHaul[beforeHaul.length - 1]).toBeCloseTo(99_000, 5);
    expect(
      beforeHaul.every((t, i) => i === 0 || t - beforeHaul[i - 1]! === 1000),
    ).toBe(true);

    presenter.advanceMs(HAUL_ROUND_TRIP_MS + 3_000);
    const allSwings = swingCueTimes(audio);
    const duringHaul = allSwings.filter(
      (t) => t > haulStartMs && t < haulEndMs,
    );
    expect(duringHaul).toEqual([]);

    const afterHaul = allSwings.filter((t) => t >= haulEndMs);
    expect(afterHaul.length).toBeGreaterThanOrEqual(2);
    expect(
      afterHaul.every((t, i) => i === 0 || t - afterHaul[i - 1]! === 1000),
    ).toBe(true);
  });

  it("stays in swing after a Face break without walking", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        advance: 0,
        faceSwingProgress: 999,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(10);
    expect(presenter.snapshot().animation).toBe("swing");
  });

  it("resets faceSlide to 0 when Advance increases and drives it to 1 over FACE_SLIDE_MS", () => {
    const almostBroken = advanceEngine(initialSnapshot(), 1_071_999);
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: almostBroken,
    });
    const presenter = createMinePresenter(session);
    presenter.start();

    expect(presenter.snapshot().faceSlide).toBe(1);
    expect(presenter.snapshot().advance).toBe(0);

    presenter.advanceMs(1);
    expect(presenter.snapshot().advance).toBe(1);
    expect(presenter.snapshot().faceSlide).toBeCloseTo(1 / FACE_SLIDE_MS, 5);

    presenter.advanceMs(200);
    expect(presenter.snapshot().faceSlide).toBeCloseTo(201 / FACE_SLIDE_MS, 5);

    presenter.advanceMs(200);
    expect(presenter.snapshot().faceSlide).toBe(1);
  });

  it("omits hauler and adds crewSize and heapLoads for a one-Dwarf Crew", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(1000);
    const snap = presenter.snapshot();
    expect(snap.crewSize).toBe(1);
    expect(snap.heapLoads).toBe(0);
    expect(snap.hauler).toBeUndefined();
  });

  it("with crewSize 2 the Miner never walks and always faces east across a Haul", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        haulRemainingMs: HAUL_ROUND_TRIP_MS,
        bagLoads: heapCapacityFor(0),
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    for (let t = 0; t <= HAUL_ROUND_TRIP_MS; t += 250) {
      presenter.advanceMs(250);
      const snap = presenter.snapshot();
      expect(snap.animation).not.toBe("walk");
      expect(snap.facing).toBe("east");
    }
  });

  it("with crewSize 2 idles the Miner on a full Heap and resumes swing when a Load drains", () => {
    const cap = heapCapacityFor(0);
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: cap,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.snapshot().animation).toBe("idle");
    presenter.advanceMs(pickupMsPerLoad(0));
    expect(presenter.snapshot().animation).toBe("swing");
  });

  it("with crewSize 2 drives Hauler walk clip during pickup shuttle legs", () => {
    const outbound = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 3,
        pickupProgressMs: 2_500,
        haulSpeedUpgradeCount: 0,
      },
    });
    const outboundPresenter = createMinePresenter(outbound);
    outboundPresenter.start();
    const eastLeg = outboundPresenter.snapshot();
    expect(eastLeg.hauler!.phase).toBe("pickup");
    expect(eastLeg.hauler!.animation).toBe("walk");
    expect(eastLeg.hauler!.facing).toBe("east");
    expect(eastLeg.hauler!.pickupProgress).toBeCloseTo(0.25, 5);

    const returnLeg = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 3,
        pickupProgressMs: 7_500,
        haulSpeedUpgradeCount: 0,
      },
    });
    const returnPresenter = createMinePresenter(returnLeg);
    returnPresenter.start();
    const westLeg = returnPresenter.snapshot();
    expect(westLeg.hauler!.phase).toBe("pickup");
    expect(westLeg.hauler!.animation).toBe("walk");
    expect(westLeg.hauler!.facing).toBe("west");
    expect(westLeg.hauler!.pickupProgress).toBeCloseTo(0.75, 5);

    const emptyHeap = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 0,
        pickupProgressMs: 0,
      },
    });
    const emptyPresenter = createMinePresenter(emptyHeap);
    emptyPresenter.start();
    const idle = emptyPresenter.snapshot();
    expect(idle.hauler!.phase).toBe("pickup");
    expect(idle.hauler!.animation).toBe("idle");
    expect(idle.hauler!.facing).toBe("east");
  });

  it("with crewSize 2 exposes hauler clip state on the hauler sub-object", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 1,
        pickupProgressMs: 2_500,
        haulSpeedUpgradeCount: 0,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    const picking = presenter.snapshot();
    expect(picking.hauler).toBeDefined();
    expect(picking.hauler!.phase).toBe("pickup");
    expect(picking.hauler!.animation).toBe("walk");
    expect(picking.hauler!.facing).toBe("east");
    expect(picking.hauler!.pickupProgress).toBeCloseTo(0.25, 5);

    const hauling = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        haulRemainingMs: HAUL_ROUND_TRIP_MS,
        bagLoads: heapCapacityFor(0),
      },
    });
    const haulPresenter = createMinePresenter(hauling);
    haulPresenter.start();
    const outLeg = haulPresenter.snapshot();
    expect(outLeg.hauler!.phase).toBe("out");
    expect(outLeg.hauler!.animation).toBe("walk");
    expect(outLeg.hauler!.facing).toBe("west");
    expect(outLeg.hauler!.pickupProgress).toBe(0);

    haulPresenter.advanceMs(HAUL_ROUND_TRIP_MS / 2 + 1);
    const backLeg = haulPresenter.snapshot();
    expect(backLeg.hauler!.phase).toBe("back");
    expect(backLeg.hauler!.animation).toBe("walk");
    expect(backLeg.hauler!.facing).toBe("east");
    expect(backLeg.hauler!.haulProgress).toBeGreaterThan(0);
  });

  it("seeds a fallingOre entry from loadDropped whose progress tracks nowMs", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(10_000);
    expect(presenter.snapshot().heapLoads).toBe(1);
    expect(presenter.snapshot(10_000).fallingOre).toEqual([
      { destination: "heap", slot: 0, progress: 0 },
    ]);
    expect(presenter.snapshot(10_125).fallingOre).toEqual([
      { destination: "heap", slot: 0, progress: 0.5 },
    ]);
    expect(presenter.snapshot(10_000 + ORE_FALL_MS).fallingOre).toEqual([]);
  });

  it("seeds a bag-bound fallingOre entry for a one-Dwarf Crew", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(10_000);
    expect(session.snapshot.bagLoads).toBe(1);
    expect(presenter.snapshot(10_000).fallingOre).toEqual([
      { destination: "bag", slot: 0, progress: 0 },
    ]);
    expect(presenter.snapshot(10_125).fallingOre).toEqual([
      { destination: "bag", slot: 0, progress: 0.5 },
    ]);
    expect(presenter.snapshot(10_000 + ORE_FALL_MS).fallingOre).toEqual([]);
  });

  it("keeps heapLoads at zero while a one-Dwarf fall is in flight", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(10_000);
    const engineBefore = { ...session.snapshot };
    const midFall = presenter.snapshot(10_125);
    expect(midFall.heapLoads).toBe(0);
    expect(midFall.fallingOre).toEqual([
      { destination: "bag", slot: 0, progress: 0.5 },
    ]);
    expect(session.snapshot).toEqual(engineBefore);
  });

  it("reports no fallingOre after offline catch-up with a saved Bag", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        bagLoads: 5,
        bagOre: 5,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.snapshot().fallingOre).toEqual([]);
  });

  it("truncates newest falls when heapLoads drops below the active list", () => {
    const cap = carryCapacityFor(0);
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        bagLoads: cap,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    presenter.advanceMs(10_000);
    presenter.advanceMs(10_000);
    expect(session.snapshot.heapLoads).toBe(2);
    const twoInFlight = presenter.snapshot(10_001).fallingOre;
    expect(twoInFlight).toHaveLength(2);
    expect(twoInFlight.every((f) => f.slot >= 0)).toBe(true);
    presenter.advanceMs(pickupMsPerLoad(0));
    const afterPickup = presenter.snapshot(10_001).fallingOre;
    expect(afterPickup.length).toBeLessThanOrEqual(session.snapshot.heapLoads);
    expect(afterPickup.every((f) => f.slot >= 0)).toBe(true);
  });

  it("reports no fallingOre after offline catch-up with a deep Heap", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: 5,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.snapshot().fallingOre).toEqual([]);
  });
});
