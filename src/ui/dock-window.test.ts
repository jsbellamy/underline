import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it, vi } from "vitest";
import { DOCK_GAP_PX, DOCK_HEIGHT, dockRect } from "./dock-geometry";
import { PANE_HEIGHT, PANE_WIDTH } from "./pane-layout";
import {
  createCachedDockGeometryDeps,
  createDockWindowPort,
  createDockWindowWithOptionalParent,
  isMacOSPlatform,
  physicalRectToLogical,
  wrapDockWebviewWindow,
  type DockWebviewWindow,
  type DockWebviewWindowHandle,
} from "./dock-window";

function createManualScheduler() {
  const queue: Array<() => void | Promise<void>> = [];
  return {
    scheduleFrame(callback: () => void | Promise<void>) {
      queue.push(callback);
    },
    async flushOne() {
      const callback = queue.shift();
      if (!callback) {
        return;
      }
      await callback();
    },
    get depth() {
      return queue.length;
    },
  };
}

describe("physicalRectToLogical", () => {
  it("divides physical Pane and monitor coordinates by the Pane scale factor", () => {
    const physical = { x: 440, y: 1464, width: 960, height: 224 };
    expect(physicalRectToLogical(physical, 2)).toEqual({
      x: 220,
      y: 732,
      width: 480,
      height: 112,
    });
  });
});

