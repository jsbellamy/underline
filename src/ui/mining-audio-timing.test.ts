// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { browserSaveStore } from "../core/mining-save";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot, type MiningSnapshot } from "../core/mining-engine";
import { persistSettings } from "../core/settings-save";
import type { AudioClipId } from "../data/audio-pack";
import { createMiningAudio, MIN_RETRIGGER_MS } from "./mining-audio";
import { createMinePresenter } from "./mine-presenter";
import { mountPaneShell } from "./pane-root";
import { PUMP_INTERVAL_MS, HIDDEN_HEARTBEAT_MS } from "./pump";

const RUN_MS = 30_000;
const RAF_STEP_MS = 1000 / 60;
const ONSET_TOLERANCE_MS = 20;

interface RecordedStart {
  clip: AudioClipId;
  whenSec: number;
}

interface TimingRunResult {
  swingEvents: Array<{ cueAbsoluteMs: number }>;
  swingStarts: RecordedStart[];
  breakStarts: RecordedStart[];
}

function stubDockWindow() {
  return {
    open: vi.fn(async () => {}),
    close: vi.fn(async () => {}),
    toggle: vi.fn(async () => true),
    isOpen: () => false,
    reposition: vi.fn(async () => {}),
    syncPositionFromPane: vi.fn(async () => {}),
    destroy: vi.fn(),
  };
}

function stubBusFactory() {
  return () => ({
    publish: vi.fn(),
    close: vi.fn(),
  });
}

