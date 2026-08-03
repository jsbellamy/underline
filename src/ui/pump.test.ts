// @vitest-environment happy-dom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createFrameMetrics } from "./frame-metrics";
import {
  HIDDEN_HEARTBEAT_MS,
  MAX_CATCH_UP_BUDGET_MS,
  MAX_CATCH_UP_CHUNK_MS,
  PUMP_INTERVAL_MS,
  startPump,
} from "./pump";

describe("live pump loop", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("pumps the Engine every 250ms while visible", () => {
    const advanceBy = vi.fn(() => [] as unknown[]);
    const render = vi.fn();
    const doc = document;
    Object.defineProperty(doc, "hidden", { configurable: true, value: false });

    const pump = startPump({
      advanceBy,
      onAdvance: vi.fn(),
      render,
      document: doc,
    });

    vi.advanceTimersByTime(PUMP_INTERVAL_MS);
    expect(advanceBy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(PUMP_INTERVAL_MS * 3);
    expect(advanceBy).toHaveBeenCalledTimes(4);

    pump.stop();
  });

  it("stops rendering and drops pumping to a 5s heartbeat when hidden", () => {
    const advanceBy = vi.fn(() => [] as unknown[]);
    const render = vi.fn();
    const doc = document;
    Object.defineProperty(doc, "hidden", { configurable: true, value: false });

    const pump = startPump({
      advanceBy,
      onAdvance: vi.fn(),
      render,
      document: doc,
    });

    vi.advanceTimersByTime(PUMP_INTERVAL_MS);
    expect(advanceBy).toHaveBeenCalledTimes(1);

    Object.defineProperty(doc, "hidden", { configurable: true, value: true });
    doc.dispatchEvent(new Event("visibilitychange"));
    render.mockClear();
    advanceBy.mockClear();

    vi.advanceTimersByTime(PUMP_INTERVAL_MS * 4);
    expect(render).not.toHaveBeenCalled();
    expect(advanceBy).not.toHaveBeenCalled();

    vi.advanceTimersByTime(HIDDEN_HEARTBEAT_MS);
    expect(advanceBy).toHaveBeenCalledTimes(1);

    Object.defineProperty(doc, "hidden", { configurable: true, value: false });
    doc.dispatchEvent(new Event("visibilitychange"));
    vi.advanceTimersByTime(PUMP_INTERVAL_MS);
    expect(advanceBy.mock.calls.length).toBeGreaterThanOrEqual(2);

    pump.stop();
  });

  it("renders once per delivered animation frame with no wall-clock gate", () => {
    let clock = 0;
    const render = vi.fn();
    const rafCallbacks: FrameRequestCallback[] = [];
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const pump = startPump({
      advanceBy: vi.fn(() => [] as unknown[]),
      onAdvance: vi.fn(),
      render,
      now: () => clock,
      requestAnimationFrame: (callback) => {
        rafCallbacks.push(callback);
        return rafCallbacks.length;
      },
      cancelAnimationFrame: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      document: doc,
    });

    function runRafAt(at: number): void {
      clock = at;
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(at);
      }
    }

    const frameTimesMs: number[] = [];
    for (let frame = 1; frame <= 12; frame++) {
      frameTimesMs.push(Math.round(frame * 16.7));
    }
    for (const at of frameTimesMs) {
      runRafAt(at);
    }

    expect(render.mock.calls.length).toBe(frameTimesMs.length);

    pump.stop();
  });

  it("renders on consecutive rAF ticks even when they arrive 5ms apart", () => {
    let clock = 0;
    const render = vi.fn();
    const rafCallbacks: FrameRequestCallback[] = [];
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const pump = startPump({
      advanceBy: vi.fn(() => [] as unknown[]),
      onAdvance: vi.fn(),
      render,
      now: () => clock,
      requestAnimationFrame: (callback) => {
        rafCallbacks.push(callback);
        return rafCallbacks.length;
      },
      cancelAnimationFrame: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      document: doc,
    });

    function runRafAt(at: number): void {
      clock = at;
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(at);
      }
    }

    runRafAt(10);
    runRafAt(15);

    expect(render).toHaveBeenCalledTimes(2);

    pump.stop();
  });

  it("cancels the pending rAF and performs no further renders after stop()", () => {
    const render = vi.fn();
    const rafCallbacks: FrameRequestCallback[] = [];
    const cancelAnimationFrame = vi.fn();
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const pump = startPump({
      advanceBy: vi.fn(() => [] as unknown[]),
      onAdvance: vi.fn(),
      render,
      requestAnimationFrame: (callback) => {
        rafCallbacks.push(callback);
        return rafCallbacks.length;
      },
      cancelAnimationFrame,
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      document: doc,
    });

    expect(rafCallbacks.length).toBe(1);
    pump.stop();
    expect(cancelAnimationFrame).toHaveBeenCalled();
    render.mockClear();

    for (const callback of rafCallbacks.splice(0)) {
      callback(0);
    }
    expect(render).not.toHaveBeenCalled();

    pump.stop();
  });
});

