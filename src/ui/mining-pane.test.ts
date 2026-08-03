// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import { dwarfFramePaths, type ExternalSpritePack } from "../data/external-sprite-pack";
import { dwarfFrameUrl, dwarfFrameUrlsFor } from "./dwarf-frames";
import { mountPaneShell } from "./pane-root";
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
});
