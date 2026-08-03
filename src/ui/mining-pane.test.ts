// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot } from "../core/mining-engine";
import { dwarfFramePaths, type ExternalSpritePack } from "../data/external-sprite-pack";
import { dwarfFrameUrl, dwarfFrameUrlsFor } from "./dwarf-frames";
import { mountPaneShell } from "./pane-root";
import { mountMiningTunnel } from "./mining-tunnel";
import { DWARF_SCALE, PANE_HEIGHT, PANE_WIDTH, TUNNEL_HEIGHT } from "./pane-layout";

describe("dwarfFrameUrl", () => {
  const pack = dwarfManifest as ExternalSpritePack;

  it("resolves every manifest relative_path via the pack glob, not hard-coded URLs", () => {
    for (const animation of ["idle", "swing", "walk"] as const) {
      for (const facing of ["east", "west"] as const) {
        const paths = dwarfFramePaths(pack, animation, facing);
        const urls = dwarfFrameUrlsFor(pack, animation, facing);
        expect(urls).toHaveLength(paths.length);
        for (let i = 0; i < paths.length; i += 1) {
          expect(urls[i]).toBe(dwarfFrameUrl(paths[i]!));
          expect(urls[i]).toMatch(/frame_\d{3}\.png/);
        }
      }
    }
  });
});

describe("mountPaneShell mining Pane", () => {
  it("mounts a full-band Tunnel with Colony chip and a Dwarf sprite at 3×", () => {
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
      deferPump: true,
    });

    expect(root.querySelector(".pane-dig-rate-line")).toBeNull();
    expect(root.querySelector(".pane-tunnel")).not.toBeNull();
    expect(root.querySelector("[data-open-dock]")).not.toBeNull();

    const dwarf = root.querySelector<HTMLImageElement>("[data-dwarf]");
    expect(dwarf).not.toBeNull();
    expect(dwarf!.width).toBe(26 * DWARF_SCALE);
    expect(dwarf!.height).toBe(18 * DWARF_SCALE);
    expect(dwarf!.style.imageRendering).toMatch(/pixelated|crisp-edges/);

    expect(PANE_WIDTH).toBe(480);
    expect(PANE_HEIGHT).toBe(112);
    expect(TUNNEL_HEIGHT).toBe(PANE_HEIGHT);
    expect(DWARF_SCALE).toBe(3);

    shell.destroy();
  });

  it("starts the Dwarf in swing after the demo mine loop begins", () => {
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
      deferPump: true,
    });

    shell.startPump();
    // Pump calls advanceBy once on interval — drive render via shell's mine loop
    // through a direct tick: the dwarf src should be a swing frame after start.
    const dwarf = root.querySelector<HTMLImageElement>("[data-dwarf]");
    expect(dwarf?.getAttribute("data-anim")).toBe("swing");
    expect(dwarf?.src).toMatch(/swing\/east\/frame_/);

    shell.destroy();
  });

  it("persists then exits immediately when Quit is activated once", async () => {
    const root = document.createElement("main");
    const order: string[] = [];
    const store = {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    };
    const session = createMiningSession({
      store,
      now: () => 1_000,
      snapshot: initialSnapshot(),
    });
    const persist = vi.spyOn(session, "persist").mockImplementation(() => {
      order.push("persist");
    });
    const exit = vi.fn(async () => {
      order.push("exit");
    });

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
      deferPump: true,
      session,
      appExit: { exit },
    });

    const quit = root.querySelector<HTMLButtonElement>("[data-quit]");
    expect(quit).not.toBeNull();

    quit!.click();
    await Promise.resolve();

    expect(persist).toHaveBeenCalledOnce();
    expect(exit).toHaveBeenCalledOnce();
    expect(order).toEqual(["persist", "exit"]);
    expect(root.querySelector("[role=dialog]")).toBeNull();

    shell.destroy();
  });

  it("scales Face crack progress by the Hardness band at Advance 24 vs 25", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const base = {
      animation: "swing" as const,
      facing: "east" as const,
      frameIndex: 0,
      faceSwingProgress: 2,
      swingFraction: 0,
      digRate: 1,
    };

    tunnel.render({ ...base, advance: 24 });
    const crackAt24 = host.querySelector<HTMLElement>(".pane-face-crack");
    expect(crackAt24).not.toBeNull();
    const opacityAt24 = Number(crackAt24!.style.opacity);

    tunnel.render({ ...base, advance: 25 });
    const crackAt25 = host.querySelector<HTMLElement>(".pane-face-crack");
    expect(crackAt25).not.toBeNull();
    const opacityAt25 = Number(crackAt25!.style.opacity);

    // Band 0 Hardness 4 vs band 1 Hardness 5 — same Swings, lower crack fill at 25.
    expect(opacityAt24).toBeCloseTo(0.625, 5);
    expect(opacityAt25).toBeCloseTo(0.55, 5);
    expect(opacityAt24).toBeGreaterThan(opacityAt25);

    tunnel.destroy();
  });
});
