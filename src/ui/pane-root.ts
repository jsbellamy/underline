/** Adapted from Nightglass.

Source: nightglass/src/ui/tile-root.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Empty Pane shell scaffold: Dig Rate line + Tunnel band, Dock toggle via bus.
No mining Engine / combat Battle Tile.
*/

import { createBusEndpoint, type BusEndpoint } from "./bus";
import {
  createProductionDockWindowPort,
  type DockWindowPort,
} from "./dock-window";
import { bindPressable } from "./keyboard";
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

  let bus: BusEndpoint | null = null;

  const pane = document.createElement("div");
  pane.className = "pane";

  const digRateLine = document.createElement("div");
  digRateLine.className = "pane-dig-rate-line";

  const digRateLabel = document.createElement("span");
  digRateLabel.className = "pane-dig-rate-label";
  digRateLabel.textContent = "Dig Rate —";

  const openDockButton = document.createElement("button");
  openDockButton.type = "button";
  openDockButton.className = "pane-open-dock";
  openDockButton.dataset["openDock"] = "";
  openDockButton.textContent = "Colony";
  openDockButton.setAttribute("aria-label", "Open Colony Dock");

  digRateLine.append(digRateLabel, openDockButton);

  const tunnelBand = document.createElement("div");
  tunnelBand.className = "pane-tunnel-band";

  pane.append(digRateLine, tunnelBand);
  root.replaceChildren(pane);

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
      advanceBy: () => [],
      onAdvance: () => {},
      render: () => {},
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
      bus = null;
      root.replaceChildren();
    },
  };
}