function createTimingHarness(options?: {
  soundEnabled?: boolean;
  snapshot?: MiningSnapshot;
}) {
  let clock = 0;
  const rafCallbacks: FrameRequestCallback[] = [];
  const intervalCallbacks: Array<() => void> = [];
  let intervalId = 0;
  const listeners = new Map<string, Set<EventListener>>();

  const doc = {
    hidden: false,
    addEventListener(type: string, listener: EventListener) {
      if (!listeners.has(type)) {
        listeners.set(type, new Set());
      }
      listeners.get(type)!.add(listener);
    },
    removeEventListener(type: string, listener: EventListener) {
      listeners.get(type)?.delete(listener);
    },
    dispatchEvent(event: Event) {
      for (const listener of listeners.get(event.type) ?? []) {
        listener(event);
      }
      return true;
    },
  } as unknown as Document;

  const swingBuffer = {} as AudioBuffer;
  const breakBuffer = {} as AudioBuffer;
  let decodeCount = 0;
  const recordedStarts: RecordedStart[] = [];
  let presentationAnchorMs = 0;

  const createAudioContext = vi.fn(() => {
    const createBufferSource = vi.fn(() => {
      const source = {
        buffer: null as AudioBuffer | null,
        connect: vi.fn(),
        start: vi.fn((whenSec: number) => {
          const clip: AudioClipId =
            source.buffer === swingBuffer
              ? "swing"
              : source.buffer === breakBuffer
                ? "break"
                : "swing";
          recordedStarts.push({ clip, whenSec });
        }),
      };
      return source;
    });

    return {
      get currentTime() {
        return presentationAnchorMs / 1000;
      },
      state: "running" as const,
      resume: vi.fn(async () => {}),
      decodeAudioData: vi.fn(async () => {
        decodeCount += 1;
        return decodeCount === 1 ? swingBuffer : breakBuffer;
      }),
      createBufferSource,
      destination: {},
      close: vi.fn(),
    } as unknown as AudioContext;
  });

  vi.stubGlobal(
    "AudioContext",
    vi.fn(function AudioContextStub(this: unknown) {
      return createAudioContext();
    }),
  );

  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    })),
  );

  const store = browserSaveStore();
  persistSettings(
    { schemaVersion: 1, soundEnabled: options?.soundEnabled ?? true },
    store,
  );

  const session = createMiningSession({
    store,
    now: () => clock,
    snapshot: options?.snapshot ?? initialSnapshot(),
  });

  const audio = createMiningAudio({ createAudioContext });
  audio.setEnabled(options?.soundEnabled ?? true);
  const releaseDueToOriginal = audio.releaseDueTo.bind(audio);
  // Observation-only: anchor AudioContext.currentTime to presentation ms for C4.
  vi.spyOn(audio, "releaseDueTo").mockImplementation((nowMs) => {
    presentationAnchorMs = nowMs;
    return releaseDueToOriginal(nowMs);
  });
  const presenter = createMinePresenter(session, { audio });

  const swingEvents: Array<{ cueAbsoluteMs: number }> = [];
  const faceBrokenEvents: Array<{ cueAbsoluteMs: number }> = [];
  let simTrackMs = 0;
  // Observation-only: record swing events with absolute cue ms for C3/C4.
  const advanceLive = session.advanceLive.bind(session);
  vi.spyOn(session, "advanceLive").mockImplementation((dtMs) => {
    const baseMs = simTrackMs;
    simTrackMs += dtMs;
    const result = advanceLive(dtMs);
    for (const event of result.events) {
      if (event.type === "swing") {
        swingEvents.push({ cueAbsoluteMs: baseMs + event.atMs });
      }
      if (event.type === "faceBroken") {
        faceBrokenEvents.push({ cueAbsoluteMs: baseMs + event.atMs });
      }
    }
    return result;
  });

  const pumpSchedule = {
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
  };

  const root = document.createElement("main");
  const shell = mountPaneShell(root, {
    dockWindow: stubDockWindow(),
    busFactory: stubBusFactory(),
    deferPump: true,
    session,
    presenter,
    pumpSchedule,
  });

  function runIntervals(): void {
    for (const callback of [...intervalCallbacks]) {
      callback();
    }
  }

  function runTick(targetMs: number): void {
    while (clock < targetMs) {
      const nextFrameMs = Math.min(targetMs, clock + RAF_STEP_MS);
      clock = nextFrameMs;
      if (nextFrameMs === targetMs) {
        runIntervals();
      }
      const pending = rafCallbacks.splice(0);
      for (const callback of pending) {
        callback(clock);
      }
    }
  }

  function flushPendingRaf(): void {
    let guard = 0;
    while (rafCallbacks.length > 0 && guard < 10_000) {
      guard += 1;
      const pending = rafCallbacks.splice(0);
      for (const callback of pending) {
        callback(clock);
      }
    }
  }

  function setHidden(hidden: boolean): void {
    (doc as { hidden: boolean }).hidden = hidden;
    doc.dispatchEvent(new Event("visibilitychange"));
  }

  function runHeartbeatSteps(untilMs: number): void {
    while (clock < untilMs) {
      clock = Math.min(untilMs, clock + HIDDEN_HEARTBEAT_MS);
      runIntervals();
    }
  }

  function drainCatchUp(): void {
    const targetMs = clock;
    let guard = 0;
    while (guard < 50_000) {
      guard += 1;
      const pending = rafCallbacks.splice(0);
      if (pending.length === 0) {
        break;
      }
      for (const callback of pending) {
        callback(targetMs);
      }
    }
    rafCallbacks.length = 0;
  }

  return {
    root,
    shell,
    doc,
    presenter,
    recordedStarts,
    swingEvents,
    faceBrokenEvents,
    get clock() {
      return clock;
    },
    set clock(ms: number) {
      clock = ms;
    },
    runTick,
    flushPendingRaf,
    runIntervals,
    setHidden,
    runHeartbeatSteps,
    drainCatchUp,
    swingStarts(): RecordedStart[] {
      return recordedStarts.filter((start) => start.clip === "swing");
    },
    breakStarts(): RecordedStart[] {
      return recordedStarts.filter((start) => start.clip === "break");
    },
    result(): TimingRunResult {
      return {
        swingEvents: [...swingEvents],
        swingStarts: this.swingStarts(),
        breakStarts: this.breakStarts(),
      };
    },
  };
}

function tickDurationsExact(): number[] {
  const deltas: number[] = [];
  let total = 0;
  while (total < RUN_MS) {
    deltas.push(PUMP_INTERVAL_MS);
    total += PUMP_INTERVAL_MS;
  }
  return deltas;
}

