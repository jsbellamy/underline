import { describe, expect, it, vi } from "vitest";
import { createMiningSession } from "../core/mining-session";
import {
  advance as advanceEngine,
  HAUL_ROUND_TRIP_MS,
  initialSnapshot,
} from "../core/mining-engine";
import {
  persistSettings,
} from "../core/settings-save";
import { createMinePresenter, FACE_SLIDE_MS } from "./mine-presenter";
import type { MiningAudio } from "./mining-audio";

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
  swings: number[];
  breaks: number[];
} {
  const swings: number[] = [];
  const breaks: number[] = [];
  return {
    swings,
    breaks,
    swing(count: number) {
      swings.push(count);
    },
    faceBroken(count: number) {
      breaks.push(count);
    },
    setEnabled() {},
    isEnabled() {
      return true;
    },
    destroy() {},
  };
}

describe("mine presenter", () => {
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

  it("emits swing counts from elapsed ms at Dig Rate 1", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    presenter.advanceMs(1000);
    expect(audio.swings).toEqual([1]);

    presenter.advanceMs(500);
    expect(audio.swings).toEqual([1]);

    presenter.advanceMs(500);
    expect(audio.swings).toEqual([1, 1]);
  });

  it("is chunk-neutral for swing counts", () => {
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

    const totalA = audioA.swings.reduce((sum, n) => sum + n, 0);
    const totalB = audioB.swings.reduce((sum, n) => sum + n, 0);
    expect(totalA).toBe(1);
    expect(totalB).toBe(1);
    expect(totalA).toBe(totalB);
  });

  it("emits faceBroken with Face breaks gained in the tick", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    presenter.advanceMs(1_080_000);
    expect(audio.breaks).toEqual([1]);
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

  it("does not emit swing audio during a Haul", () => {
    const session = createMiningSession({
      store: memoryStore(),
      now: () => 0,
    });
    const audio = spyMiningAudio();
    const presenter = createMinePresenter(session, { audio });
    presenter.start();

    presenter.advanceMs(100_000);
    const swingsBeforeHaul = audio.swings.length;

    presenter.advanceMs(HAUL_ROUND_TRIP_MS);
    expect(audio.swings.length).toBe(swingsBeforeHaul);
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
});
