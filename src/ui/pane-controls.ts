import { bindPressable } from "./keyboard";

export interface PaneControlsOptions {
  onOpenDock: () => void;
  onQuit: () => void;
}

export interface PaneControlsView {
  root: HTMLElement;
  destroy(): void;
}

export function mountPaneControls(
  host: HTMLElement,
  options: PaneControlsOptions,
): PaneControlsView {
  const cluster = document.createElement("div");
  cluster.className = "pane-controls";

  const colonyChip = document.createElement("button");
  colonyChip.type = "button";
  colonyChip.className = "pane-colony-chip";
  colonyChip.dataset["openDock"] = "";
  colonyChip.textContent = "Colony";
  colonyChip.setAttribute("aria-label", "Open Colony Dock");

  const quitChip = document.createElement("button");
  quitChip.type = "button";
  quitChip.className = "pane-quit-chip";
  quitChip.dataset["quit"] = "";
  quitChip.textContent = "Quit";
  quitChip.setAttribute("aria-label", "Quit Underline");

  cluster.append(colonyChip, quitChip);
  host.append(cluster);

  bindPressable(colonyChip, options.onOpenDock);
  bindPressable(quitChip, options.onQuit);

  return {
    root: cluster,
    destroy() {
      cluster.remove();
    },
  };
}
