// @vitest-environment happy-dom

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import { browserSaveStore } from "../core/mining-save";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot } from "../core/mining-engine";
import {
  persistSettings,
  SETTINGS_KEY,
} from "../core/settings-save";
import { createDwarfAnimController } from "../core/dwarf-anim-state";
import { dwarfFramePaths, type ExternalSpritePack } from "../data/external-sprite-pack";
import { dwarfFrameUrl, dwarfFrameUrlsFor } from "./dwarf-frames";
import { mountPaneShell } from "./pane-root";
import { mountMiningTunnel } from "./mining-tunnel";
import type { TunnelSnapshot } from "./mine-presenter";
import { PUMP_INTERVAL_MS } from "./pump";
import { DWARF_SCALE, PANE_HEIGHT, PANE_WIDTH, TUNNEL_HEIGHT } from "./pane-layout";

function stubPresenter(setSoundEnabled = vi.fn()) {
  const anim = createDwarfAnimController({ digRate: 1 });
  const snapshot = (): TunnelSnapshot => ({
      animation: "swing" as const,
      facing: "east" as const,
      frameIndex: 0,
      advance: 0,
      faceSwingProgress: 0,
      swingFraction: 0,
      digRate: 1,
      haulPhase: "none" as const,
      haulProgress: 0,
  });
  return {
    anim,
    snapshot,
    start: vi.fn(),
    advanceMs: vi.fn(),
    syncDigRate: vi.fn(),
    setSoundEnabled,
  };
}

function stubDockWindow() {
  return {
    open: vi.fn(async () => {}),
    close: vi.fn(async () => {}),
    toggle: vi.fn(async () => true),
    isOpen: () => false,
    reposition: vi.fn(async () => {}),
    syncPositionFromPane: vi.fn(async () => {}),
    destroy: vi.fn(),
  };
}

function stubBusFactory() {
  return () => ({
    publish: vi.fn(),
    close: vi.fn(),
  });
}

function stubAudioContextFactory() {
  const createAudioContext = vi.fn(
    () =>
      ({
        decodeAudioData: vi.fn(async () => ({} as AudioBuffer)),
        createBufferSource: vi.fn(() => ({
          connect: vi.fn(),
          start: vi.fn(),
        })),
        destination: {},
        close: vi.fn(),
      }) as unknown as AudioContext,
  );
  vi.stubGlobal(
    "AudioContext",
    vi.fn(function AudioContextStub(this: unknown) {
      return createAudioContext();
    }),
  );
  return createAudioContext;
}

