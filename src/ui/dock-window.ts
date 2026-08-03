/** Adapted from Nightglass.

Source: nightglass/src/ui/dock-window.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Adapted for Underline Pane vocabulary (tile → pane). Imports pane-layout.
Colony Dock likely uses click/press; dragDropEnabled retained from Nightglass
until Dock UX is settled.
*/

import { dockRect, type Rect } from "./dock-geometry";
import { DOCK_HEIGHT, DOCK_WIDTH } from "./dock-geometry";
import { PANE_HEIGHT, PANE_WIDTH } from "./pane-layout";
export const DOCK_WINDOW_LABEL = "dock";

export interface MonitorRect extends Rect {}

export interface DockWindowGeometry {
  pane: Rect;
  monitor: MonitorRect;
}

export interface DockWindowPort {
  open(): Promise<void>;
  close(): Promise<void>;
  toggle(): Promise<boolean>;
  isOpen(): boolean;
  reposition(geometry: DockWindowGeometry): Promise<void>;
  syncPositionFromPane(): Promise<void>;
  destroy(): void;
}

export interface DockWindowDeps {
  isTauri?: boolean;
  dockUrl?: string;
  getPaneOuterPosition?: () => Promise<Rect>;
  getMonitorForPane?: () => Promise<MonitorRect>;
  getDockWindow?: () => Promise<DockWebviewWindow | null>;
  createDockWindow?: (url: string) => Promise<DockWebviewWindow>;
  onPaneMoved?: (listener: () => void) => () => void;
  /** When true, macOS creation-time child attach succeeded (stacking hint only; JS still follows on open). */
  isDockChildAttached?: () => boolean;
  /** Called from destroy() so production can reset dockChildAttachSupported. */
  onDestroy?: () => void;
  /** Frame scheduler, injectable so tests can step it. Defaults to requestAnimationFrame. */
  scheduleFrame?: (callback: () => void | Promise<void>) => void;
  /** Clears cached scale-factor / monitor reads. Called from close() and destroy(). */
  invalidateGeometryCache?: () => void;
  /** Snaps the Pane horizontally when dock clamping recenters it. */
  setPanePosition?: (x: number, y: number) => Promise<void>;
}

export interface DockWebviewWindow {
  show(): Promise<void>;
  hide(): Promise<void>;
  setPosition(x: number, y: number): Promise<void>;
  ready(): Promise<void>;
}

export interface DockGeometryHost {
  scaleFactor(): Promise<number>;
  outerPosition(): Promise<{ x: number; y: number }>;
  currentMonitor(): Promise<{
    position: { x: number; y: number };
    size: { width: number; height: number };
  } | null>;
}

export function physicalRectToLogical(rect: Rect, scaleFactor: number): Rect {
  return {
    x: rect.x / scaleFactor,
    y: rect.y / scaleFactor,
    width: rect.width / scaleFactor,
    height: rect.height / scaleFactor,
  };
}

function defaultScheduleFrame(callback: () => void | Promise<void>): void {
  const run = () => {
    void callback();
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(run);
    return;
  }
  queueMicrotask(run);
}

function monitorIdentity(
  monitor: {
    position: { x: number; y: number };
    size: { width: number; height: number };
  } | null,
): string {
  if (!monitor) {
    return "none";
  }
  return `${monitor.position.x},${monitor.position.y},${monitor.size.width},${monitor.size.height}`;
}

/** Cached pane/monitor geometry readers — scale and monitor stay warm mid-drag. */
export function createCachedDockGeometryDeps(host: DockGeometryHost): {
  getPaneOuterPosition: () => Promise<Rect>;
  getMonitorForPane: () => Promise<MonitorRect>;
  invalidateGeometryCache: () => void;
} {
  let scaleFactorCache: number | null = null;
  let monitorCache: MonitorRect | null = null;
  let lastMonitorIdentity: string | null = null;

  async function readScaleFactor(): Promise<number> {
    if (scaleFactorCache != null) {
      return scaleFactorCache;
    }
    scaleFactorCache = await host.scaleFactor();
    return scaleFactorCache;
  }

  return {
    async getPaneOuterPosition() {
      const scaleFactor = await readScaleFactor();
      const position = await host.outerPosition();
      return physicalRectToLogical(
        {
          x: position.x,
          y: position.y,
          width: PANE_WIDTH * scaleFactor,
          height: PANE_HEIGHT * scaleFactor,
        },
        scaleFactor,
      );
    },
    async getMonitorForPane() {
      if (monitorCache) {
        return monitorCache;
      }
      const raw = await host.currentMonitor();
      const identity = monitorIdentity(raw);
      if (lastMonitorIdentity != null && identity !== lastMonitorIdentity) {
        scaleFactorCache = null;
      }
      lastMonitorIdentity = identity;
      const scaleFactor = await readScaleFactor();
      if (!raw) {
        monitorCache = { x: 0, y: 0, width: 1920, height: 1080 };
        return monitorCache;
      }
      monitorCache = physicalRectToLogical(
        {
          x: raw.position.x,
          y: raw.position.y,
          width: raw.size.width,
          height: raw.size.height,
        },
        scaleFactor,
      );
      return monitorCache;
    },
    invalidateGeometryCache() {
      scaleFactorCache = null;
      monitorCache = null;
    },
  };
}