describe("frame metrics wiring", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null from frameMetrics when no recorder was supplied", () => {
    const doc = document;
    Object.defineProperty(doc, "hidden", { configurable: true, value: false });

    const pump = startPump({
      advanceBy: vi.fn(() => [] as unknown[]),
      onAdvance: vi.fn(),
      render: vi.fn(),
      document: doc,
    });

    expect(pump.frameMetrics()).toBeNull();
    pump.stop();
  });

  it("records one sample per render the pump performs when a recorder is supplied", () => {
    let clock = 0;
    const render = vi.fn();
    const rafCallbacks: FrameRequestCallback[] = [];
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;
    const frameMetrics = createFrameMetrics({ now: () => clock });

    const pump = startPump({
      advanceBy: vi.fn(() => [] as unknown[]),
      onAdvance: vi.fn(),
      render,
      frameMetrics,
      now: () => clock,
      requestAnimationFrame: (callback) => {
        rafCallbacks.push(callback);
        return rafCallbacks.length;
      },
      cancelAnimationFrame: vi.fn(),
      setInterval: vi.fn(),
      clearInterval: vi.fn(),
      document: doc,
    });

    function runRafAt(at: number): void {
      clock = at;
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(at);
      }
    }

    for (let at = 17; at <= 100; at += 17) {
      runRafAt(at);
    }

    const report = pump.frameMetrics();
    expect(report).not.toBeNull();
    expect(report!.sampleCount).toBe(render.mock.calls.length);
    expect(render.mock.calls.length).toBeGreaterThanOrEqual(2);

    pump.stop();
  });

  it("records tick duration when the live pump interval fires with a recorder", () => {
    const doc = document;
    Object.defineProperty(doc, "hidden", { configurable: true, value: false });
    const frameMetrics = createFrameMetrics();
    const advanceBy = vi.fn(() => {
      return [{ seq: 1, atMs: 250, type: "tick" }];
    });

    const pump = startPump({
      advanceBy,
      onAdvance: vi.fn(),
      render: vi.fn(),
      frameMetrics,
      setInterval: ((handler: TimerHandler) =>
        setInterval(handler, PUMP_INTERVAL_MS)) as typeof setInterval,
      clearInterval: ((id: ReturnType<typeof setInterval>) =>
        clearInterval(id)) as typeof clearInterval,
      requestAnimationFrame: vi.fn(),
      cancelAnimationFrame: vi.fn(),
      document: doc,
    });

    vi.advanceTimersByTime(PUMP_INTERVAL_MS);

    const report = pump.frameMetrics();
    expect(report?.tickSampleCount).toBe(1);
    expect(report?.tickPhases.advance.maxMs).toBeGreaterThanOrEqual(0);

    pump.stop();
  });
});