describe("dock window port", () => {
  const monitor = { x: 0, y: 0, width: 1920, height: 1080 };
  const pane = { x: 220, y: 732, width: 480, height: 112 };
  const dockUrl = "http://test.local/?window=dock";

  function mockDockWindow(overrides: Partial<DockWebviewWindow> = {}): DockWebviewWindow & {
    callOrder: string[];
  } {
    const callOrder: string[] = [];
    return {
      callOrder,
      show: async () => {
        callOrder.push("show");
        await overrides.show?.();
      },
      hide: async () => {
        callOrder.push("hide");
        await overrides.hide?.();
      },
      setPosition: async (x, y) => {
        callOrder.push(`setPosition:${x},${y}`);
        await overrides.setPosition?.(x, y);
      },
      ready: async () => {
        callOrder.push("ready");
        await overrides.ready?.();
      },
    };
  }

  class TestLogicalPosition {
    constructor(
      readonly x: number,
      readonly y: number,
    ) {}
  }

  function createTauriCreatedOnceWindow() {
    const listeners = new Map<string, Array<() => void>>();
    const once = vi.fn((event: string, handler: () => void) => {
      const list = listeners.get(event) ?? [];
      list.push(handler);
      listeners.set(event, list);
      return Promise.resolve(() => {});
    });
    const windowRef = {
      show: vi.fn(async () => {}),
      hide: vi.fn(async () => {}),
      setPosition: vi.fn(async () => {}),
      once,
    };
    const wrapped = wrapDockWebviewWindow(windowRef, TestLogicalPosition, {
      awaitCreated: true,
    });
    return {
      wrapped,
      windowRef,
      once,
      emitCreated: () => {
        for (const handler of listeners.get("tauri://created") ?? []) {
          handler();
        }
      },
      emitError: () => {
        for (const handler of listeners.get("tauri://error") ?? []) {
          handler();
        }
      },
    };
  }

  function createPortWithWrappedNewWindow(
    extraDeps: Partial<Parameters<typeof createDockWindowPort>[0]> = {},
  ) {
    let tauriWindow: ReturnType<typeof createTauriCreatedOnceWindow> | null = null;
    const createDockWindow = vi.fn(async () => {
      tauriWindow = createTauriCreatedOnceWindow();
      queueMicrotask(() => {
        tauriWindow?.emitCreated();
      });
      return tauriWindow.wrapped;
    });
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow,
      ...extraDeps,
    });
    return { port, createDockWindow, getTauriWindow: () => tauriWindow };
  }

  it("manual-check: dock-no-pane-resize — reads pane geometry without calling pane resize APIs", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "dock-window.ts"),
      "utf8",
    );
    expect(source).not.toMatch(/getCurrentWindow\(\)\.set(Size|Fullscreen)/);
    expect(source).not.toMatch(/getCurrentWindow\(\)\.hide\(/);
    expect(source).toMatch(/scaleFactor/);
  });

  it("manual-check: dock-geometry-not-persisted — window-state restores pane position only and ignores the dock", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "..", "..", "src-tauri", "src", "lib.rs"),
      "utf8",
    );
    expect(source).toMatch(/with_state_flags\(StateFlags::POSITION\)/);
    expect(source).toMatch(/with_denylist\(&\["dock"\]\)/);
    expect(source).not.toMatch(/tauri_plugin_window_state::Builder::default\(\)\.build\(\)/);
  });

  it("does not mark the Dock open when ready rejects on a new window", async () => {
    const dock = mockDockWindow({
      ready: () => Promise.reject(new Error("tauri://error")),
    });
    const createDockWindow = vi.fn(async () => dock);
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow,
    });

    await port.open();

    expect(createDockWindow).toHaveBeenCalledOnce();
    expect(dock.callOrder).toEqual(["ready"]);
    expect(port.isOpen()).toBe(false);
  });

  it("opens a new Dock with create → ready → position → show", async () => {
    const dock = mockDockWindow();
    const createDockWindow = vi.fn(async () => dock);
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow,
    });

    await port.open();
    const expected = dockRect(pane, monitor);
    expect(createDockWindow).toHaveBeenCalledOnce();
    expect(dock.callOrder).toEqual([
      "ready",
      `setPosition:${expected.x},${expected.y}`,
      "show",
    ]);
    expect(port.isOpen()).toBe(true);
  });

  it("reuses an existing Dock with immediate ready, positions before show, and preserves hide/reopen", async () => {
    const dock = mockDockWindow();
    const createDockWindow = vi.fn();
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      createDockWindow,
    });

    await port.open();
    const expected = dockRect(pane, monitor);
    expect(createDockWindow).not.toHaveBeenCalled();
    expect(dock.callOrder.indexOf("ready")).toBeLessThan(
      dock.callOrder.indexOf(`setPosition:${expected.x},${expected.y}`),
    );
    expect(dock.callOrder.indexOf(`setPosition:${expected.x},${expected.y}`)).toBeLessThan(
      dock.callOrder.indexOf("show"),
    );
    expect(port.isOpen()).toBe(true);

    await port.close();
    expect(dock.callOrder).toContain("hide");
    expect(port.isOpen()).toBe(false);

    dock.callOrder.length = 0;
    await port.open();
    expect(dock.callOrder).toEqual([
      "ready",
      `setPosition:${expected.x},${expected.y}`,
      "show",
    ]);
    expect(createDockWindow).not.toHaveBeenCalled();
  });

  it("repositions only the Dock when the Pane moves", async () => {
    const dock = mockDockWindow();
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    const positionsBefore = dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length;
    moved?.();
    expect(frames.depth).toBe(1);
    await frames.flushOne();
    expect(
      dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length,
    ).toBe(positionsBefore + 1);
    expect(dock.callOrder.filter((entry) => entry === "show")).toHaveLength(1);
  });

  it("coalesces ten synchronous move events into one setPosition per frame", async () => {
    const dock = mockDockWindow();
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    const positionsBefore = dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length;
    for (let i = 0; i < 10; i += 1) {
      moved?.();
    }
    expect(frames.depth).toBe(1);
    await frames.flushOne();
    expect(
      dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length,
    ).toBe(positionsBefore + 1);
    expect(frames.depth).toBe(0);
  });

  it("runs one trailing setPosition for a move that arrives while applyPosition is in flight", async () => {
    const dock = mockDockWindow();
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    let releasePaneRead: (() => void) | undefined;
    let paneReads = 0;
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => {
        paneReads += 1;
        if (paneReads === 2) {
          await new Promise<void>((resolve) => {
            releasePaneRead = resolve;
          });
        }
        return pane;
      },
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    const positionsBefore = dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length;
    moved?.();
    const flushInFlight = frames.flushOne();
    await Promise.resolve();
    moved?.();
    expect(frames.depth).toBe(1);
    releasePaneRead?.();
    await flushInFlight;
    await frames.flushOne();
    expect(
      dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length,
    ).toBe(positionsBefore + 2);
  });

  it("lands the dock on dockRect of the last pane position after a move burst", async () => {
    const dock = mockDockWindow();
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    let currentPane = { ...pane };
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => ({ ...currentPane }),
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    const positions = [
      { ...pane, x: 100 },
      { ...pane, x: 200 },
      { ...pane, x: 300 },
    ];
    for (const next of positions) {
      currentPane = next;
      moved?.();
    }
    await frames.flushOne();
    const expected = dockRect(positions[positions.length - 1]!, monitor);
    expect(dock.callOrder[dock.callOrder.length - 1]).toBe(
      `setPosition:${expected.x},${expected.y}`,
    );
  });

  it("production adapter converts physical geometry using the Pane scale factor before dockRect", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "dock-window.ts"),
      "utf8",
    );
    expect(source).toMatch(/physicalRectToLogical/);
    expect(source).toMatch(/scaleFactor\(\)/);
  });

  it("positions the dock at dockRect with the configured gap for a bottom-parked pane", async () => {
    const dock = mockDockWindow();
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow: async () => dock,
    });

    await port.open();
    const expected = dockRect(pane, monitor);
    const expectedY = pane.y - DOCK_GAP_PX - DOCK_HEIGHT;
    expect(dock.callOrder).toContain(`setPosition:${expected.x},${expectedY}`);
  });

  it("manual-check: dock-position-only — calls setPanePosition only when dockRect paneX differs from pane.x", async () => {
    const dock = mockDockWindow();
    const setPanePosition = vi.fn(async () => {});
    const clampedPane = { x: 80, y: 732, width: 480, height: 112 };
    const portClamped = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => clampedPane,
      getMonitorForPane: async () => monitor,
      createDockWindow: async () => dock,
      setPanePosition,
    });
    await portClamped.open();
    const clampedRect = dockRect(clampedPane, monitor);
    expect(clampedRect.paneX).not.toBe(clampedPane.x);
    expect(setPanePosition).toHaveBeenCalledTimes(1);
    expect(setPanePosition).toHaveBeenCalledWith(clampedRect.paneX, clampedPane.y);

    const setPanePositionUnclamped = vi.fn(async () => {});
    const dock2 = mockDockWindow();
    const portUnclamped = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow: async () => dock2,
      setPanePosition: setPanePositionUnclamped,
    });
    await portUnclamped.open();
    expect(setPanePositionUnclamped).not.toHaveBeenCalled();

    dock.callOrder.length = 0;
    setPanePosition.mockClear();
    await portClamped.reposition({ pane: clampedPane, monitor });
    expect(setPanePosition).toHaveBeenCalledTimes(1);
    expect(setPanePosition).toHaveBeenCalledWith(clampedRect.paneX, clampedPane.y);
    expect(dock.callOrder.some((entry) => entry.startsWith("setPosition"))).toBe(true);

    dock2.callOrder.length = 0;
    await portUnclamped.syncPositionFromPane();
    expect(setPanePositionUnclamped).not.toHaveBeenCalled();

    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    const setPanePositionOnMove = vi.fn(async () => {});
    const dockMove = mockDockWindow();
    const portMove = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => clampedPane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dockMove,
      scheduleFrame: frames.scheduleFrame,
      setPanePosition: setPanePositionOnMove,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });
    await portMove.open();
    setPanePositionOnMove.mockClear();
    moved?.();
    await frames.flushOne();
    expect(setPanePositionOnMove).toHaveBeenCalledTimes(1);
    expect(setPanePositionOnMove).toHaveBeenCalledWith(clampedRect.paneX, clampedPane.y);
  });

  it("fetches scaleFactor and currentMonitor at most once across a drag, never outerSize", async () => {
    const frames = createManualScheduler();
    const dock = mockDockWindow();
    let moved: (() => void) | undefined;
    let physicalX = 440;
    const host = {
      scaleFactor: vi.fn(async () => 2),
      outerPosition: vi.fn(async () => ({ x: physicalX, y: 1464 })),
      outerSize: vi.fn(async () => ({ width: 960, height: 224 })),
      currentMonitor: vi.fn(async () => ({
        position: { x: 0, y: 0 },
        size: { width: 3840, height: 2160 },
      })),
    };
    const geometry = createCachedDockGeometryDeps(host);
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: geometry.getPaneOuterPosition,
      getMonitorForPane: geometry.getMonitorForPane,
      invalidateGeometryCache: geometry.invalidateGeometryCache,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    for (let i = 0; i < 8; i += 1) {
      physicalX += 10;
      moved?.();
    }
    await frames.flushOne();

    expect(host.scaleFactor).toHaveBeenCalledTimes(1);
    expect(host.currentMonitor).toHaveBeenCalledTimes(1);
    expect(host.outerSize).not.toHaveBeenCalled();
    expect(host.outerPosition.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("keeps steady-state IPC to outerPosition and setPosition per coalesced frame", async () => {
    const frames = createManualScheduler();
    const dock = mockDockWindow();
    let moved: (() => void) | undefined;
    let physicalX = 440;
    const host = {
      scaleFactor: vi.fn(async () => 2),
      outerPosition: vi.fn(async () => ({ x: physicalX, y: 1464 })),
      currentMonitor: vi.fn(async () => ({
        position: { x: 0, y: 0 },
        size: { width: 3840, height: 2160 },
      })),
    };
    const geometry = createCachedDockGeometryDeps(host);
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: geometry.getPaneOuterPosition,
      getMonitorForPane: geometry.getMonitorForPane,
      invalidateGeometryCache: geometry.invalidateGeometryCache,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    const outerBefore = host.outerPosition.mock.calls.length;
    const setBefore = dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length;
    host.scaleFactor.mockClear();
    host.currentMonitor.mockClear();

    physicalX = 500;
    moved?.();
    await frames.flushOne();

    expect(host.outerPosition.mock.calls.length - outerBefore).toBe(1);
    expect(
      dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length - setBefore,
    ).toBe(1);
    expect(host.scaleFactor).not.toHaveBeenCalled();
    expect(host.currentMonitor).not.toHaveBeenCalled();
  });

  it("invalidates scale and monitor caches on monitor change, close, and destroy", async () => {
    const frames = createManualScheduler();
    const dock = mockDockWindow();
    let moved: (() => void) | undefined;
    let scale = 2;
    let monitorPhysical = {
      position: { x: 0, y: 0 },
      size: { width: 3840, height: 2160 },
    };
    const host = {
      scaleFactor: vi.fn(async () => scale),
      outerPosition: vi.fn(async () => ({ x: 440, y: 1464 })),
      currentMonitor: vi.fn(async () => monitorPhysical),
    };
    const geometry = createCachedDockGeometryDeps(host);
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: geometry.getPaneOuterPosition,
      getMonitorForPane: geometry.getMonitorForPane,
      invalidateGeometryCache: geometry.invalidateGeometryCache,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });

    await port.open();
    moved?.();
    await frames.flushOne();
    expect(host.scaleFactor).toHaveBeenCalledTimes(1);
    expect(host.currentMonitor).toHaveBeenCalledTimes(1);

    await port.close();
    moved?.();
    await frames.flushOne();
    expect(host.scaleFactor).toHaveBeenCalledTimes(2);
    expect(host.currentMonitor).toHaveBeenCalledTimes(2);

    scale = 1.5;
    monitorPhysical = {
      position: { x: 3840, y: 0 },
      size: { width: 1920, height: 1080 },
    };
    // Cache still warm from the post-close move; a fresh monitor read must drop scale.
    geometry.invalidateGeometryCache();
    await geometry.getMonitorForPane();
    await geometry.getPaneOuterPosition();
    expect(host.currentMonitor).toHaveBeenCalledTimes(3);
    expect(host.scaleFactor).toHaveBeenCalledTimes(3);

    port.destroy();
    const afterDestroy = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: geometry.getPaneOuterPosition,
      getMonitorForPane: geometry.getMonitorForPane,
      invalidateGeometryCache: geometry.invalidateGeometryCache,
      getDockWindow: async () => dock,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });
    await afterDestroy.open();
    expect(host.scaleFactor).toHaveBeenCalledTimes(4);
    expect(host.currentMonitor).toHaveBeenCalledTimes(4);
  });

  it("reports fixed Pane logical size when reading pane geometry without querying outerSize", async () => {
    const host = {
      scaleFactor: vi.fn(async () => 2),
      outerPosition: vi.fn(async () => ({ x: 440, y: 1464 })),
      currentMonitor: vi.fn(async () => ({
        position: { x: 0, y: 0 },
        size: { width: 3840, height: 2160 },
      })),
    };
    const geometry = createCachedDockGeometryDeps(host);
    const tileRect = await geometry.getPaneOuterPosition();
    expect(tileRect).toEqual(
      physicalRectToLogical(
        {
          x: 440,
          y: 1464,
          width: PANE_WIDTH * 2,
          height: PANE_HEIGHT * 2,
        },
        2,
      ),
    );
  });

  it("completes open → close → open when tauri://created fires once, calling show on both opens", async () => {
    const { port, createDockWindow, getTauriWindow } = createPortWithWrappedNewWindow();
    await port.open();
    const dock = getTauriWindow()!;
    expect(dock.windowRef.show).toHaveBeenCalledTimes(1);

    await port.close();
    await port.open();
    expect(createDockWindow).toHaveBeenCalledTimes(1);
    expect(dock.windowRef.show).toHaveBeenCalledTimes(2);
  });

  it("reuses the same wrapped window across three open/close cycles", async () => {
    const { port, createDockWindow } = createPortWithWrappedNewWindow();
    for (let cycle = 0; cycle < 3; cycle += 1) {
      await port.open();
      await port.close();
    }
    expect(createDockWindow).toHaveBeenCalledTimes(1);
  });

  it("runs applyPosition before show on the second and third opens after close", async () => {
    const { port, getTauriWindow } = createPortWithWrappedNewWindow();
    const expected = dockRect(pane, monitor);
    await port.open();
    await port.close();

    const tauri = getTauriWindow()!;
    tauri.windowRef.setPosition.mockClear();
    tauri.windowRef.show.mockClear();
    await port.open();
    expect(tauri.windowRef.setPosition.mock.invocationCallOrder[0]!).toBeLessThan(
      tauri.windowRef.show.mock.invocationCallOrder[0]!,
    );
    expect(tauri.windowRef.setPosition).toHaveBeenCalledWith(
      expect.objectContaining({ x: expected.x, y: expected.y }),
    );

    await port.close();
    tauri.windowRef.setPosition.mockClear();
    tauri.windowRef.show.mockClear();
    await port.open();
    expect(tauri.windowRef.setPosition.mock.invocationCallOrder[0]!).toBeLessThan(
      tauri.windowRef.show.mock.invocationCallOrder[0]!,
    );
  });

  it("registers onPaneMoved after a second open and repositions on move", async () => {
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    const { port, getTauriWindow } = createPortWithWrappedNewWindow({
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved: (listener) => {
        moved = listener;
        return () => {};
      },
    });
    await port.open();
    await port.close();
    await port.open();
    const dock = getTauriWindow()!;
    const positionsBefore = dock.windowRef.setPosition.mock.calls.length;
    moved?.();
    await frames.flushOne();
    expect(dock.windowRef.setPosition.mock.calls.length).toBeGreaterThan(positionsBefore);
  });

  it("subscribes to tauri://created only once when ready is called twice on the same wrap", async () => {
    const tauri = createTauriCreatedOnceWindow();
    queueMicrotask(() => {
      tauri.emitCreated();
    });
    const first = tauri.wrapped.ready();
    const second = tauri.wrapped.ready();
    expect(first).toBe(second);
    await expect(first).resolves.toBeUndefined();
    expect(tauri.once.mock.calls.filter(([event]) => event === "tauri://created")).toHaveLength(1);
  });

  it("clears the cached handle when creation fails and recreates on the next open", async () => {
    let attempt = 0;
    const createDockWindow = vi.fn(async () => {
      attempt += 1;
      const tauri = createTauriCreatedOnceWindow();
      if (attempt === 1) {
        queueMicrotask(() => {
          tauri.emitError();
        });
      } else {
        queueMicrotask(() => {
          tauri.emitCreated();
        });
      }
      return tauri.wrapped;
    });
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      createDockWindow,
    });

    await expect(port.open()).resolves.toBeUndefined();
    expect(port.isOpen()).toBe(false);
    expect(createDockWindow).toHaveBeenCalledTimes(1);

    await port.open();
    expect(createDockWindow).toHaveBeenCalledTimes(2);
    expect(port.isOpen()).toBe(true);
  });

  it("does not surface an unhandled rejection when creation fails before ready is awaited", async () => {
    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => {
      unhandled.push(reason);
    };
    process.on("unhandledRejection", onUnhandled);
    try {
      const tauri = createTauriCreatedOnceWindow();
      queueMicrotask(() => {
        tauri.emitError();
      });
      await new Promise((resolve) => {
        setTimeout(resolve, 10);
      });
      expect(unhandled).toEqual([]);
      await expect(tauri.wrapped.ready()).rejects.toThrow("tauri://error");
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });

  it("keeps ready → setPosition → show with one show per open across wrapped reopen cycles", async () => {
    const { port, getTauriWindow } = createPortWithWrappedNewWindow();
    const expected = dockRect(pane, monitor);
    await port.open();
    const dock = getTauriWindow()!;
    expect(dock.windowRef.show).toHaveBeenCalledTimes(1);

    await port.close();
    dock.windowRef.show.mockClear();
    await port.open();
    expect(dock.windowRef.show).toHaveBeenCalledTimes(1);
    expect(dock.windowRef.setPosition).toHaveBeenLastCalledWith(
      expect.objectContaining({ x: expected.x, y: expected.y }),
    );
  });

  it("completes open → close → open while attached, calling show on both opens", async () => {
    const { port, createDockWindow, getTauriWindow } = createPortWithWrappedNewWindow({
      isDockChildAttached: () => true,
    });
    await port.open();
    const dock = getTauriWindow()!;
    expect(dock.windowRef.show).toHaveBeenCalledTimes(1);

    await port.close();
    await port.open();
    expect(createDockWindow).toHaveBeenCalledTimes(1);
    expect(dock.windowRef.show).toHaveBeenCalledTimes(2);
  });

  it("registers onPaneMoved on first open even when the dock is attached as a child window", async () => {
    const dock = mockDockWindow();
    const onPaneMoved = vi.fn(() => () => {});
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      isDockChildAttached: () => true,
      onPaneMoved,
    });

    await port.open();

    expect(onPaneMoved).toHaveBeenCalledOnce();
    expect(dock.callOrder.filter((entry) => entry === "show")).toHaveLength(1);
  });

  it("manual-check: dock-position-only — with child attach, open→close→open still follows pane moves", async () => {
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    let currentPane = { ...pane };
    const dock = mockDockWindow();
    const onPaneMoved = vi.fn((listener: () => void) => {
      moved = listener;
      return vi.fn();
    });
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => ({ ...currentPane }),
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      isDockChildAttached: () => true,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved,
    });

    await port.open();
    await port.close();
    expect(onPaneMoved).toHaveBeenCalledOnce();
    onPaneMoved.mockClear();

    await port.open();
    expect(onPaneMoved).toHaveBeenCalledOnce();

    const movedPane = { ...pane, x: 350 };
    currentPane = movedPane;
    moved?.();
    await frames.flushOne();
    const expected = dockRect(movedPane, monitor);
    expect(dock.callOrder[dock.callOrder.length - 1]).toBe(
      `setPosition:${expected.x},${expected.y}`,
    );
  });

  it("invokes onPaneMoved cleanup on close and registers exactly one listener on the next open", async () => {
    const cleanup = vi.fn();
    const onPaneMoved = vi.fn(() => cleanup);
    const dock = mockDockWindow();
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      onPaneMoved,
    });

    await port.open();
    expect(onPaneMoved).toHaveBeenCalledOnce();

    await port.close();
    expect(cleanup).toHaveBeenCalledOnce();

    onPaneMoved.mockClear();
    await port.open();
    expect(onPaneMoved).toHaveBeenCalledOnce();
  });

  it("repositions the dock on pane move via coalesced onPaneMoved frames", async () => {
    const dock = mockDockWindow();
    const frames = createManualScheduler();
    let moved: (() => void) | undefined;
    const onPaneMoved = vi.fn((listener: () => void) => {
      moved = listener;
      return () => {};
    });
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      isDockChildAttached: () => false,
      scheduleFrame: frames.scheduleFrame,
      onPaneMoved,
    });

    await port.open();
    expect(onPaneMoved).toHaveBeenCalledOnce();
    const positionsBefore = dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length;
    moved?.();
    await frames.flushOne();
    expect(
      dock.callOrder.filter((entry) => entry.startsWith("setPosition")).length,
    ).toBe(positionsBefore + 1);
  });

  it("reposition and syncPositionFromPane still compute from dockRect when attached", async () => {
    const dock = mockDockWindow();
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => dock,
      isDockChildAttached: () => true,
    });

    await port.open();
    dock.callOrder.length = 0;
    const movedPane = { ...pane, x: 400 };
    await port.reposition({ pane: movedPane, monitor });
    const expected = dockRect(movedPane, monitor);
    expect(dock.callOrder).toEqual([`setPosition:${expected.x},${expected.y}`]);

    dock.callOrder.length = 0;
    await port.syncPositionFromPane();
    const synced = dockRect(pane, monitor);
    expect(dock.callOrder).toEqual([`setPosition:${synced.x},${synced.y}`]);
  });

  it("resets child-attach support on destroy so the next Dock create re-probes", async () => {
    const onPaneMoved = vi.fn(() => () => {});
    let dockChildAttachSupported = false;
    let createCount = 0;
    const onDestroy = vi.fn(() => {
      dockChildAttachSupported = false;
    });
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl,
      getPaneOuterPosition: async () => pane,
      getMonitorForPane: async () => monitor,
      getDockWindow: async () => null,
      isDockChildAttached: () => dockChildAttachSupported,
      onDestroy,
      onPaneMoved,
      async createDockWindow() {
        createCount += 1;
        dockChildAttachSupported = false;
        dockChildAttachSupported = true;
        return mockDockWindow();
      },
    });

    await port.open();
    expect(createCount).toBe(1);
    expect(onPaneMoved).toHaveBeenCalledOnce();

    port.destroy();
    expect(onDestroy).toHaveBeenCalledOnce();
    expect(dockChildAttachSupported).toBe(false);

    onPaneMoved.mockClear();
    await port.open();
    expect(createCount).toBe(2);
    expect(dockChildAttachSupported).toBe(true);
    expect(onPaneMoved).toHaveBeenCalledOnce();
  });

  it("does not reparent the Dock webview after create", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "dock-window.ts"),
      "utf8",
    );
    expect(source).not.toMatch(/reparent/);
  });
});