function tickDurationsDrift(): number[] {
  const drifts = [2, 3, 4, 5, 6, 7, 8];
  const deltas: number[] = [];
  let total = 0;
  let tick = 0;
  while (total < RUN_MS) {
    const drift = drifts[tick % drifts.length]!;
    const delta = PUMP_INTERVAL_MS + drift;
    deltas.push(delta);
    total += delta;
    tick += 1;
  }
  return deltas;
}

function tickDurationsJank(): number[] {
  const deltas: number[] = [];
  let total = 0;
  let tick = 0;
  while (total < RUN_MS) {
    tick += 1;
    const delta = tick % 17 === 0 ? 400 : PUMP_INTERVAL_MS;
    deltas.push(delta);
    total += delta;
  }
  return deltas;
}

async function runProfile(
  harness: ReturnType<typeof createTimingHarness>,
  tickDeltas: number[],
): Promise<TimingRunResult> {
  harness.shell.startPump();
  let clock = 0;
  for (const delta of tickDeltas) {
    clock += delta;
    harness.runTick(clock);
  }
  harness.flushPendingRaf();
  await vi.waitFor(() => expect(harness.swingStarts().length).toBeGreaterThan(0));
  return harness.result();
}

function assertSwingCorrespondence(result: TimingRunResult): void {
  const { swingEvents, swingStarts } = result;
  expect(swingStarts).toHaveLength(swingEvents.length);
  for (let i = 0; i < swingEvents.length; i += 1) {
    const event = swingEvents[i]!;
    const start = swingStarts[i]!;
    expect(start).toBeDefined();
    expect(start.clip).toBe("swing");
    if (i > 0) {
      expect(event.cueAbsoluteMs).toBeGreaterThan(
        swingEvents[i - 1]!.cueAbsoluteMs,
      );
      expect(start.whenSec).toBeGreaterThan(swingStarts[i - 1]!.whenSec);
    }
  }
}

function assertOnsetsWithinTolerance(result: TimingRunResult): void {
  const { swingEvents, swingStarts } = result;
  expect(swingStarts).toHaveLength(swingEvents.length);
  let maxErrorMs = 0;
  for (let i = 0; i < swingEvents.length; i += 1) {
    const cueAbsoluteMs = swingEvents[i]!.cueAbsoluteMs;
    const recordedMs = swingStarts[i]!.whenSec * 1000;
    const errorMs = Math.abs(recordedMs - cueAbsoluteMs);
    maxErrorMs = Math.max(maxErrorMs, errorMs);
    expect(errorMs).toBeLessThanOrEqual(ONSET_TOLERANCE_MS);
  }
}