export function createDockWindowPort(deps: DockWindowDeps = {}): DockWindowPort {
  const isTauri = deps.isTauri ?? isTauriRuntime();
  const scheduleFrame = deps.scheduleFrame ?? defaultScheduleFrame;
  let open = false;
  let moveCleanup: (() => void) | null = null;
  let dockWindow: DockWebviewWindow | null = null;
  let pendingMove = false;
  let frameScheduled = false;

  async function ensureDockWindow(): Promise<DockWebviewWindow | null> {
    if (!isTauri) {
      return null;
    }
    if (dockWindow) {
      return dockWindow;
    }
    const existing = deps.getDockWindow ? await deps.getDockWindow() : null;
    if (existing) {
      dockWindow = existing;
      return dockWindow;
    }
    const url = deps.dockUrl ?? `${window.location.origin}${window.location.pathname}?window=dock`;
    dockWindow = deps.createDockWindow ? await deps.createDockWindow(url) : null;
    return dockWindow;
  }

  async function readGeometry(): Promise<DockWindowGeometry | null> {
    if (!deps.getPaneOuterPosition || !deps.getMonitorForPane) {
      return null;
    }
    const pane = await deps.getPaneOuterPosition();
    const monitor = await deps.getMonitorForPane();
    return { pane, monitor };
  }

  async function applyDockPlacement(
    geometry: DockWindowGeometry,
    next: ReturnType<typeof dockRect>,
  ): Promise<void> {
    const windowRef = await ensureDockWindow();
    if (windowRef) {
      await windowRef.setPosition(next.x, next.y);
    }
    if (next.paneX !== geometry.pane.x && deps.setPanePosition) {
      await deps.setPanePosition(next.paneX, geometry.pane.y);
    }
  }

  async function applyPosition(): Promise<void> {
    const geometry = await readGeometry();
    if (!geometry) {
      return;
    }
    const next = dockRect(geometry.pane, geometry.monitor);
    await applyDockPlacement(geometry, next);
  }

  async function runScheduledFrame(): Promise<void> {
    frameScheduled = false;
    if (!pendingMove) {
      return;
    }
    pendingMove = false;
    await applyPosition();
    if (pendingMove) {
      scheduleMoveFrame();
    }
  }

  function scheduleMoveFrame(): void {
    if (frameScheduled) {
      return;
    }
    frameScheduled = true;
    scheduleFrame(() => runScheduledFrame());
  }

  function onPaneMoved(): void {
    pendingMove = true;
    scheduleMoveFrame();
  }

  return {
    async open() {
      if (open) {
        return;
      }
      const windowRef = await ensureDockWindow();
      if (windowRef) {
        try {
          await windowRef.ready();
        } catch {
          dockWindow = null;
          return;
        }
        await applyPosition();
        await windowRef.show();
      }
      open = true;
      if (!moveCleanup && deps.onPaneMoved) {
        moveCleanup = deps.onPaneMoved(() => {
          onPaneMoved();
        });
      }
    },
    async close() {
      if (!open) {
        return;
      }
      const windowRef = await ensureDockWindow();
      if (windowRef) {
        await windowRef.hide();
      }
      open = false;
      deps.invalidateGeometryCache?.();
      moveCleanup?.();
      moveCleanup = null;
    },
    async toggle() {
      if (open) {
        await this.close();
        return false;
      }
      await this.open();
      return true;
    },
    isOpen() {
      return open;
    },
    async reposition(geometry) {
      const next = dockRect(geometry.pane, geometry.monitor);
      await applyDockPlacement(geometry, next);
    },
    async syncPositionFromPane() {
      await applyPosition();
    },
    destroy() {
      moveCleanup?.();
      moveCleanup = null;
      dockWindow = null;
      open = false;
      pendingMove = false;
      frameScheduled = false;
      deps.invalidateGeometryCache?.();
      deps.onDestroy?.();
    },
  };
}

export function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function isMacOSPlatform(
  nav: Pick<Navigator, "platform" | "userAgent"> | undefined =
    typeof navigator !== "undefined" ? navigator : undefined,
): boolean {
  if (!nav) {
    return false;
  }
  return /Mac/i.test(nav.platform) || /Mac OS|Macintosh/i.test(nav.userAgent);
}

export const DOCK_WINDOW_SIZE = {
  width: DOCK_WIDTH,
  height: DOCK_HEIGHT,
} as const;

export interface DockWebviewWindowHandle {
  show(): Promise<void>;
  hide(): Promise<void>;
  setPosition(position: unknown): Promise<void>;
  once(event: string, handler: () => void): void;
}

const DOCK_WEBVIEW_BASE_OPTIONS = {
  width: DOCK_WIDTH,
  height: DOCK_HEIGHT,
  decorations: false,
  transparent: true,
  alwaysOnTop: true,
  resizable: false,
  visible: false,
  focus: true,
  // Retain Nightglass HTML5 DnD opt-out until Colony Dock UX is settled.
  dragDropEnabled: false,
} as const;