function createPumpTestHarness(options?: {
  initialClock?: number;
  hidden?: boolean;
}) {
  let clock = options?.initialClock ?? 0;
  const advanceBy = vi.fn<(ms: number) => unknown[]>((_ms) => []);
  const render = vi.fn();
  const rafCallbacks: FrameRequestCallback[] = [];
  const intervalCallbacks: Array<() => void> = [];
  let intervalId = 0;

  const listeners = new Map<string, Set<EventListener>>();

  const doc = {
    hidden: options?.hidden ?? false,
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

  const setIntervalFn = vi.fn((callback: TimerHandler) => {
    const fn = typeof callback === "function" ? callback : () => {};
    intervalCallbacks.push(fn as () => void);
    intervalId += 1;
    return intervalId;
  });
  const setIntervalMock = setIntervalFn as unknown as typeof setInterval;

  const pump = startPump({
    advanceBy,
    onAdvance: vi.fn(),
    render,
    now: () => clock,
    requestAnimationFrame: (callback) => {
      rafCallbacks.push(callback);
      return rafCallbacks.length;
    },
    cancelAnimationFrame: vi.fn(),
    setInterval: setIntervalMock,
    clearInterval: vi.fn(),
    document: doc,
  });

  function runRafAt(at: number): void {
    clock = at;
    const callbacks = rafCallbacks.splice(0);
    for (const callback of callbacks) {
      callback(at);
    }
  }

  function runIntervals(): void {
    for (const callback of [...intervalCallbacks]) {
      callback();
    }
  }

  function setHidden(hidden: boolean): void {
    (doc as { hidden: boolean }).hidden = hidden;
    doc.dispatchEvent(new Event("visibilitychange"));
  }

  function totalAdvancedMs(): number {
    return advanceBy.mock.calls.reduce((sum, call) => sum + (call[0] as number), 0);
  }

  function assertAdvanceByDeltasValid(): void {
    for (const call of advanceBy.mock.calls) {
      const delta = call[0] as number;
      expect(delta).toBeGreaterThan(0);
      expect(Number.isInteger(delta)).toBe(true);
    }
  }

  return {
    pump,
    advanceBy,
    render,
    rafCallbacks,
    intervalCallbacks,
    setIntervalFn,
    get clock() {
      return clock;
    },
    get clockValue() {
      return clock;
    },
    set clockValue(ms: number) {
      clock = ms;
    },
    runRafAt,
    runIntervals,
    setHidden,
    totalAdvancedMs,
    assertAdvanceByDeltasValid,
    doc,
  };
}

describe("unhide catch-up drain", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("chunks an 8-hour hidden span into advanceBy calls no larger than MAX_CATCH_UP_CHUNK_MS", () => {
    const eightHoursMs = 8 * 60 * 60 * 1000;
    const h = createPumpTestHarness({ initialClock: 0, hidden: false });

    h.runIntervals();
    h.advanceBy.mockClear();

    h.setHidden(true);
    h.clockValue = eightHoursMs;
    h.setHidden(false);

    const hiddenSpanMs = eightHoursMs;
    let guard = 0;
    while (h.totalAdvancedMs() < hiddenSpanMs && guard < 50_000) {
      guard += 1;
      h.runRafAt(h.clock);
      if (h.rafCallbacks.length === 0 && h.totalAdvancedMs() < hiddenSpanMs) {
        h.clockValue += 16;
      }
    }

    expect(h.advanceBy).not.toHaveBeenCalledWith(hiddenSpanMs);
    for (const call of h.advanceBy.mock.calls) {
      expect(call[0] as number).toBeLessThanOrEqual(MAX_CATCH_UP_CHUNK_MS);
    }
    expect(h.totalAdvancedMs()).toBe(hiddenSpanMs);
    h.assertAdvanceByDeltasValid();

    h.pump.stop();
  });

  it("yields to the next animation frame when the catch-up budget is exceeded", () => {
    const h = createPumpTestHarness({ initialClock: 0, hidden: false });

    h.runIntervals();
    h.advanceBy.mockClear();

    h.setHidden(true);
    h.clockValue = MAX_CATCH_UP_CHUNK_MS * 3;
    h.setHidden(false);

    let pumpCallsThisFrame = 0;
    const unhideAt = h.clock;
    h.advanceBy.mockImplementation((_ms: number) => {
      pumpCallsThisFrame += 1;
      if (pumpCallsThisFrame === 1) {
        h.clockValue = unhideAt + MAX_CATCH_UP_BUDGET_MS + 1;
      }
      return [];
    });

    h.runRafAt(h.clock);
    const callsAfterFirstFrame = h.advanceBy.mock.calls.length;
    expect(callsAfterFirstFrame).toBeGreaterThan(0);
    expect(h.rafCallbacks.length).toBeGreaterThan(0);

    h.advanceBy.mockImplementation(() => []);
    h.runRafAt(h.clock);
    expect(h.advanceBy.mock.calls.length).toBeGreaterThan(callsAfterFirstFrame);

    h.pump.stop();
  });

  it("does not start the live interval until catch-up draining completes", () => {
    const h = createPumpTestHarness({ initialClock: 0, hidden: false });
    h.runIntervals();
    h.advanceBy.mockClear();
    h.setIntervalFn.mockClear();

    h.setHidden(true);
    h.setIntervalFn.mockClear();
    h.clockValue = MAX_CATCH_UP_CHUNK_MS * 2;
    h.setHidden(false);

    expect(h.setIntervalFn).not.toHaveBeenCalled();

    let guard = 0;
    while (h.totalAdvancedMs() < MAX_CATCH_UP_CHUNK_MS * 2 && guard < 10_000) {
      guard += 1;
      h.runRafAt(h.clock);
      h.clockValue += 16;
    }
    h.runRafAt(h.clock);

    expect(h.setIntervalFn).toHaveBeenCalled();

    h.pump.stop();
  });

  it("preserves remaining catch-up when hidden mid-drain and finishes on a later unhide", () => {
    const h = createPumpTestHarness({ initialClock: 0, hidden: false });
    h.runIntervals();
    h.advanceBy.mockClear();

    const hiddenSpanMs = MAX_CATCH_UP_CHUNK_MS * 2 + 5000;
    let cycleTotalMs = 0;
    let pumpCalls = 0;

    h.setHidden(true);
    h.clockValue = hiddenSpanMs;
    h.setHidden(false);

    const unhideAt = h.clock;
    h.advanceBy.mockImplementation((ms: number) => {
      cycleTotalMs += ms;
      pumpCalls += 1;
      if (pumpCalls === 1) {
        h.clockValue = unhideAt + MAX_CATCH_UP_BUDGET_MS + 1;
      }
      return [];
    });

    h.runRafAt(h.clock);
    expect(cycleTotalMs).toBeGreaterThan(0);
    expect(cycleTotalMs).toBeLessThan(hiddenSpanMs);

    h.setHidden(true);
    h.clockValue += HIDDEN_HEARTBEAT_MS;
    h.runIntervals();

    h.clockValue += 3000;
    h.setHidden(false);
    h.setIntervalFn.mockClear();

    let guard = 0;
    while (guard < 10_000) {
      guard += 1;
      h.runRafAt(h.clock);
      if (h.setIntervalFn.mock.calls.length > 0) {
        break;
      }
      h.clockValue += 16;
    }
    expect(h.setIntervalFn).toHaveBeenCalled();

    expect(cycleTotalMs).toBe(h.clockValue);
    h.assertAdvanceByDeltasValid();

    h.pump.stop();
  });
});

