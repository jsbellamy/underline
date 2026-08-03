// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { mountPaneControls } from "./pane-controls";

function press(element: HTMLElement, key: "Enter" | " "): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

function defaultOptions() {
  return {
    onOpenDock: vi.fn(),
    onQuit: vi.fn(),
    soundEnabled: false,
    onToggleSound: vi.fn(),
  };
}

describe("mountPaneControls", () => {
  it("mounting Pane controls leaves the host empty after destroy", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, defaultOptions());

    expect(view.root).toBeInstanceOf(HTMLElement);
    expect(view.root.className).toBe("pane-controls");
    expect(host.contains(view.root)).toBe(true);

    view.destroy();
    expect(host.childElementCount).toBe(0);
  });

  it("renders Colony, Sound, then Quit chips inside the cluster", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, defaultOptions());

    const cluster = host.querySelector(".pane-controls");
    expect(cluster).not.toBeNull();
    const chips = cluster!.children;
    expect(chips).toHaveLength(3);
    expect(chips[0]!.classList.contains("pane-colony-chip")).toBe(true);
    expect(chips[1]!.classList.contains("pane-sound-chip")).toBe(true);
    expect(chips[2]!.classList.contains("pane-quit-chip")).toBe(true);

    view.destroy();
  });

  it("keeps the Colony chip contract", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, defaultOptions());

    const colony = host.querySelector<HTMLButtonElement>("[data-open-dock]");
    expect(colony).not.toBeNull();
    expect(colony!.classList.contains("pane-colony-chip")).toBe(true);
    expect(colony!.textContent).toBe("Colony");
    expect(colony!.getAttribute("aria-label")).toBe("Open Colony Dock");

    view.destroy();
  });

  it("renders the Sound chip off by default with visible affordance", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const view = mountPaneControls(host, defaultOptions());

    const sound = host.querySelector<HTMLButtonElement>("[data-sound]");
    expect(sound).not.toBeNull();
    expect(sound!.classList.contains("pane-sound-chip")).toBe(true);
    expect(sound!.getAttribute("aria-pressed")).toBe("false");
    expect(sound!.dataset["soundState"]).toBe("off");
    expect(sound!.getAttribute("aria-label")).toBe("Sound off");
    expect(sound!.offsetParent).not.toBeNull();

    view.destroy();
    host.remove();
  });

  it("renders the Sound chip on when soundEnabled is true", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, { ...defaultOptions(), soundEnabled: true });

    const sound = host.querySelector<HTMLButtonElement>("[data-sound]");
    expect(sound).not.toBeNull();
    expect(sound!.getAttribute("aria-pressed")).toBe("true");
    expect(sound!.dataset["soundState"]).toBe("on");
    expect(sound!.getAttribute("aria-label")).toBe("Sound on");

    view.destroy();
  });

  it("updates Sound chip state in place via setSoundEnabled", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, defaultOptions());

    view.setSoundEnabled(true);
    const soundOn = host.querySelector<HTMLButtonElement>("[data-sound]")!;
    expect(soundOn.getAttribute("aria-pressed")).toBe("true");
    expect(soundOn.dataset["soundState"]).toBe("on");
    expect(soundOn.getAttribute("aria-label")).toBe("Sound on");

    view.setSoundEnabled(false);
    const soundOff = host.querySelector<HTMLButtonElement>("[data-sound]")!;
    expect(soundOff.getAttribute("aria-pressed")).toBe("false");
    expect(soundOff.dataset["soundState"]).toBe("off");
    expect(soundOff.getAttribute("aria-label")).toBe("Sound off");

    view.destroy();
  });

  it("exposes a visible Quit chip with the expected label", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, defaultOptions());

    const quit = host.querySelector<HTMLButtonElement>("[data-quit]");
    expect(quit).not.toBeNull();
    expect(quit!.classList.contains("pane-quit-chip")).toBe(true);
    expect(quit!.getAttribute("aria-label")).toBe("Quit Underline");
    expect(quit!.offsetParent).not.toBeNull();

    view.destroy();
  });

  it("activates all chips from click and keyboard", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const onOpenDock = vi.fn();
    const onQuit = vi.fn();
    const onToggleSound = vi.fn();
    const view = mountPaneControls(host, {
      onOpenDock,
      onQuit,
      soundEnabled: false,
      onToggleSound,
    });

    const colony = host.querySelector<HTMLButtonElement>("[data-open-dock]")!;
    const sound = host.querySelector<HTMLButtonElement>("[data-sound]")!;
    const quit = host.querySelector<HTMLButtonElement>("[data-quit]")!;

    colony.click();
    expect(onOpenDock).toHaveBeenCalledOnce();

    onOpenDock.mockClear();
    press(colony, "Enter");
    expect(onOpenDock).toHaveBeenCalledOnce();

    onOpenDock.mockClear();
    press(colony, " ");
    expect(onOpenDock).toHaveBeenCalledOnce();

    sound.click();
    expect(onToggleSound).toHaveBeenCalledOnce();
    expect(onToggleSound).toHaveBeenCalledWith(true);

    onToggleSound.mockClear();
    press(sound, "Enter");
    expect(onToggleSound).toHaveBeenCalledOnce();
    expect(onToggleSound).toHaveBeenCalledWith(true);

    onToggleSound.mockClear();
    press(sound, " ");
    expect(onToggleSound).toHaveBeenCalledOnce();
    expect(onToggleSound).toHaveBeenCalledWith(true);

    quit.click();
    expect(onQuit).toHaveBeenCalledOnce();

    onQuit.mockClear();
    press(quit, "Enter");
    expect(onQuit).toHaveBeenCalledOnce();

    onQuit.mockClear();
    press(quit, " ");
    expect(onQuit).toHaveBeenCalledOnce();

    view.destroy();
    host.remove();
  });
});
