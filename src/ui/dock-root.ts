/** Adapted from Nightglass.

Source: nightglass/src/ui/dock-root.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Empty Colony Dock shell scaffold. No Management Dock surfaces / combat bus
command wiring yet.
*/

import { createBusEndpoint, type BusEndpoint } from "./bus";

export interface DockShellOptions {
  busFactory?: typeof createBusEndpoint;
}

export function mountDockShell(
  root: HTMLElement,
  options: DockShellOptions = {},
): { destroy(): void } {
  const empty = document.createElement("div");
  empty.className = "dock-empty";
  empty.textContent = "Colony";
  root.replaceChildren(empty);

  const bus: BusEndpoint = (options.busFactory ?? createBusEndpoint)({});
  // Announce ourselves so a future Pane can answer with a Snapshot.
  bus.publish({ type: "dock-opened" });

  return {
    destroy() {
      bus.close();
      root.replaceChildren();
    },
  };
}