describe("isMacOSPlatform", () => {
  it("detects macOS from platform or userAgent without a Tauri OS plugin", () => {
    expect(isMacOSPlatform({ platform: "MacIntel", userAgent: "Mozilla/5.0" })).toBe(true);
    expect(
      isMacOSPlatform({
        platform: "Win32",
        userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
      }),
    ).toBe(true);
    expect(isMacOSPlatform({ platform: "Win32", userAgent: "Windows NT 10.0" })).toBe(false);
    expect(isMacOSPlatform({ platform: "Linux x86_64", userAgent: "X11; Linux" })).toBe(false);
  });
});

describe("createDockWindowWithOptionalParent", () => {
  class FakeLogicalPosition {
    constructor(
      readonly x: number,
      readonly y: number,
    ) {}
  }

  function fakeHandle(options: {
    emit?: "created" | "error";
    createdOptions?: Record<string, unknown>;
  }): DockWebviewWindowHandle & { options: Record<string, unknown> } {
    const listeners = new Map<string, Array<() => void>>();
    const handle: DockWebviewWindowHandle & { options: Record<string, unknown> } = {
      options: options.createdOptions ?? {},
      show: async () => {},
      hide: async () => {},
      setPosition: async () => {},
      once(event, handler) {
        const list = listeners.get(event) ?? [];
        list.push(handler);
        listeners.set(event, list);
        if (options.emit === "created" && event === "tauri://created") {
          queueMicrotask(() => handler());
        }
        if (options.emit === "error" && event === "tauri://error") {
          queueMicrotask(() => handler());
        }
      },
    };
    return handle;
  }

  it('passes parent: "pane" on macOS and omits it otherwise', async () => {
    const created: Array<Record<string, unknown>> = [];
    const mac = await createDockWindowWithOptionalParent("http://test/?window=dock", {
      isMacOS: () => true,
      LogicalPosition: FakeLogicalPosition,
      createWebviewWindow: (_label, opts) => {
        created.push(opts);
        return fakeHandle({ emit: "created", createdOptions: opts });
      },
    });
    expect(created[0]).toMatchObject({ parent: "pane" });
    expect(mac.childAttached).toBe(true);

    created.length = 0;
    const other = await createDockWindowWithOptionalParent("http://test/?window=dock", {
      isMacOS: () => false,
      LogicalPosition: FakeLogicalPosition,
      createWebviewWindow: (_label, opts) => {
        created.push(opts);
        return fakeHandle({ emit: "created", createdOptions: opts });
      },
    });
    expect(created[0]).not.toHaveProperty("parent");
    expect(other.childAttached).toBe(false);
  });

  it("disables Tauri drag-drop interception so the HTML5 drag-and-drop reaches the page", async () => {
    const created: Array<Record<string, unknown>> = [];
    await createDockWindowWithOptionalParent("http://test/?window=dock", {
      isMacOS: () => true,
      LogicalPosition: FakeLogicalPosition,
      createWebviewWindow: (_label, opts) => {
        created.push(opts);
        return fakeHandle({ emit: "created", createdOptions: opts });
      },
    });
    expect(created[0]).toMatchObject({ dragDropEnabled: false });
  });

  it("recreates without parent when creation with parent rejects, and reports unattached", async () => {
    const created: Array<Record<string, unknown>> = [];
    let attempts = 0;
    const result = await createDockWindowWithOptionalParent("http://test/?window=dock", {
      isMacOS: () => true,
      LogicalPosition: FakeLogicalPosition,
      createWebviewWindow: (_label, opts) => {
        attempts += 1;
        created.push(opts);
        if (attempts === 1) {
          return fakeHandle({ emit: "error", createdOptions: opts });
        }
        return fakeHandle({ emit: "created", createdOptions: opts });
      },
    });

    expect(attempts).toBe(2);
    expect(created[0]).toMatchObject({ parent: "pane" });
    expect(created[1]).not.toHaveProperty("parent");
    expect(result.childAttached).toBe(false);

    const dock = result.window;
    const callOrder: string[] = [];
    const originalShow = dock.show.bind(dock);
    dock.show = async () => {
      callOrder.push("show");
      await originalShow();
    };
    await dock.ready();
    await dock.setPosition(1, 2);
    await dock.show();
    expect(callOrder).toEqual(["show"]);
  });

  it("opens successfully with the throttled listener after a parent-create probe failure", async () => {
    let dockChildAttachSupported = false;
    const onPaneMoved = vi.fn(() => () => {});
    const port = createDockWindowPort({
      isTauri: true,
      dockUrl: "http://test/?window=dock",
      getPaneOuterPosition: async () => ({ x: 220, y: 732, width: 480, height: 112 }),
      getMonitorForPane: async () => ({ x: 0, y: 0, width: 1920, height: 1080 }),
      isDockChildAttached: () => dockChildAttachSupported,
      onDestroy() {
        dockChildAttachSupported = false;
      },
      onPaneMoved,
      async createDockWindow(url) {
        dockChildAttachSupported = false;
        let attempts = 0;
        const result = await createDockWindowWithOptionalParent(url, {
          isMacOS: () => true,
          LogicalPosition: FakeLogicalPosition,
          createWebviewWindow: (_label, opts) => {
            attempts += 1;
            if (attempts === 1) {
              return fakeHandle({ emit: "error", createdOptions: opts });
            }
            return fakeHandle({ emit: "created", createdOptions: opts });
          },
        });
        dockChildAttachSupported = result.childAttached;
        return result.window;
      },
    });

    await port.open();
    expect(port.isOpen()).toBe(true);
    expect(dockChildAttachSupported).toBe(false);
    expect(onPaneMoved).toHaveBeenCalledOnce();
  });

  it("memoises readiness on the wrapped window returned after parent attach", async () => {
    const created = await createDockWindowWithOptionalParent("http://test/?window=dock", {
      isMacOS: () => true,
      LogicalPosition: FakeLogicalPosition,
      createWebviewWindow: (_label, opts) =>
        fakeHandle({ emit: "created", createdOptions: opts }),
    });
    expect(created.childAttached).toBe(true);
    const first = created.window.ready();
    const second = created.window.ready();
    expect(first).toBe(second);
    await expect(first).resolves.toBeUndefined();
  });
});
