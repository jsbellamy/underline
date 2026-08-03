/** Adapted from Nightglass.

Source: nightglass/src/ui/dock-root.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Colony Dock: Snapshot client + buyUpgrade / requestSnapshot commands.
*/

import { SCHEMA_VERSION } from "../core/mining-engine";
import type { WireSnapshot } from "../core/wire-snapshot";
import { createBusEndpoint, isWireSnapshot, type BusEndpoint } from "./bus";
import { mountColonyView, type ColonyView } from "./colony-view";

export interface DockShellOptions {
  busFactory?: typeof createBusEndpoint;
}

export function mountDockShell(
  root: HTMLElement,
  options: DockShellOptions = {},
): { destroy(): void } {
  const shell = document.createElement("div");
  shell.className = "dock-shell";
  root.replaceChildren(shell);

  let colony: ColonyView | null = null;
  let last: WireSnapshot | null = null;

  const bus: BusEndpoint = (options.busFactory ?? createBusEndpoint)({
    snapshot(message) {
      if (!isWireSnapshot(message.snapshot)) {
        return;
      }
      last = message.snapshot;
      colony?.render(message.snapshot);
    },
  });

  colony = mountColonyView(shell, {
    onBuyUpgrade() {
      bus.publish({
        type: "command",
        command: { schemaVersion: SCHEMA_VERSION, name: "buyUpgrade" },
      });
    },
    onDismissOffline() {
      // Dismiss is Dock-local; strip offlineSummary from the last view only.
      if (last) {
        const { offlineSummary: _drop, ...rest } = last;
        last = rest;
        colony?.render(rest);
      }
    },
  });

  bus.publish({ type: "dock-opened" });
  bus.publish({
    type: "command",
    command: { schemaVersion: SCHEMA_VERSION, name: "requestSnapshot" },
  });

  return {
    destroy() {
      bus.publish({ type: "dock-closed" });
      bus.close();
      colony?.destroy();
      colony = null;
      root.replaceChildren();
    },
  };
}
