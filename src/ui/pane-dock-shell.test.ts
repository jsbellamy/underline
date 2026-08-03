// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { mountDockShell } from "./dock-root";
import { createFrameMetrics } from "./frame-metrics";
import { mountPaneShell, startPaneRoot } from "./pane-root";
import { PUMP_INTERVAL_MS } from "./pump";

function createStubDockWindow() {
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

function createPanePumpHarness(options?: { frameMetrics?: ReturnType<typeof createFrameMetrics> }) {
  let clock = 0;
  const rafCallbacks: FrameRequestCallback[] = [];
  const intervalCallbacks: Array<() => void> = [];
  let intervalId = 0;

  const doc = {
    hidden: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as Document;

  const frameMetrics =
    options?.frameMetrics ?? createFrameMetrics({ now: () => clock });

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
    dockWindow: createStubDockWindow(),
    busFactory: () => ({
      publish: vi.fn(),
      close: vi.fn(),
    }),
    deferPump: true,
    frameMetrics,
    pumpSchedule,
  });

  function setClock(ms: number): void {
    clock = ms;
  }

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

  return {
    root,
    shell,
    frameMetrics,
    setClock,
    runRafAt,
    runIntervals,
  };
}

describe("mountPaneShell", () => {
  it("mounts full-band Tunnel, Colony chip, and an open-dock control", () => {
    const root = document.createElement("main");
    const shell = mountPaneShell(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
      deferPump: true,
    });

    expect(root.querySelector(".pane")).not.toBeNull();
    expect(root.querySelector(".pane-dig-rate-line")).toBeNull();
    expect(root.querySelector(".pane-tunnel")).not.toBeNull();
    expect(root.querySelector("[data-open-dock]")).not.toBeNull();
    expect(root.querySelector("[data-dwarf]")).not.toBeNull();

    shell.destroy();
  });

  it("toggles the Dock port and publishes dock-opened / dock-closed", async () => {
    const publish = vi.fn();
    const toggle = vi.fn(async () => true);
    const root = document.createElement("main");
    const shell = mountPaneShell(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle,
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish,
        close: vi.fn(),
      }),
      deferPump: true,
    });

    const button = root.querySelector<HTMLButtonElement>("[data-open-dock]");
    expect(button).not.toBeNull();
    button!.click();
    await Promise.resolve();
    await Promise.resolve();

    expect(toggle).toHaveBeenCalledOnce();
    expect(publish).toHaveBeenCalledWith({ type: "dock-opened" });

    toggle.mockResolvedValueOnce(false);
    button!.click();
    await Promise.resolve();
    await Promise.resolve();
    expect(publish).toHaveBeenCalledWith({ type: "dock-closed" });

    shell.destroy();
  });

  it("returns null from frameMetrics before the pump starts", () => {
    const harness = createPanePumpHarness();
    expect(harness.shell.frameMetrics()).toBeNull();
    harness.shell.destroy();
  });

  it("records tick samples after driving the pump through injected schedulers", () => {
    const harness = createPanePumpHarness();
    expect(harness.shell.frameMetrics()).toBeNull();

    harness.shell.startPump();
    harness.setClock(PUMP_INTERVAL_MS);
    harness.runIntervals();
    harness.runRafAt(PUMP_INTERVAL_MS);
    harness.setClock(PUMP_INTERVAL_MS * 2);
    harness.runIntervals();
    harness.runRafAt(PUMP_INTERVAL_MS * 2);

    const report = harness.shell.frameMetrics();
    expect(report).not.toBeNull();
    expect(report!.tickSampleCount).toBeGreaterThan(0);
    expect(report!.tickPhases.advance.maxMs).toBeGreaterThanOrEqual(0);

    harness.shell.destroy();
  });

  it("preserves frame metrics across stop and restart", () => {
    const harness = createPanePumpHarness();

    harness.shell.startPump();
    harness.setClock(PUMP_INTERVAL_MS);
    harness.runIntervals();
    harness.runRafAt(PUMP_INTERVAL_MS);
    const afterFirst = harness.shell.frameMetrics()!.tickSampleCount;
    expect(afterFirst).toBeGreaterThan(0);

    harness.shell.stop();
    harness.shell.startPump();
    harness.setClock(PUMP_INTERVAL_MS * 2);
    harness.runIntervals();
    harness.runRafAt(PUMP_INTERVAL_MS * 2);

    const afterRestart = harness.shell.frameMetrics();
    expect(afterRestart).not.toBeNull();
    expect(afterRestart!.tickSampleCount).toBeGreaterThan(afterFirst);

    harness.shell.destroy();
  });

  it("creates production frame metrics when none is injected", () => {
    let clock = 0;
    const rafCallbacks: FrameRequestCallback[] = [];
    const intervalCallbacks: Array<() => void> = [];
    let intervalId = 0;
    const doc = {
      hidden: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Document;

    const root = document.createElement("main");
    const shell = mountPaneShell(root, {
      dockWindow: createStubDockWindow(),
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
      deferPump: true,
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

    expect(shell.frameMetrics()).toBeNull();
    shell.startPump();
    clock = PUMP_INTERVAL_MS;
    for (const callback of intervalCallbacks) {
      callback();
    }
    runRafCallbacks(rafCallbacks, clock);

    expect(shell.frameMetrics()?.tickSampleCount).toBeGreaterThan(0);
    shell.destroy();
  });
});

function runRafCallbacks(
  rafCallbacks: FrameRequestCallback[],
  at: number,
): void {
  const callbacks = rafCallbacks.splice(0);
  for (const callback of callbacks) {
    callback(at);
  }
}

describe("mountDockShell", () => {
  it("mounts the Colony surface with Dig Rate and Upgrade controls", () => {
    const root = document.createElement("main");
    const shell = mountDockShell(root, {
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
    });
    expect(root.querySelector("[data-colony]")).not.toBeNull();
    expect(root.querySelector("[data-buy-upgrade]")).not.toBeNull();
    expect(root.querySelector("[data-smelter]")).not.toBeNull();
    shell.destroy();
  });
});

describe("startPaneRoot", () => {
  it("mounts the mining Pane shell", () => {
    const root = document.createElement("main");
    const result = startPaneRoot(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
      deferPump: true,
    });
    expect(root.querySelector(".pane")).not.toBeNull();
    result.dispose();
  });
});
