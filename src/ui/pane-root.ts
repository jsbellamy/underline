/** Adapted from Nightglass.

Source: nightglass/src/ui/tile-root.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Pane shell: owns the mining Engine + save, presents the Tunnel, broadcasts
Snapshots to the Dock.
*/

import {
  AUTOSAVE_MS,
  createMiningSession,
  type MiningSession,
} from "../core/mining-session";
import {
  createBusEndpoint,
  isDockCommand,
  type BusEndpoint,
  type BusMessage,
} from "./bus";
import {
  createProductionAppExitPort,
  type AppExitPort,
} from "./app-exit";
import {
  createProductionDockWindowPort,
  type DockWindowPort,
} from "./dock-window";
import {
  createFrameMetrics,
  type FrameMetrics,
  type FrameMetricsReport,
} from "./frame-metrics";
import { browserSaveStore } from "../core/mining-save";
import {
  loadSettings,
  persistSettings,
  type PlayerSettings,
} from "../core/settings-save";
import { createMinePresenter, type MinePresenter } from "./mine-presenter";
import { mountMiningTunnel, type MiningTunnelView } from "./mining-tunnel";
import { mountPaneControls, type PaneControlsView } from "./pane-controls";
import { PUMP_INTERVAL_MS, startPump, type PumpController, type PumpDeps } from "./pump";

export interface PaneShell {
  startPump(): void;
  stop(): void;
  destroy(): void;
  frameMetrics(): FrameMetricsReport | null;
}

export interface PaneShellOptions {
  appExit?: AppExitPort;
  dockWindow?: DockWindowPort;
  busFactory?: typeof createBusEndpoint;
  deferPump?: boolean;
  now?: () => number;
  session?: MiningSession;
  presenter?: MinePresenter;
  frameMetrics?: FrameMetrics;
  pumpSchedule?: Partial<
    Pick<
      PumpDeps,
      | "now"
      | "setInterval"
      | "clearInterval"
      | "requestAnimationFrame"
      | "cancelAnimationFrame"
      | "document"
    >
  >;
}

export interface PaneRootResult {
  shell: PaneShell;
  dispose(): void;
}

export function startPaneRoot(
  root: HTMLElement,
  options: PaneShellOptions = {},
): PaneRootResult {
  const shell = mountPaneShell(root, options);
  return {
    shell,
    dispose() {
      shell.destroy();
    },
  };
}

