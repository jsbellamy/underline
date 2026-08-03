import { bindPressable } from "./keyboard";

export interface PaneControlsOptions {
  onOpenDock: () => void;
  onQuit: () => void;
  soundEnabled: boolean;
  onToggleSound: (next: boolean) => void;
}

export interface PaneControlsView {
  root: HTMLElement;
  setSoundEnabled(enabled: boolean): void;
  destroy(): void;
}

function applySoundChipState(chip: HTMLButtonElement, enabled: boolean): void {
  chip.setAttribute("aria-pressed", enabled ? "true" : "false");
  chip.dataset["soundState"] = enabled ? "on" : "off";
  chip.setAttribute("aria-label", enabled ? "Sound on" : "Sound off");
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

  const soundChip = document.createElement("button");
  soundChip.type = "button";
  soundChip.className = "pane-sound-chip";
  soundChip.dataset["sound"] = "";
  soundChip.textContent = "Sound";
  applySoundChipState(soundChip, options.soundEnabled);

  const quitChip = document.createElement("button");
  quitChip.type = "button";
  quitChip.className = "pane-quit-chip";
  quitChip.dataset["quit"] = "";
  quitChip.textContent = "Quit";
  quitChip.setAttribute("aria-label", "Quit Underline");

  cluster.append(colonyChip, soundChip, quitChip);
  host.append(cluster);

  bindPressable(colonyChip, options.onOpenDock);
  bindPressable(soundChip, () => {
    const next = soundChip.getAttribute("aria-pressed") !== "true";
    options.onToggleSound(next);
  });
  bindPressable(quitChip, options.onQuit);

  return {
    root: cluster,
    setSoundEnabled(enabled: boolean) {
      applySoundChipState(soundChip, enabled);
    },
    destroy() {
      cluster.remove();
    },
  };
}