function createPanePumpSchedule() {
  let clock = 0;
  const rafCallbacks: FrameRequestCallback[] = [];
  const intervalCallbacks: Array<() => void> = [];
  let intervalId = 0;
  const doc = {
    hidden: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as Document;

  const pumpSchedule = {
    now: () => clock,
    requestAnimationFrame: (callback: FrameRequestCallback) => {
      rafCallbacks.push(callback);
      return rafCallbacks.length;
    },
    cancelAnimationFrame: vi.fn(),
    setInterval: ((callback: TimerHandler) => {
      const fn = typeof callback === "function" ? callback : () => {};
      intervalCallbacks.push(fn as () => void);
      intervalId += 1;
      return intervalId;
    }) as typeof setInterval,
    clearInterval: vi.fn(),
    document: doc,
  };

  return {
    pumpSchedule,
    setClock(ms: number) {
      clock = ms;
    },
    runIntervals() {
      for (const callback of [...intervalCallbacks]) {
        callback();
      }
    },
    runRafAt(at: number) {
      clock = at;
      const callbacks = rafCallbacks.splice(0);
      for (const callback of callbacks) {
        callback(at);
      }
    },
  };
}

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

  it("scales Face crack progress by Face Hardness at Advance 0 vs 10", () => {
    const host = document.createElement("div");
    const tunnel = mountMiningTunnel(host);
    const base = {
      animation: "swing" as const,
      facing: "east" as const,
      frameIndex: 0,
      faceSwingProgress: 500,
      swingFraction: 0,
      digRate: 1,
      haulPhase: "none" as const,
      haulProgress: 0,
    };

    tunnel.render({ ...base, advance: 0 });
    const crackAt0 = host.querySelector<HTMLElement>(".pane-face-crack");
    expect(crackAt0).not.toBeNull();
    const opacityAt0 = Number(crackAt0!.style.opacity);

    tunnel.render({ ...base, advance: 10 });
    const crackAt10 = host.querySelector<HTMLElement>(".pane-face-crack");
    expect(crackAt10).not.toBeNull();
    const opacityAt10 = Number(crackAt10!.style.opacity);

    // Hardness 1000 vs ≈4045.55773 — same damage, fuller crack on the easier Face.
    expect(opacityAt0).toBeCloseTo(0.625, 5);
    expect(opacityAt10).toBeCloseTo(0.34269, 4);
    expect(opacityAt0).toBeGreaterThan(opacityAt10);

    tunnel.destroy();
  });

  describe("Sound toggle", () => {
    beforeEach(() => {
      window.localStorage.clear();
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => ({
          ok: true,
          arrayBuffer: async () => new ArrayBuffer(8),
        })),
      );
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("toggles sound off to on, persists, calls presenter, and updates the chip in one press", () => {
      const store = browserSaveStore();
      const setSoundEnabled = vi.fn();
      const root = document.createElement("main");
      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter: stubPresenter(setSoundEnabled),
      });

      const sound = root.querySelector<HTMLButtonElement>("[data-sound]")!;
      expect(sound.dataset["soundState"]).toBe("off");

      sound.click();

      const persisted = JSON.parse(store.getItem(SETTINGS_KEY)!);
      expect(persisted.soundEnabled).toBe(true);
      expect(setSoundEnabled).toHaveBeenCalledOnce();
      expect(setSoundEnabled).toHaveBeenCalledWith(true);
      expect(sound.dataset["soundState"]).toBe("on");
      expect(sound.getAttribute("aria-pressed")).toBe("true");
      expect(sound.getAttribute("aria-label")).toBe("Sound on");

      shell.destroy();
    });

    it("renders sound on from persisted settings and constructs audio on mount", () => {
      const createAudioContext = stubAudioContextFactory();
      const store = browserSaveStore();
      persistSettings({ schemaVersion: 1, soundEnabled: true }, store);

      const root = document.createElement("main");
      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
      });

      const sound = root.querySelector<HTMLButtonElement>("[data-sound]")!;
      expect(sound.dataset["soundState"]).toBe("on");
      expect(createAudioContext).toHaveBeenCalled();

      shell.destroy();
    });

    it("renders sound off when no settings key is present", () => {
      const createAudioContext = stubAudioContextFactory();
      const store = browserSaveStore();
      expect(store.getItem(SETTINGS_KEY)).toBeNull();

      const root = document.createElement("main");
      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
      });

      const sound = root.querySelector<HTMLButtonElement>("[data-sound]")!;
      expect(sound.dataset["soundState"]).toBe("off");
      expect(createAudioContext).not.toHaveBeenCalled();

      shell.destroy();
    });

    it("does not construct AudioContext until sound is enabled", () => {
      const createAudioContext = stubAudioContextFactory();
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        pumpSchedule: pump.pumpSchedule,
      });

      expect(createAudioContext).not.toHaveBeenCalled();

      shell.startPump();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runIntervals();
      pump.runRafAt(PUMP_INTERVAL_MS);
      pump.setClock(PUMP_INTERVAL_MS * 2);
      pump.runIntervals();
      pump.runRafAt(PUMP_INTERVAL_MS * 2);

      expect(createAudioContext).not.toHaveBeenCalled();

      const sound = root.querySelector<HTMLButtonElement>("[data-sound]")!;
      sound.click();

      expect(createAudioContext).toHaveBeenCalledTimes(1);

      shell.destroy();
    });
  });
});
