// @vitest-environment happy-dom

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import { browserSaveStore } from "../core/mining-save";
import { createMiningSession } from "../core/mining-session";
import { initialSnapshot } from "../core/mining-engine";
import { persistSettings, SETTINGS_KEY } from "../core/settings-save";
import { createDwarfAnimController } from "../core/dwarf-anim-state";
import {
  dwarfFramePaths,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";
import { dwarfFrameUrl, dwarfFrameUrlsFor } from "./dwarf-frames";
import { mountPaneShell } from "./pane-root";
import { mountMiningTunnel } from "./mining-tunnel";
import { tunnelArtPath } from "../data/tunnel-art-pack";
import { TUNNEL_ART_PACK, tunnelArtUrl } from "./tunnel-art";
import { createMinePresenter } from "./mine-presenter";
import { createMiningAudio } from "./mining-audio";
import type { TunnelSnapshot } from "./mine-presenter";
import { PUMP_INTERVAL_MS } from "./pump";
import {
  DWARF_SCALE,
  PANE_HEIGHT,
  PANE_WIDTH,
  TUNNEL_HEIGHT,
} from "./pane-layout";

function stubPresenter(setSoundEnabled = vi.fn()) {
  const anim = createDwarfAnimController({ digRate: 1 });
  let simNowMs = 0;
  const snapshot = (nowMs?: number): TunnelSnapshot => ({
    animation: "swing" as const,
    facing: "east" as const,
    frameIndex: 0,
    advance: 0,
    faceSwingProgress: 0,
    swingFraction: nowMs !== undefined ? nowMs / 1000 : simNowMs / 1000,
    digRate: 1,
    haulPhase: "none" as const,
    haulProgress: 0,
    faceSlide: 1,
    crewSize: 1,
    heapLoads: 0,
    fallingOre: [],
  });
  return {
    anim,
    get simNowMs() {
      return simNowMs;
    },
    snapshot,
    start: vi.fn(),
    advanceMs: vi.fn((dt: number) => {
      simNowMs += dt;
    }),
    syncDigRate: vi.fn(),
    setSoundEnabled,
    releaseAudioDueTo: vi.fn(),
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
        decodeAudioData: vi.fn(async () => ({}) as AudioBuffer),
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

  it("scales Face damage quarter by Face Hardness at Advance 0 vs 10", () => {
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
      faceSlide: 1,
      crewSize: 1,
      heapLoads: 0,
      fallingOre: [],
    };

    tunnel.render({ ...base, advance: 0 });
    const faceAt0 = host.querySelector<HTMLElement>("[data-face]")!;
    const crackedPath = tunnelArtPath(TUNNEL_ART_PACK, "tiles/face/cracked");
    expect(faceAt0.style.backgroundImage).toBe(
      `url("${tunnelArtUrl(crackedPath)}")`,
    );

    tunnel.render({ ...base, advance: 10 });
    const faceAt10 = host.querySelector<HTMLElement>("[data-face]")!;
    const intactPath = tunnelArtPath(TUNNEL_ART_PACK, "tiles/face/intact");
    expect(faceAt10.style.backgroundImage).toBe(
      `url("${tunnelArtUrl(intactPath)}")`,
    );

    tunnel.destroy();
  });

  describe("presentation clock", () => {
    it("passes 0 to snapshot on the pre-tick mount render", () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const captured: number[] = [];
      const presenter = {
        anim: createDwarfAnimController({ digRate: 1 }),
        simNowMs: 0,
        snapshot(nowMs?: number) {
          captured.push(nowMs ?? this.simNowMs);
          return {
            animation: "swing" as const,
            facing: "east" as const,
            frameIndex: 0,
            advance: 0,
            faceSwingProgress: 0,
            swingFraction: 0,
            digRate: 1,
            haulPhase: "none" as const,
            haulProgress: 0,
            faceSlide: 1,
            crewSize: 1,
            heapLoads: 0,
            fallingOre: [],
          };
        },
        start: vi.fn(),
        advanceMs: vi.fn(),
        syncDigRate: vi.fn(),
        setSoundEnabled: vi.fn(),
        releaseAudioDueTo: vi.fn(),
      };

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      expect(captured[0]).toBe(0);

      shell.destroy();
    });

    it("interpolates 100ms past a tick and clamps at PUMP_INTERVAL_MS", () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const captured: number[] = [];
      const anim = createDwarfAnimController({ digRate: 1 });
      const presenter = {
        anim,
        simNowMs: 0,
        snapshot(nowMs?: number) {
          captured.push(nowMs ?? this.simNowMs);
          return {
            animation: "swing" as const,
            facing: "east" as const,
            frameIndex: 0,
            advance: 0,
            faceSwingProgress: 0,
            swingFraction: 0,
            digRate: 1,
            haulPhase: "none" as const,
            haulProgress: 0,
            faceSlide: 1,
            crewSize: 1,
            heapLoads: 0,
            fallingOre: [],
          };
        },
        start: vi.fn(),
        advanceMs(dt: number) {
          this.simNowMs += dt;
        },
        syncDigRate: vi.fn(),
        setSoundEnabled: vi.fn(),
        releaseAudioDueTo: vi.fn(),
      };

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      shell.startPump();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runIntervals();
      expect(presenter.simNowMs).toBe(PUMP_INTERVAL_MS);

      captured.length = 0;
      pump.setClock(PUMP_INTERVAL_MS + 100);
      pump.runRafAt(PUMP_INTERVAL_MS + 100);
      expect(captured[captured.length - 1]).toBe(100);

      captured.length = 0;
      pump.setClock(PUMP_INTERVAL_MS + 400);
      pump.runRafAt(PUMP_INTERVAL_MS + 400);
      expect(captured[captured.length - 1]).toBe(PUMP_INTERVAL_MS);

      shell.destroy();
    });

    it("does not rewind the presentation clock when a tick lands after a late gap", () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const captured: number[] = [];
      const anim = createDwarfAnimController({ digRate: 1 });
      const presenter = {
        anim,
        simNowMs: 0,
        snapshot(nowMs?: number) {
          captured.push(nowMs ?? this.simNowMs);
          return {
            animation: "swing" as const,
            facing: "east" as const,
            frameIndex: 0,
            advance: 0,
            faceSwingProgress: 0,
            swingFraction: 0,
            digRate: 1,
            haulPhase: "none" as const,
            haulProgress: 0,
            faceSlide: 1,
            crewSize: 1,
            heapLoads: 0,
            fallingOre: [],
          };
        },
        start: vi.fn(),
        advanceMs(dt: number) {
          this.simNowMs += dt;
        },
        syncDigRate: vi.fn(),
        setSoundEnabled: vi.fn(),
        releaseAudioDueTo: vi.fn(),
      };

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      shell.startPump();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runIntervals();

      pump.setClock(PUMP_INTERVAL_MS + 400);
      pump.runRafAt(PUMP_INTERVAL_MS + 400);
      const beforeTick = captured[captured.length - 1]!;

      pump.setClock(PUMP_INTERVAL_MS + 500);
      pump.runIntervals();
      pump.runRafAt(PUMP_INTERVAL_MS + 500);
      const afterTick = captured[captured.length - 1]!;

      expect(afterTick).toBeGreaterThanOrEqual(beforeTick);

      shell.destroy();
    });

    it("calls releaseAudioDueTo with the same presentation clock as snapshot", () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const releaseAudioDueTo = vi.fn();
      const snapshot = vi.fn((_nowMs?: number) => ({
        animation: "swing" as const,
        facing: "east" as const,
        frameIndex: 0,
        advance: 0,
        faceSwingProgress: 0,
        swingFraction: 0,
        digRate: 1,
        haulPhase: "none" as const,
        haulProgress: 0,
        faceSlide: 1,
        crewSize: 1,
        heapLoads: 0,
        fallingOre: [],
      }));
      const presenter = {
        anim: createDwarfAnimController({ digRate: 1 }),
        simNowMs: 0,
        snapshot,
        start: vi.fn(),
        advanceMs(dt: number) {
          this.simNowMs += dt;
        },
        syncDigRate: vi.fn(),
        setSoundEnabled: vi.fn(),
        releaseAudioDueTo,
      };

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      shell.startPump();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runIntervals();

      pump.setClock(PUMP_INTERVAL_MS + 100);
      pump.runRafAt(PUMP_INTERVAL_MS + 100);

      expect(releaseAudioDueTo).toHaveBeenCalled();
      const releaseArg =
        releaseAudioDueTo.mock.calls[
          releaseAudioDueTo.mock.calls.length - 1
        ]![0];
      const snapshotArg =
        snapshot.mock.calls[snapshot.mock.calls.length - 1]![0];
      expect(releaseArg).toBe(snapshotArg);
      expect(releaseArg).toBe(100);

      shell.destroy();
    });

    it("queues cues at or ahead of the lagged presentation clock on the first rAF after a tick", () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const queuedBatches: { baseMs: number; events: { atMs: number }[] }[] =
        [];
      const releaseAudioDueTo = vi.fn();
      const snapshot = vi.fn((_nowMs?: number) => ({
        animation: "swing" as const,
        facing: "east" as const,
        frameIndex: 0,
        advance: 0,
        faceSwingProgress: 0,
        swingFraction: 0,
        digRate: 1,
        haulPhase: "none" as const,
        haulProgress: 0,
        faceSlide: 1,
        crewSize: 1,
        heapLoads: 0,
        fallingOre: [],
      }));
      let simNowMs = 0;
      const presenter = {
        anim: createDwarfAnimController({ digRate: 1 }),
        get simNowMs() {
          return simNowMs;
        },
        snapshot,
        start: vi.fn(),
        advanceMs(dt: number) {
          const baseMs = simNowMs;
          simNowMs += dt;
          queuedBatches.push({
            baseMs,
            events: [{ atMs: dt }],
          });
        },
        syncDigRate: vi.fn(),
        setSoundEnabled: vi.fn(),
        releaseAudioDueTo,
      };

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      shell.startPump();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runIntervals();
      pump.setClock(PUMP_INTERVAL_MS);
      pump.runRafAt(PUMP_INTERVAL_MS);

      const presentationMs =
        snapshot.mock.calls[snapshot.mock.calls.length - 1]![0]!;
      const latestBatch = queuedBatches[queuedBatches.length - 1]!;
      for (const event of latestBatch.events) {
        expect(latestBatch.baseMs + event.atMs).toBeGreaterThanOrEqual(
          presentationMs,
        );
      }

      shell.destroy();
    });

    it("plays a queued swing cue on the first render frame at or after its time", async () => {
      const pump = createPanePumpSchedule();
      const root = document.createElement("main");
      const createAudioContext = stubAudioContextFactory();
      vi.stubGlobal(
        "fetch",
        vi.fn(async () => ({
          ok: true,
          arrayBuffer: async () => new ArrayBuffer(8),
        })),
      );
      const store = browserSaveStore();
      const session = createMiningSession({ store, now: () => 0 });
      const audio = createMiningAudio({ createAudioContext });
      audio.setEnabled(true);
      const presenter = createMinePresenter(session, { audio });

      const shell = mountPaneShell(root, {
        dockWindow: stubDockWindow(),
        busFactory: stubBusFactory(),
        deferPump: true,
        session,
        presenter,
        pumpSchedule: pump.pumpSchedule,
      });

      shell.startPump();
      for (let tick = 1; tick <= 4; tick += 1) {
        pump.setClock(PUMP_INTERVAL_MS * tick);
        pump.runIntervals();
      }

      const source =
        createAudioContext.mock.results[0]!.value.createBufferSource;
      expect(source).not.toHaveBeenCalled();

      pump.setClock(1000);
      pump.runRafAt(1000);
      await vi.waitFor(() => expect(source).toHaveBeenCalled());

      shell.destroy();
      vi.unstubAllGlobals();
    });
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
