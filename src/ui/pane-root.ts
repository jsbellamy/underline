/** Adapted from Nightglass.

Source: nightglass/src/ui/tile-root.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Pane shell: full-band Tunnel with mining Dwarf + Colony chip. Dig Rate chrome
removed per #318. Demo dig loop drives presentation until the Engine (#322).
*/

import { createDemoMineLoop, type DemoMineLoop } from "../core/demo-mine-loop";
import { createBusEndpoint, type BusEndpoint } from "./bus";
import {
  createProductionDockWindowPort,
  type DockWindowPort,
} from "./dock-window";
import { bindPressable } from "./keyboard";
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
  mineLoop?: DemoMineLoop;
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
  const mine = options.mineLoop ?? createDemoMineLoop();

  let bus: BusEndpoint | null = null;
  let tunnel: MiningTunnelView | null = null;

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
  mine.start();
  tunnel.render(mine.snapshot());

  bus = busFactory({
    "dock-closed"() {
      void dockWindow.close();
    },
    "dock-opened"() {
      void dockWindow.open();
    },
  });

  bindPressable(openDockButton, () => {
    void dockWindow.toggle().then((opened) => {
      if (opened) {
        bus?.publish({ type: "dock-opened" });
      } else {
        bus?.publish({ type: "dock-closed" });
      }
    });
  });

  const clockNow = options.now ?? Date.now;
  let pump: PumpController | null = null;

  function startLivePump(): void {
    if (pump) {
      return;
    }
    const schedule = options.pumpSchedule;
    const pumpOptions: PumpDeps = {
      advanceBy: (ms) => {
        mine.advanceMs(ms);
        return [];
      },
      onAdvance: () => {},
      render: () => {
        tunnel?.render(mine.snapshot());
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
      bus?.close();
      dockWindow.destroy();
      tunnel?.destroy();
      tunnel = null;
      bus = null;
      root.replaceChildren();
    },
  };
}
