// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { createProductionAppExitPort } from "./app-exit";

describe("AppExitPort", () => {
  it("calls beforeExit to completion before the platform exit on the Tauri path", async () => {
    const order: string[] = [];
    const beforeExit = vi.fn(() => {
      order.push("beforeExit");
    });
    const invoke = vi.fn(async () => {
      order.push("invoke");
    });

    const port = createProductionAppExitPort({
      isTauri: true,
      beforeExit,
      invoke,
    });

    await port.exit();

    expect(beforeExit).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith("quit_app");
    expect(order).toEqual(["beforeExit", "invoke"]);
  });

  it("does not invoke the platform exit when beforeExit throws", async () => {
    const invoke = vi.fn(async () => {});
    const port = createProductionAppExitPort({
      isTauri: true,
      beforeExit: () => {
        throw new Error("save failed");
      },
      invoke,
    });

    await expect(port.exit()).rejects.toThrow("save failed");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("invokes quit_app on the Tauri path", async () => {
    const invoke = vi.fn(async () => {});

    const port = createProductionAppExitPort({
      isTauri: true,
      invoke,
    });

    await port.exit();

    expect(invoke).toHaveBeenCalledOnce();
    expect(invoke).toHaveBeenCalledWith("quit_app");
  });

  it("runs beforeExit and resolves without a platform exit in the browser path", async () => {
    const beforeExit = vi.fn();
    const invoke = vi.fn(async () => {});

    const port = createProductionAppExitPort({
      isTauri: false,
      beforeExit,
      invoke,
    });

    await port.exit();

    expect(beforeExit).toHaveBeenCalledOnce();
    expect(invoke).not.toHaveBeenCalled();
  });

  it("does not throw in the browser path when beforeExit is absent", async () => {
    const port = createProductionAppExitPort({ isTauri: false });
    await expect(port.exit()).resolves.toBeUndefined();
  });
});