describe("mining audio end-to-end timing", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("profile 1 — exact 250 ms ticks", () => {
    it("matches every swing event to one onset within 20 ms", async () => {
      const harness = createTimingHarness();
      const result = await runProfile(harness, tickDurationsExact());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      harness.shell.destroy();
    });
  });

  describe("profile 2 — 250 ms + cycling 2…8 ms drift", () => {
    it("matches every swing event to one onset within 20 ms", async () => {
      const harness = createTimingHarness();
      const result = await runProfile(harness, tickDurationsDrift());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      harness.shell.destroy();
    });
  });

  describe("profile 3 — 250 ms with every 17th tick at 400 ms", () => {
    it("matches every swing event to one onset within 20 ms", async () => {
      const harness = createTimingHarness();
      const result = await runProfile(harness, tickDurationsJank());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      harness.shell.destroy();
    });
  });

  describe("catch-up after hidden visibility", () => {
    it("does not machine-gun swings after a 60 s hidden span", async () => {
      const harness = createTimingHarness();
      harness.shell.startPump();
      harness.runTick(PUMP_INTERVAL_MS * 4);
      await vi.waitFor(() =>
        expect(harness.swingStarts().length).toBeGreaterThan(0),
      );

      const startsBeforeHide = harness.swingStarts().length;
      harness.setHidden(true);
      const hiddenUntil = harness.clock + 60_000;
      harness.runHeartbeatSteps(hiddenUntil);

      harness.recordedStarts.length = 0;
      harness.setHidden(false);
      harness.drainCatchUp();
      await vi.waitFor(() =>
        expect(harness.swingStarts().length).toBeGreaterThan(0),
      );

      const postCatchUpStarts = harness.swingStarts();
      const maxSwingsInFinalTick =
        Math.ceil((PUMP_INTERVAL_MS / 1000) * 1) + 1;
      expect(postCatchUpStarts.length).toBeLessThanOrEqual(maxSwingsInFinalTick);

      for (let i = 1; i < postCatchUpStarts.length; i += 1) {
        const gapMs =
          (postCatchUpStarts[i]!.whenSec - postCatchUpStarts[i - 1]!.whenSec) *
          1000;
        expect(gapMs).toBeGreaterThanOrEqual(MIN_RETRIGGER_MS);
      }

      expect(harness.swingEvents.length).toBeGreaterThan(startsBeforeHide);
      harness.shell.destroy();
    });
  });

  describe("muted playback", () => {
    it("records zero starts over a 30 s profile-2 run", async () => {
      const harness = createTimingHarness({ soundEnabled: false });
      harness.shell.startPump();
      let clock = 0;
      for (const delta of tickDurationsDrift()) {
        clock += delta;
        harness.runTick(clock);
      }
      harness.flushPendingRaf();
      await vi.waitFor(() =>
        expect(harness.swingEvents.length).toBeGreaterThan(0),
      );
      expect(harness.recordedStarts).toHaveLength(0);
      harness.shell.destroy();
    });
  });

  describe("upgraded Dig Rate and Pick Damage", () => {
    const upgradedSnapshot = {
      ...initialSnapshot(),
      digRateUpgradeCount: 1,
      pickDamageUpgradeCount: 1,
    };

    it("matches one swing onset per event on profile 1 with upgrades", async () => {
      const harness = createTimingHarness({ snapshot: upgradedSnapshot });
      const result = await runProfile(harness, tickDurationsExact());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      for (let i = 1; i < result.swingStarts.length; i += 1) {
        const gapMs =
          (result.swingStarts[i]!.whenSec - result.swingStarts[i - 1]!.whenSec) *
          1000;
        expect(gapMs).toBeGreaterThanOrEqual(MIN_RETRIGGER_MS);
      }
      harness.shell.destroy();
    });

    it("matches one swing onset per event on profile 2 with upgrades", async () => {
      const harness = createTimingHarness({ snapshot: upgradedSnapshot });
      const result = await runProfile(harness, tickDurationsDrift());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      harness.shell.destroy();
    });

    it("matches one swing onset per event on profile 3 with upgrades", async () => {
      const harness = createTimingHarness({ snapshot: upgradedSnapshot });
      const result = await runProfile(harness, tickDurationsJank());
      assertSwingCorrespondence(result);
      assertOnsetsWithinTolerance(result);
      harness.shell.destroy();
    });

    it("plays one break cue and no layered swing at Face break", async () => {
      const harness = createTimingHarness({
        snapshot: { ...initialSnapshot(), faceSwingProgress: 999 },
      });
      harness.presenter.start();
      harness.presenter.advanceMs(1000);
      harness.presenter.releaseAudioDueTo(1000);
      await vi.waitFor(
        () => expect(harness.breakStarts().length).toBe(1),
        { timeout: 5_000 },
      );
      const breakCueMs = harness.faceBrokenEvents[0]!.cueAbsoluteMs;
      const swingEventsAtBreak = harness.swingEvents.filter(
        (event) => Math.abs(event.cueAbsoluteMs - breakCueMs) <= ONSET_TOLERANCE_MS,
      );
      const swingAtBreak = harness.swingStarts().filter(
        (start) => Math.abs(start.whenSec * 1000 - breakCueMs) <= ONSET_TOLERANCE_MS,
      );
      expect(harness.faceBrokenEvents).toHaveLength(1);
      expect(swingEventsAtBreak).toHaveLength(0);
      expect(swingAtBreak).toHaveLength(0);
      harness.shell.destroy();
    });
  });
});