describe("live pump delta clamp", () => {
  it("advances by the actual elapsed ms when the interval fires early, not PUMP_INTERVAL_MS", () => {
    const h = createPumpTestHarness({ initialClock: 0, hidden: false });
    h.runIntervals();
    h.advanceBy.mockClear();

    h.clockValue = 1000;
    h.runIntervals();
    h.advanceBy.mockClear();

    h.clockValue = 1200;
    h.runIntervals();

    expect(h.advanceBy).toHaveBeenCalledTimes(1);
    expect(h.advanceBy).toHaveBeenCalledWith(200);

    h.pump.stop();
  });

  it("keeps sim advancement within a few ms of wall elapsed over many early intervals", () => {
    const startWall = 5000;
    const h = createPumpTestHarness({ initialClock: startWall, hidden: false });

    h.runIntervals();

    for (let i = 0; i < 200; i++) {
      h.clockValue += 200;
      h.runIntervals();
    }

    const simNowMs = h.totalAdvancedMs();
    const wallElapsed = h.clockValue - startWall;
    expect(simNowMs).toBeGreaterThanOrEqual(wallElapsed - 5);
    expect(simNowMs).toBeLessThanOrEqual(wallElapsed + 5);
    h.assertAdvanceByDeltasValid();

    h.pump.stop();
  });
});
