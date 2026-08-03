// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { mountPaneControls } from "./pane-controls";

function press(element: HTMLElement, key: "Enter" | " "): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

describe("mountPaneControls", () => {
  it("returns a root element and destroy that clears the host", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, {
      onOpenDock: vi.fn(),
      onQuit: vi.fn(),
    });

    expect(view.root).toBeInstanceOf(HTMLElement);
    expect(view.root.className).toBe("pane-controls");
    expect(host.contains(view.root)).toBe(true);

    view.destroy();
    expect(host.replaceChildren).toBeDefined();
    expect(host.childElementCount).toBe(0);
  });

  it("renders Colony then Quit chips inside the cluster", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, {
      onOpenDock: vi.fn(),
      onQuit: vi.fn(),
    });

    const cluster = host.querySelector(".pane-controls");
    expect(cluster).not.toBeNull();
    const chips = cluster!.children;
    expect(chips).toHaveLength(2);
    expect(chips[0]!.classList.contains("pane-colony-chip")).toBe(true);
    expect(chips[1]!.classList.contains("pane-quit-chip")).toBe(true);

    view.destroy();
  });

  it("keeps the Colony chip contract", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, {
      onOpenDock: vi.fn(),
      onQuit: vi.fn(),
    });

    const colony = host.querySelector<HTMLButtonElement>("[data-open-dock]");
    expect(colony).not.toBeNull();
    expect(colony!.classList.contains("pane-colony-chip")).toBe(true);
    expect(colony!.textContent).toBe("Colony");
    expect(colony!.getAttribute("aria-label")).toBe("Open Colony Dock");

    view.destroy();
  });

  it("exposes a visible Quit chip with the expected label", () => {
    const host = document.createElement("div");
    const view = mountPaneControls(host, {
      onOpenDock: vi.fn(),
      onQuit: vi.fn(),
    });

    const quit = host.querySelector<HTMLButtonElement>("[data-quit]");
    expect(quit).not.toBeNull();
    expect(quit!.classList.contains("pane-quit-chip")).toBe(true);
    expect(quit!.getAttribute("aria-label")).toBe("Quit Underline");
    expect(quit!.offsetParent).not.toBeNull();

    view.destroy();
  });

  it("activates both chips from click and keyboard", () => {
    const host = document.createElement("div");
    document.body.append(host);
    const onOpenDock = vi.fn();
    const onQuit = vi.fn();
    const view = mountPaneControls(host, { onOpenDock, onQuit });

    const colony = host.querySelector<HTMLButtonElement>("[data-open-dock]")!;
    const quit = host.querySelector<HTMLButtonElement>("[data-quit]")!;

    colony.click();
    expect(onOpenDock).toHaveBeenCalledOnce();

    onOpenDock.mockClear();
    press(colony, "Enter");
    expect(onOpenDock).toHaveBeenCalledOnce();

    onOpenDock.mockClear();
    press(colony, " ");
    expect(onOpenDock).toHaveBeenCalledOnce();

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