export function wrapDockWebviewWindow(
  windowRef: DockWebviewWindowHandle,
  LogicalPosition: new (x: number, y: number) => object,
  options: { awaitCreated: boolean },
): DockWebviewWindow {
  const readinessPromise = options.awaitCreated
    ? new Promise<void>((resolve, reject) => {
        windowRef.once("tauri://created", () => {
          resolve();
        });
        windowRef.once("tauri://error", () => {
          reject(new Error("tauri://error"));
        });
      })
    : null;

  if (readinessPromise) {
    readinessPromise.catch(() => {});
  }

  return {
    show: () => windowRef.show(),
    hide: () => windowRef.hide(),
    setPosition: async (x, y) => {
      await windowRef.setPosition(new LogicalPosition(x, y));
    },
    ready: () => readinessPromise ?? Promise.resolve(),
  };
}

export async function createDockWindowWithOptionalParent(
  url: string,
  deps: {
    isMacOS: () => boolean;
    createWebviewWindow: (label: string, options: Record<string, unknown>) => DockWebviewWindowHandle;
    LogicalPosition: new (x: number, y: number) => object;
  },
): Promise<{ window: DockWebviewWindow; childAttached: boolean }> {
  const baseOptions: Record<string, unknown> = {
    ...DOCK_WEBVIEW_BASE_OPTIONS,
    url,
  };

  async function createWithoutParent(): Promise<DockWebviewWindow> {
    const dock = deps.createWebviewWindow(DOCK_WINDOW_LABEL, { ...baseOptions });
    const wrapped = wrapDockWebviewWindow(dock, deps.LogicalPosition, { awaitCreated: true });
    await wrapped.ready();
    return wrapped;
  }

  if (!deps.isMacOS()) {
    return { window: await createWithoutParent(), childAttached: false };
  }

  try {
    const dock = deps.createWebviewWindow(DOCK_WINDOW_LABEL, {
      ...baseOptions,
      parent: "pane",
    });
    const wrapped = wrapDockWebviewWindow(dock, deps.LogicalPosition, { awaitCreated: true });
    await wrapped.ready();
    return { window: wrapped, childAttached: true };
  } catch {
    return { window: await createWithoutParent(), childAttached: false };
  }
}

export function createProductionDockWindowPort(): DockWindowPort {
  if (!isTauriRuntime()) {
    return createDockWindowPort();
  }

  let dockChildAttachSupported = false;

  const geometry = createCachedDockGeometryDeps({
    async scaleFactor() {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      return getCurrentWindow().scaleFactor();
    },
    async outerPosition() {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const position = await getCurrentWindow().outerPosition();
      return { x: position.x, y: position.y };
    },
    async currentMonitor() {
      const { currentMonitor } = await import("@tauri-apps/api/window");
      const monitor = await currentMonitor();
      if (!monitor) {
        return null;
      }
      return {
        position: { x: monitor.position.x, y: monitor.position.y },
        size: { width: monitor.size.width, height: monitor.size.height },
      };
    },
  });

  return createDockWindowPort({
    isTauri: true,
    dockUrl: `${window.location.origin}${window.location.pathname}?window=dock`,
    getPaneOuterPosition: geometry.getPaneOuterPosition,
    getMonitorForPane: geometry.getMonitorForPane,
    invalidateGeometryCache: geometry.invalidateGeometryCache,
    isDockChildAttached: () => dockChildAttachSupported,
    onDestroy() {
      dockChildAttachSupported = false;
    },
    async getDockWindow() {
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      const { LogicalPosition } = await import("@tauri-apps/api/dpi");
      const existing = await WebviewWindow.getByLabel(DOCK_WINDOW_LABEL);
      if (!existing) {
        return null;
      }
      return wrapDockWebviewWindow(existing, LogicalPosition, { awaitCreated: false });
    },
    async createDockWindow(url) {
      dockChildAttachSupported = false;
      const { WebviewWindow } = await import("@tauri-apps/api/webviewWindow");
      const { LogicalPosition } = await import("@tauri-apps/api/dpi");
      const result = await createDockWindowWithOptionalParent(url, {
        isMacOS: () => isMacOSPlatform(),
        LogicalPosition,
        createWebviewWindow: (label, windowOptions) =>
          new WebviewWindow(label, windowOptions),
      });
      dockChildAttachSupported = result.childAttached;
      return result.window;
    },
    onPaneMoved(listener) {
      let unlisten: (() => void) | null = null;
      void import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        void getCurrentWindow()
          .onMoved(() => {
            listener();
          })
          .then((dispose: () => void) => {
            unlisten = dispose;
          });
      });
      return () => {
        unlisten?.();
      };
    },
    async setPanePosition(x, y) {
      const { getCurrentWindow } = await import("@tauri-apps/api/window");
      const { LogicalPosition } = await import("@tauri-apps/api/dpi");
      await getCurrentWindow().setPosition(new LogicalPosition(x, y));
    },
  });
}
