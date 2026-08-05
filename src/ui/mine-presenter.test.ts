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
import { SWING_IMPACT_FRAME } from "../data/dwarf-animation-timing";
import { createHeapPileSim } from "../core/heap-pile-sim";
import { createMinePresenter, FACE_SLIDE_MS } from "./mine-presenter";
import type { MiningAudio } from "./mining-audio";
import {
  heapOreContentCenter,
  heapOreRadius,
} from "./heap-ore-variants";
import {
  HEAP_BIN_CEILING_Y,
  HEAP_BIN_EAST_X,
  HEAP_BIN_FLOOR_Y,
  HEAP_BIN_WEST_X,
  HAULER_GRAB_X,
  HEAP_GRAB_Y,
  HEAP_PILE_SEED,
  HEAP_SPAWN_X,
  ORE_FALL_MS,
  ORE_SPAWN_BOTTOM,
} from "./pane-layout";
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

  function advanceToSwingBoundaries(
    presenter: ReturnType<typeof createMinePresenter>,
    tickDeltas: number[],
    boundariesMs: number[],
  ): void {
    let tick = 0;
    for (const boundaryMs of boundariesMs) {
      while (presenter.simNowMs < boundaryMs) {
        const remaining = boundaryMs - presenter.simNowMs;
        const delta = tickDeltas[tick % tickDeltas.length]!;
        presenter.advanceMs(Math.min(delta, remaining));
        tick += 1;
      }
      const snap = presenter.snapshot(presenter.simNowMs);
      expect(snap.swingFraction).toBeCloseTo(0, 5);
      expect(snap.frameIndex).toBe(SWING_IMPACT_FRAME);
    }
  }

  it("samples SWING_IMPACT_FRAME at Swing boundaries under drift with Pick Damage > 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), pickDamageUpgradeCount: 1 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    const drifts = [2, 3, 4, 5, 6, 7, 8];
    const tickDeltas = Array.from({ length: 40 }, (_, i) => 250 + drifts[i % drifts.length]!);
    advanceToSwingBoundaries(presenter, tickDeltas, [1000, 2000, 3000, 4000, 5000]);
  });

  it("samples SWING_IMPACT_FRAME at Swing boundaries under jank with Pick Damage > 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: { ...initialSnapshot(), pickDamageUpgradeCount: 1 },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    const tickDeltas = Array.from({ length: 40 }, (_, i) =>
      (i + 1) % 17 === 0 ? 400 : 250,
    );
    advanceToSwingBoundaries(presenter, tickDeltas, [1000, 2000, 3000, 4000, 5000]);
  });

  it("is chunk-neutral for queued swing cue times when Pick Damage exceeds 1", () => {
    const upgraded = { ...initialSnapshot(), pickDamageUpgradeCount: 1 };
    const sessionA = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: upgraded,
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
      snapshot: upgraded,
    });
    const audioB = spyMiningAudio();
    const presenterB = createMinePresenter(sessionB, { audio: audioB });
    presenterB.start();
    presenterB.advanceMs(1000);

    expect(swingCueTimes(audioA)[0]).toBeCloseTo(1000, 5);
    expect(swingCueTimes(audioB)[0]).toBeCloseTo(1000, 5);
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

  it("with crewSize 2 idles the Miner on a full Heap while the Heap stays full", () => {
    const cap = heapCapacityFor(0);
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
      snapshot: {
        ...initialSnapshot(),
        crewSize: 2,
        heapLoads: cap,
        heapOre: cap,
        bagLoads: carryCapacityFor(0),
        bagOre: carryCapacityFor(0),
        haulRemainingMs: 100_000,
      },
    });
    const presenter = createMinePresenter(session);
    presenter.start();
    expect(presenter.snapshot().animation).toBe("idle");
    presenter.advanceMs(pickupMsPerLoad(0));
    expect(presenter.snapshot().animation).toBe("idle");
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

  it("seeds no fallingOre for a two-Dwarf Crew — pile bodies spawn directly", () => {
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
    expect(presenter.snapshot(10_000).fallingOre).toEqual([]);
    expect(presenter.snapshot(10_125).fallingOre).toEqual([]);
    expect(presenter.snapshot(10_000 + ORE_FALL_MS).fallingOre).toEqual([]);
    expect(presenter.snapshot(10_125).heapOre.length).toBe(1);
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
      { slot: 0, progress: 0 },
    ]);
    expect(presenter.snapshot(10_125).fallingOre).toEqual([
      { slot: 0, progress: 0.5 },
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
      { slot: 0, progress: 0.5 },
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

  it("does not track fallingOre for a two-Dwarf Crew when heapLoads drops", () => {
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
    expect(presenter.snapshot(10_001).fallingOre).toEqual([]);
    presenter.advanceMs(pickupMsPerLoad(0));
    expect(presenter.snapshot(10_001).fallingOre).toEqual([]);
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

  describe("heap pile on TunnelSnapshot", () => {
    const twoDwarfBase = {
      ...initialSnapshot(),
      crewSize: 2,
    };

    function twoDwarfPresenter(
      snapshotOverrides: Partial<typeof initialSnapshot> = {},
    ) {
      const session = createMiningSession({
        store: memoryStore(),
        now: () => 0,
        snapshot: { ...twoDwarfBase, ...snapshotOverrides },
      });
      const presenter = createMinePresenter(session);
      presenter.start();
      return { session, presenter };
    }

    it("exposes settled Heap Ore on the Tunnel snapshot for a two-Dwarf Crew", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 3 });
      const snap = presenter.snapshot();
      expect(snap.heapOre).toHaveLength(3);
      for (const ore of snap.heapOre) {
        expect(ore).toEqual(
          expect.objectContaining({
            id: expect.any(Number),
            left: expect.any(Number),
            bottom: expect.any(Number),
            variantIndex: expect.any(Number),
          }),
        );
        expect(ore.variantIndex).toBeGreaterThanOrEqual(0);
        expect(ore.variantIndex).toBeLessThan(6);
      }
      expect(snap.carriedVariantIndex).toBeUndefined();
      expect(snap.heapLoads).toBe(3);
      expect(snap.crewSize).toBe(2);
      expect(snap.fallingOre).toEqual([]);
    });

    it("rests a deep Heap on first snapshot without falling Ore", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 17 });
      const snap = presenter.snapshot();
      expect(snap.heapOre).toHaveLength(17);
      const ids = snap.heapOre.map((o) => o.id);
      expect(ids).toEqual([...ids].sort((a, b) => a - b));
      for (const ore of snap.heapOre) {
        expect(ore.bottom).toBeLessThanOrEqual(112);
      }
    });

    it("targets zero bodies for a one-Dwarf Crew", () => {
      const session = createMiningSession({
        store: memoryStore(),
        now: () => 0,
      });
      const presenter = createMinePresenter(session);
      presenter.start();
      const snap = presenter.snapshot();
      expect(snap.heapOre).toEqual([]);
      expect(snap.carriedVariantIndex).toBeUndefined();
    });

    it("targets heapLoads mid-pickup below the midpoint", () => {
      const { presenter } = twoDwarfPresenter({
        heapLoads: 5,
        pickupProgressMs: 2_500,
      });
      expect(presenter.snapshot().heapOre).toHaveLength(5);
    });

    it("targets heapLoads minus one past the pickup midpoint", () => {
      const { presenter } = twoDwarfPresenter({
        heapLoads: 5,
        pickupProgressMs: 7_500,
      });
      const snap = presenter.snapshot();
      expect(snap.heapOre).toHaveLength(4);
      expect(snap.carriedVariantIndex).toBeDefined();
    });

    it("grabs the nearest Heap Ore for carriedVariantIndex at HEAP_PILE_SEED", () => {
      const { presenter } = twoDwarfPresenter({
        heapLoads: 5,
        pickupProgressMs: 0,
      });
      presenter.advanceMs(7_500);
      const snap = presenter.snapshot();

      const oracle = createHeapPileSim({
        bin: {
          floorY: HEAP_BIN_FLOOR_Y,
          westX: HEAP_BIN_WEST_X,
          eastX: HEAP_BIN_EAST_X,
          ceilingY: HEAP_BIN_CEILING_Y,
        },
        seed: HEAP_PILE_SEED,
      });
      const variantByBodyId = new Map<number, number>();
      for (let v = 0; v < 5; v += 1) {
        const id = oracle.spawnJittered(
          heapOreRadius(v),
          HEAP_SPAWN_X,
          ORE_SPAWN_BOTTOM,
        );
        variantByBodyId.set(id, v);
      }
      oracle.settle();
      const removedId = oracle.removeGrabbed(HAULER_GRAB_X, HEAP_GRAB_Y);
      expect(removedId).not.toBeNull();
      expect(snap.carriedVariantIndex).toBe(variantByBodyId.get(removedId!));
    });

    it("caps visible Heap Ore at 20 Loads while heapLoads keeps counting", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 40 });
      expect(presenter.snapshot().heapOre).toHaveLength(20);
    });

    it("keeps pile target unchanged when heapLoads decrements at return-leg end", () => {
      const beforeReturn = twoDwarfPresenter({
        heapLoads: 3,
        pickupProgressMs: 7_500,
      });
      const targetBefore = beforeReturn.presenter.snapshot().heapOre.length;

      const afterReturn = twoDwarfPresenter({
        heapLoads: 2,
        pickupProgressMs: 0,
      });
      const targetAfter = afterReturn.presenter.snapshot().heapOre.length;
      expect(targetBefore).toBe(2);
      expect(targetAfter).toBe(2);
    });

    it("spawns one falling body when a single Load arrives during live play", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 0 });
      presenter.advanceMs(10_000);
      expect(presenter.snapshot().heapLoads).toBe(1);
      const atDrop = presenter.simNowMs;
      const snap = presenter.snapshot(atDrop + 50);
      expect(snap.heapOre).toHaveLength(1);
      expect(snap.heapOre[0]!.bottom).toBeLessThan(40);
    });

    it("settles five bodies when heapLoads jumps by five", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 5 });
      const snap = presenter.snapshot();
      expect(snap.heapOre).toHaveLength(5);
      const bottoms = snap.heapOre.map((o) => o.bottom);
      expect(new Set(bottoms).size).toBeGreaterThan(1);
    });

    it("samples an interpolated snapshot after the presentation clock without rewinding the pile", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 5 });
      presenter.advanceMs(250);
      const t = presenter.simNowMs;
      presenter.snapshot(t);
      expect(() => presenter.snapshot()).not.toThrow();
    });

    it("cycles six Ore variants in spawn order across seven Loads", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 7 });
      const variants = presenter.snapshot().heapOre.map((o) => o.variantIndex);
      expect(variants).toEqual([0, 1, 2, 3, 4, 5, 0]);
    });

    it("keeps a Heap Ore variant when another Load is lifted off the pile", () => {
      const session = createMiningSession({
        store: memoryStore(),
        now: () => 0,
        snapshot: {
          ...twoDwarfBase,
          heapLoads: 3,
          pickupProgressMs: 0,
        },
      });
      const presenter = createMinePresenter(session);
      presenter.start();
      const survivorId = presenter.snapshot().heapOre[0]!.id;
      const variantBefore = presenter.snapshot().heapOre[0]!.variantIndex;

      presenter.advanceMs(7_500);
      const midPickup = presenter.snapshot();
      expect(midPickup.heapOre).toHaveLength(2);
      const survivor = midPickup.heapOre.find((o) => o.id === survivorId);
      expect(survivor?.variantIndex).toBe(variantBefore);
    });

    it("keeps the carried Ore variant stable across lifted pickup frames", () => {
      const { presenter } = twoDwarfPresenter({
        heapLoads: 5,
        pickupProgressMs: 7_500,
      });
      const first = presenter.snapshot();
      const second = presenter.snapshot();
      const third = presenter.snapshot(1_000);
      expect(first.carriedVariantIndex).toBeDefined();
      expect(second.carriedVariantIndex).toBe(first.carriedVariantIndex);
      expect(third.carriedVariantIndex).toBe(first.carriedVariantIndex);
    });

    it("places Heap Ore at pane coordinates from native art content centres", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 6 });
      const snap = presenter.snapshot();

      const oracle = createHeapPileSim({
        bin: {
          floorY: HEAP_BIN_FLOOR_Y,
          westX: HEAP_BIN_WEST_X,
          eastX: HEAP_BIN_EAST_X,
          ceilingY: HEAP_BIN_CEILING_Y,
        },
        seed: HEAP_PILE_SEED,
      });
      for (let v = 0; v < 6; v += 1) {
        oracle.spawnJittered(heapOreRadius(v), HEAP_SPAWN_X, ORE_SPAWN_BOTTOM);
      }
      oracle.settle();

      function expectedForVariant(variantIndex: number): {
        left: number;
        bottom: number;
      } {
        const body = oracle.bodies[variantIndex]!;
        const { cx, cyFromBottom } = heapOreContentCenter(variantIndex);
        return {
          left: Math.round(body.x - cx),
          bottom: Math.round(body.y - cyFromBottom),
        };
      }

      const largeB = snap.heapOre.find((o) => o.variantIndex === 1);
      const small = snap.heapOre.find((o) => o.variantIndex === 5);
      expect(largeB).toEqual(
        expect.objectContaining(expectedForVariant(1)),
      );
      expect(small).toEqual(
        expect.objectContaining(expectedForVariant(5)),
      );
    });

    it("returns deeply equal snapshots when snapshot(t) is called twice", () => {
      const { presenter } = twoDwarfPresenter({ heapLoads: 5 });
      const t = 1000;
      const a = presenter.snapshot(t);
      const b = presenter.snapshot(t);
      expect(a).toEqual(b);
      expect(a.heapOre).toEqual(b.heapOre);
    });

    it("leaves bag fallingOre unchanged for a one-Dwarf Crew", () => {
      const session = createMiningSession({
        store: memoryStore(),
        now: () => 0,
      });
      const presenter = createMinePresenter(session);
      presenter.start();
      presenter.advanceMs(10_000);
      const snap = presenter.snapshot(10_125);
      expect(snap.heapOre).toEqual([]);
      expect(snap.fallingOre).toEqual([
        { slot: 0, progress: 0.5 },
      ]);
    });
  });
});
