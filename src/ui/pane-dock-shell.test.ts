// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { mountDockShell } from "./dock-root";
import { mountPaneShell, startPaneRoot } from "./pane-root";

describe("mountPaneShell", () => {
  it("mounts Dig Rate line, empty Tunnel band, and an open-dock control", () => {
    const root = document.createElement("main");
    const shell = mountPaneShell(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
    });

    expect(root.querySelector(".pane")).not.toBeNull();
    expect(root.querySelector(".pane-dig-rate-line")).not.toBeNull();
    expect(root.querySelector(".pane-tunnel-band")).not.toBeNull();
    expect(root.querySelector("[data-open-dock]")).not.toBeNull();

    shell.destroy();
  });

  it("toggles the Dock port and publishes dock-opened / dock-closed", async () => {
    const publish = vi.fn();
    const toggle = vi.fn(async () => true);
    const root = document.createElement("main");
    const shell = mountPaneShell(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle,
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish,
        close: vi.fn(),
      }),
    });

    const button = root.querySelector<HTMLButtonElement>("[data-open-dock]");
    expect(button).not.toBeNull();
    button!.click();
    await Promise.resolve();
    await Promise.resolve();

    expect(toggle).toHaveBeenCalledOnce();
    expect(publish).toHaveBeenCalledWith({ type: "dock-opened" });

    toggle.mockResolvedValueOnce(false);
    button!.click();
    await Promise.resolve();
    await Promise.resolve();
    expect(publish).toHaveBeenCalledWith({ type: "dock-closed" });

    shell.destroy();
  });
});

describe("mountDockShell", () => {
  it("mounts an empty Colony placeholder", () => {
    const root = document.createElement("main");
    const shell = mountDockShell(root);
    expect(root.textContent).toContain("Colony");
    expect(root.querySelector(".dock-empty")).not.toBeNull();
    shell.destroy();
  });
});

describe("startPaneRoot", () => {
  it("mounts the empty Pane shell", () => {
    const root = document.createElement("main");
    const result = startPaneRoot(root, {
      dockWindow: {
        open: vi.fn(async () => {}),
        close: vi.fn(async () => {}),
        toggle: vi.fn(async () => true),
        isOpen: () => false,
        reposition: vi.fn(async () => {}),
        syncPositionFromPane: vi.fn(async () => {}),
        destroy: vi.fn(),
      },
      busFactory: () => ({
        publish: vi.fn(),
        close: vi.fn(),
      }),
      deferPump: true,
    });
    expect(root.querySelector(".pane")).not.toBeNull();
    result.dispose();
  });
});