export function mountPaneShell(
  root: HTMLElement,
  options: PaneShellOptions = {},
): PaneShell {
  const dockWindow = options.dockWindow ?? createProductionDockWindowPort();
  const busFactory = options.busFactory ?? createBusEndpoint;
  const clockNow = options.now ?? Date.now;
  const schedule = options.pumpSchedule;
  const now = schedule?.now ?? clockNow;
  const frameMetrics =
    options.frameMetrics ??
    createFrameMetrics({ now: now });

  let bus: BusEndpoint | null = null;

  const store = browserSaveStore();
  const settings = loadSettings(store);

  const session =
    options.session ??
    createMiningSession({
      store,
      now: clockNow,
      onPublish(wire) {
        bus?.publish({ type: "snapshot", snapshot: wire });
      },
    });

  const appExit = resolveAppExit(options, session);

  const createAudioContext =
    typeof AudioContext !== "undefined"
      ? () => new AudioContext()
      : undefined;

  const presenter =
    options.presenter ??
    createMinePresenter(
      session,
      createAudioContext ? { store, createAudioContext } : {},
    );

  let lastSimNowMs = presenter.simNowMs;
  let lastTickAtMs = now();

  function presentationNowMs(): number {
    const elapsed = Math.max(0, now() - lastTickAtMs);
    return Math.floor(
      lastSimNowMs + Math.min(elapsed, PUMP_INTERVAL_MS),
    );
  }

  let tunnel: MiningTunnelView | null = null;
  let controls: PaneControlsView | null = null;
  let autosaveTimer: ReturnType<typeof setInterval> | null = null;
  let lastPublishedAdvance = session.snapshot.advance;
  let lastPublishedOre = session.snapshot.ore;
  let lastPublishedIngots = session.snapshot.ingots;
  let lastPublishedUpgrades = session.snapshot.digRateUpgradeCount;
  let lastPublishedSmelterUpgrades = session.snapshot.smelterUpgradeCount;
  let lastPublishedBagLoads = session.snapshot.bagLoads;
  let lastPublishedBagOre = session.snapshot.bagOre;
  let lastPublishedCarryCapacityUpgrades =
    session.snapshot.carryCapacityUpgradeCount;

  const pane = document.createElement("div");
  pane.className = "pane";

  const tunnelHost = document.createElement("div");
  tunnelHost.className = "pane-tunnel-host";

  pane.append(tunnelHost);
  root.replaceChildren(pane);

  controls = mountPaneControls(pane, {
    soundEnabled: settings.soundEnabled,
    onOpenDock: () => {
      void dockWindow.toggle().then((opened) => {
        if (opened) {
          bus?.publish({ type: "dock-opened" });
          publishSnapshot();
        } else {
          bus?.publish({ type: "dock-closed" });
        }
      });
    },
    onToggleSound: (next) => {
      const updated: PlayerSettings = { schemaVersion: 1, soundEnabled: next };
      persistSettings(updated, store);
      presenter.setSoundEnabled(next);
      controls?.setSoundEnabled(next);
    },
    onQuit: () => {
      void appExit.exit();
    },
  });

  tunnel = mountMiningTunnel(tunnelHost);
  presenter.start();
  tunnel.render(presenter.snapshot(presentationNowMs()));

  function publishSnapshot(): void {
    const wire = session.wireSnapshot();
    bus?.publish({ type: "snapshot", snapshot: wire });
    lastPublishedAdvance = session.snapshot.advance;
    lastPublishedOre = session.snapshot.ore;
    lastPublishedIngots = session.snapshot.ingots;
    lastPublishedUpgrades = session.snapshot.digRateUpgradeCount;
    lastPublishedSmelterUpgrades = session.snapshot.smelterUpgradeCount;
    lastPublishedBagLoads = session.snapshot.bagLoads;
    lastPublishedBagOre = session.snapshot.bagOre;
    lastPublishedCarryCapacityUpgrades =
      session.snapshot.carryCapacityUpgradeCount;
  }

  function handleCommand(
    message: Extract<BusMessage, { type: "command" }>,
  ): void {
    if (!isDockCommand(message.command)) {
      return;
    }
    if (message.command.name === "buyUpgrade") {
      const beforeDigRate = session.snapshot.digRateUpgradeCount;
      if (session.tryBuyUpgrade(message.command.upgrade)) {
        // tryBuyUpgrade already publish()es via session onPublish when set;
        // always mirror on the bus for injected sessions without onPublish.
        if (
          message.command.upgrade === "digRate" &&
          session.snapshot.digRateUpgradeCount !== beforeDigRate
        ) {
          presenter.syncDigRate();
        }
        publishSnapshot();
      } else {
        publishSnapshot();
      }
      return;
    }
    if (message.command.name === "requestSnapshot") {
      publishSnapshot();
    }
  }

  bus = busFactory({
    "dock-closed"() {
      void dockWindow.close();
    },
    "dock-opened"() {
      void dockWindow.open();
      publishSnapshot();
    },
    command: handleCommand,
  });

  publishSnapshot();

  const onPageHide = (): void => {
    session.persist();
  };
  window.addEventListener("pagehide", onPageHide);

  let pump: PumpController | null = null;

  function maybePublishEconomy(): void {
    const snap = session.snapshot;
    if (
      snap.advance !== lastPublishedAdvance ||
      snap.ore !== lastPublishedOre ||
      snap.ingots !== lastPublishedIngots ||
      snap.digRateUpgradeCount !== lastPublishedUpgrades ||
      snap.smelterUpgradeCount !== lastPublishedSmelterUpgrades ||
      snap.bagLoads !== lastPublishedBagLoads ||
      snap.bagOre !== lastPublishedBagOre ||
      snap.carryCapacityUpgradeCount !== lastPublishedCarryCapacityUpgrades
    ) {
      publishSnapshot();
    }
  }

  function startLivePump(): void {
    if (pump) {
      return;
    }
    const pumpOptions: PumpDeps = {
      advanceBy: (ms) => {
        presenter.advanceMs(ms);
        lastSimNowMs = presenter.simNowMs;
        lastTickAtMs = now();
        maybePublishEconomy();
        return [];
      },
      onAdvance: () => {},
      render: () => {
        const nowMs = presentationNowMs();
        presenter.releaseAudioDueTo(nowMs);
        tunnel?.render(presenter.snapshot(nowMs));
      },
      frameMetrics,
      now: now,
    };
    if (schedule?.setInterval) {
      pumpOptions.setInterval = schedule.setInterval;
    }
    if (schedule?.clearInterval) {
      pumpOptions.clearInterval = schedule.clearInterval;
    }
    if (schedule?.requestAnimationFrame) {
      pumpOptions.requestAnimationFrame = schedule.requestAnimationFrame;
    }
    if (schedule?.cancelAnimationFrame) {
      pumpOptions.cancelAnimationFrame = schedule.cancelAnimationFrame;
    }
    if (schedule?.document) {
      pumpOptions.document = schedule.document;
    }
    pump = startPump(pumpOptions);

    if (!autosaveTimer) {
      autosaveTimer = setInterval(() => {
        session.persist();
      }, AUTOSAVE_MS);
    }
  }

  if (!options.deferPump) {
    startLivePump();
  }

  return {
    startPump: startLivePump,
    stop() {
      pump?.stop();
      pump = null;
    },
    frameMetrics() {
      return pump?.frameMetrics() ?? null;
    },
    destroy() {
      pump?.stop();
      pump = null;
      if (autosaveTimer) {
        clearInterval(autosaveTimer);
        autosaveTimer = null;
      }
      window.removeEventListener("pagehide", onPageHide);
      controls?.destroy();
      controls = null;
      session.persist();
      bus?.close();
      dockWindow.destroy();
      tunnel?.destroy();
      tunnel = null;
      bus = null;
      root.replaceChildren();
    },
  };
}

function resolveAppExit(
  options: PaneShellOptions,
  session: MiningSession,
): AppExitPort {
  if (options.appExit) {
    const injected = options.appExit;
    return {
      async exit() {
        session.persist();
        await injected.exit();
      },
    };
  }
  return createProductionAppExitPort({
    beforeExit: () => session.persist(),
  });
}
