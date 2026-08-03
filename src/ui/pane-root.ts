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
  createProductionDockWindowPort,
  type DockWindowPort,
} from "./dock-window";
import { bindPressable } from "./keyboard";
import { createMinePresenter, type MinePresenter } from "./mine-presenter";
import { mountMiningTunnel, type MiningTunnelView } from "./mining-tunnel";
import { startPump, type PumpController, type PumpDeps } from "./pump";

export interface PaneShell {
  startPump(): void;
  stop(): void;
  destroy(): void;
}

export interface PaneShellOptions {
  dockWindow?: DockWindowPort;
  busFactory?: typeof createBusEndpoint;
  deferPump?: boolean;
  now?: () => number;
  session?: MiningSession;
  presenter?: MinePresenter;
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

  let bus: BusEndpoint | null = null;

  const session =
    options.session ??
    createMiningSession({
      now: clockNow,
      onPublish(wire) {
        bus?.publish({ type: "snapshot", snapshot: wire });
      },
    });

  const presenter = options.presenter ?? createMinePresenter(session);

  let tunnel: MiningTunnelView | null = null;
  let autosaveTimer: ReturnType<typeof setInterval> | null = null;
  let lastPublishedAdvance = session.snapshot.advance;
  let lastPublishedOre = session.snapshot.ore;
  let lastPublishedIngots = session.snapshot.ingots;
  let lastPublishedUpgrades = session.snapshot.upgradeCount;

  const pane = document.createElement("div");
  pane.className = "pane";

  const tunnelHost = document.createElement("div");
  tunnelHost.className = "pane-tunnel-host";

  const openDockButton = document.createElement("button");
  openDockButton.type = "button";
  openDockButton.className = "pane-colony-chip";
  openDockButton.dataset["openDock"] = "";
  openDockButton.textContent = "Colony";
  openDockButton.setAttribute("aria-label", "Open Colony Dock");

  pane.append(tunnelHost, openDockButton);
  root.replaceChildren(pane);

  tunnel = mountMiningTunnel(tunnelHost);
  presenter.start();
  tunnel.render(presenter.snapshot());

  function publishSnapshot(): void {
    const wire = session.wireSnapshot();
    bus?.publish({ type: "snapshot", snapshot: wire });
    lastPublishedAdvance = session.snapshot.advance;
    lastPublishedOre = session.snapshot.ore;
    lastPublishedIngots = session.snapshot.ingots;
    lastPublishedUpgrades = session.snapshot.upgradeCount;
  }

  function handleCommand(
    message: Extract<BusMessage, { type: "command" }>,
  ): void {
    if (!isDockCommand(message.command)) {
      return;
    }
    if (message.command.name === "buyUpgrade") {
      const beforeCount = session.snapshot.upgradeCount;
      if (session.tryBuyUpgrade()) {
        // tryBuyUpgrade already publish()es via session onPublish when set;
        // always mirror on the bus for injected sessions without onPublish.
        if (session.snapshot.upgradeCount !== beforeCount) {
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

  bindPressable(openDockButton, () => {
    void dockWindow.toggle().then((opened) => {
      if (opened) {
        bus?.publish({ type: "dock-opened" });
        publishSnapshot();
      } else {
        bus?.publish({ type: "dock-closed" });
      }
    });
  });

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
      snap.upgradeCount !== lastPublishedUpgrades
    ) {
      publishSnapshot();
    }
  }

  function startLivePump(): void {
    if (pump) {
      return;
    }
    const schedule = options.pumpSchedule;
    const pumpOptions: PumpDeps = {
      advanceBy: (ms) => {
        presenter.advanceMs(ms);
        maybePublishEconomy();
        return [];
      },
      onAdvance: () => {},
      render: () => {
        tunnel?.render(presenter.snapshot());
      },
      now: schedule?.now ?? clockNow,
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
    destroy() {
      pump?.stop();
      pump = null;
      if (autosaveTimer) {
        clearInterval(autosaveTimer);
        autosaveTimer = null;
      }
      window.removeEventListener("pagehide", onPageHide);
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
