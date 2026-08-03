/** Adapted from Nightglass.

Source: nightglass/src/main.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Dual-root routing: Pane by default, Dock when `?window=dock`.
Throwaway mining-scene prototype when `?prototype=mining-scene`.
*/

import {
  isMiningScenePrototype,
  mountMiningScenePrototype,
} from "./prototype/mining-scene/mount";
import { mountDockShell } from "./ui/dock-root";
import { startPaneRoot } from "./ui/pane-root";

function isDockWindow(): boolean {
  return new URLSearchParams(window.location.search).get("window") === "dock";
}

window.addEventListener("DOMContentLoaded", () => {
  const paneRoot = document.querySelector<HTMLElement>("#pane");
  const dockRoot = document.querySelector<HTMLElement>("#dock");
  if (!paneRoot || !dockRoot) {
    throw new Error("#pane and #dock root elements are required");
  }

  if (isMiningScenePrototype()) {
    dockRoot.hidden = true;
    paneRoot.hidden = false;
    mountMiningScenePrototype(paneRoot);
    return;
  }

  if (isDockWindow()) {
    document.documentElement.classList.add("dock-window");
    paneRoot.hidden = true;
    dockRoot.hidden = false;
    mountDockShell(dockRoot);
    return;
  }

  dockRoot.hidden = true;
  paneRoot.hidden = false;
  startPaneRoot(paneRoot);
});
