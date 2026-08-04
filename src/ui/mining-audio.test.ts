import { describe, expect, it, vi } from "vitest";
import type { AudioClipId } from "../data/audio-pack";
import type { MiningEvent } from "../core/mining-events";
import { PUMP_INTERVAL_MS } from "./pump";
import {
  createMiningAudio,
  MAX_LIVE_WINDOW_MS,
  MIN_RETRIGGER_MS,
  SCHEDULE_LOOKAHEAD_MS,
} from "./mining-audio";

function stubAudioContext(options?: {
  currentTime?: number;
  state?: AudioContextState | undefined;
}): {
  context: AudioContext;
  createBufferSource: ReturnType<typeof vi.fn>;
  resume: ReturnType<typeof vi.fn>;
  source: { start: ReturnType<typeof vi.fn> };
} {
  const source = {
    buffer: null as AudioBuffer | null,
    connect: vi.fn(),
    start: vi.fn(),
  };
  const createBufferSource = vi.fn(() => source);
  const resume = vi.fn(async () => {});
  const context = {
    currentTime: options?.currentTime ?? 0,
    state: options?.state ?? "running",
    resume,
    decodeAudioData: vi.fn(async () => ({} as AudioBuffer)),
    createBufferSource,
    destination: {},
  } as unknown as AudioContext;
  return { context, createBufferSource, resume, source };
}

const testPack = {
  schema: "test",
  clips: [
    {
      id: "swing" as const,
      relative_path: "swing.wav",
      sha256: "",
      duration_ms: 1,
      sample_rate: 44100,
      channels: 1,
      license: "",
      source_url: "",
      source_title: "",
    },
    {
      id: "break" as const,
      relative_path: "break.wav",
      sha256: "",
      duration_ms: 1,
      sample_rate: 44100,
      channels: 1,
      license: "",
      source_url: "",
      source_title: "",
    },
  ],
};

describe("mining audio", () => {
  it("starts disabled and ignores handleEvents until enabled", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    expect(audio.isEnabled()).toBe(false);
    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    audio.releaseDueTo(1000);
    expect(createAudioContext).not.toHaveBeenCalled();
  });

  it("does not construct AudioContext while disabled", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    audio.handleEvents(
      [
        { type: "swing", atMs: 0 },
        { type: "faceBroken", atMs: 100 },
      ],
      0,
      250,
    );
    audio.releaseDueTo(200);

    expect(createAudioContext).not.toHaveBeenCalled();
  });

  it("constructs AudioContext once on first enable and reuses it", async () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });

    audio.setEnabled(true);
    await vi.waitFor(() => expect(createAudioContext).toHaveBeenCalledTimes(1));

    audio.setEnabled(false);
    audio.setEnabled(true);
    expect(createAudioContext).toHaveBeenCalledTimes(1);
  });

  it("starts one swing voice per spaced queued swing cue", async () => {
    const { context: ctx, createBufferSource } = stubAudioContext();
    const createAudioContext = vi.fn(() => ctx);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });

    audio.setEnabled(true);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());

    audio.handleEvents(
      [
        { type: "swing", atMs: 100 },
        { type: "swing", atMs: 100 + MIN_RETRIGGER_MS },
        { type: "swing", atMs: 100 + MIN_RETRIGGER_MS * 2 },
      ],
      0,
      250,
    );
    audio.releaseDueTo(0);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(3));

    createBufferSource.mockClear();
    audio.handleEvents([{ type: "faceBroken", atMs: 0 }], 500, 250);
    audio.releaseDueTo(500);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("selects swing and break clips from the audio pack, not from events", async () => {
    const clipUrlFor = vi.fn((_pack, id: AudioClipId) => `${id}-clip.wav`);
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
      url,
    }));
    const audio = createMiningAudio({
      createAudioContext: vi.fn(() => stubAudioContext().context),
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor,
    });

    audio.setEnabled(true);
    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    await vi.waitFor(() =>
      expect(clipUrlFor).toHaveBeenCalledWith(testPack, "swing"),
    );

    clipUrlFor.mockClear();
    audio.handleEvents([{ type: "faceBroken", atMs: 0 }], 100, 250);
    audio.releaseDueTo(200);
    await vi.waitFor(() =>
      expect(clipUrlFor).toHaveBeenCalledWith(testPack, "break"),
    );
  });

  it("resumes a suspended context on enable", async () => {
    const { context: ctx, resume } = stubAudioContext({
      state: "suspended",
    });
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext: vi.fn(() => ctx),
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });

    audio.setEnabled(true);
    await vi.waitFor(() => expect(resume).toHaveBeenCalled());
  });
});

describe("mining audio cue queue", () => {
  async function enabledAudio(options?: {
    currentTime?: number;
    state?: AudioContextState | undefined;
  }) {
    const stub = stubAudioContext(options);
    const createAudioContext = vi.fn(() => stub.context);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });
    audio.setEnabled(true);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    return {
      audio,
      createBufferSource: stub.createBufferSource,
      resume: stub.resume,
      source: stub.source,
      context: stub.context,
    };
  }

  it("schedules a queued swing cue within the lookahead window", async () => {
    const { audio, createBufferSource } = await enabledAudio({
      currentTime: 5,
    });

    audio.handleEvents([{ type: "swing", atMs: 100 }], 1000, 250);
    audio.releaseDueTo(1099);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("releases due cues in ascending atMs order and never replays them", async () => {
    const swingBuffer = { clip: "swing" } as unknown as AudioBuffer;
    const breakBuffer = { clip: "break" } as unknown as AudioBuffer;
    let decodeIndex = 0;
    const { context: ctx, createBufferSource } = stubAudioContext({
      currentTime: 0,
    });
    ctx.decodeAudioData = vi.fn(async () =>
      decodeIndex++ === 0 ? swingBuffer : breakBuffer,
    );
    const createAudioContext = vi.fn(() => ctx);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: testPack,
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });
    audio.setEnabled(true);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const playOrder: AudioBuffer[] = [];
    createBufferSource.mockImplementation(() => {
      const source = {
        buffer: null as AudioBuffer | null,
        connect: vi.fn(),
        start: vi.fn(() => {
          if (source.buffer) {
            playOrder.push(source.buffer);
          }
        }),
      };
      return source;
    });

    const events: MiningEvent[] = [
      { type: "swing", atMs: 100 },
      { type: "swing", atMs: 100 + MIN_RETRIGGER_MS },
      { type: "faceBroken", atMs: 100 + MIN_RETRIGGER_MS * 2 },
    ];

    audio.handleEvents(events, 0, 250);
    audio.releaseDueTo(0);
    await vi.waitFor(() => expect(playOrder).toHaveLength(3));
    expect(playOrder).toEqual([swingBuffer, swingBuffer, breakBuffer]);

    createBufferSource.mockClear();
    audio.releaseDueTo(0);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("schedules a cue left overdue across many pump intervals without discarding it", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, PUMP_INTERVAL_MS);
    audio.releaseDueTo(PUMP_INTERVAL_MS * 5);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("schedules cues on the AudioContext timeline at explicit start times", async () => {
    const { audio, createBufferSource, source } = await enabledAudio({
      currentTime: 5,
    });

    audio.handleEvents(
      [
        { type: "swing", atMs: 1000 },
        { type: "swing", atMs: 1200 },
        { type: "faceBroken", atMs: 1240 },
      ],
      0,
      250,
    );
    audio.releaseDueTo(1000);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(3));

    expect(source.start).toHaveBeenNthCalledWith(1, 5);
    expect(source.start).toHaveBeenNthCalledWith(2, 5.2);
    expect(source.start).toHaveBeenNthCalledWith(3, 5.24);

    createBufferSource.mockClear();
    source.start.mockClear();
    audio.handleEvents([{ type: "faceBroken", atMs: 1240 }], 0, 250);
    audio.releaseDueTo(1000);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("queues only the final pump tick of a long catch-up window", async () => {
    const catchUpMs = 60_000;
    const events: MiningEvent[] = [
      { type: "swing", atMs: 0 },
      { type: "faceBroken", atMs: catchUpMs - PUMP_INTERVAL_MS },
      { type: "swing", atMs: catchUpMs - 1 },
    ];

    const { audio: catchUpAudio, createBufferSource: catchUpSources } =
      await enabledAudio();
    catchUpAudio.handleEvents(events, 0, catchUpMs);
    catchUpAudio.releaseDueTo(catchUpMs - PUMP_INTERVAL_MS);
    catchUpAudio.releaseDueTo(catchUpMs - 1);
    await vi.waitFor(() => expect(catchUpSources).toHaveBeenCalledTimes(2));

    const { audio: liveAudio, createBufferSource: liveSources } =
      await enabledAudio();
    liveAudio.handleEvents(events, 0, PUMP_INTERVAL_MS);
    liveAudio.releaseDueTo(0);
    liveAudio.releaseDueTo(catchUpMs - PUMP_INTERVAL_MS);
    liveAudio.releaseDueTo(catchUpMs - 1);
    await vi.waitFor(() => expect(liveSources).toHaveBeenCalledTimes(3));
  });

  it("suppresses same-clip cues within MIN_RETRIGGER_MS but not different clips", async () => {
    const { audio, createBufferSource } = await enabledAudio({
      currentTime: 0,
    });

    audio.handleEvents(
      [
        { type: "swing", atMs: 0 },
        { type: "swing", atMs: 20 },
      ],
      0,
      250,
    );
    audio.releaseDueTo(20);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));

    const { audio: audio2, createBufferSource: sources2 } = await enabledAudio({
      currentTime: 0,
    });
    audio2.handleEvents(
      [
        { type: "swing", atMs: 0 },
        { type: "faceBroken", atMs: 20 },
      ],
      0,
      250,
    );
    audio2.releaseDueTo(20);
    await vi.waitFor(() => expect(sources2).toHaveBeenCalledTimes(2));
  });

  it("passes an explicit numeric argument to every start call", async () => {
    const { audio, source } = await enabledAudio({ currentTime: 3 });

    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    audio.releaseDueTo(0);
    await vi.waitFor(() => expect(source.start).toHaveBeenCalled());

    for (const call of source.start.mock.calls) {
      expect(typeof call[0]).toBe("number");
    }
  });

  it("resumes and discards due cues when context is suspended", async () => {
    const { audio, createBufferSource, resume } = await enabledAudio({
      state: "suspended",
    });

    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    audio.releaseDueTo(0);
    expect(resume).toHaveBeenCalled();
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("schedules cues when context is running", async () => {
    const { audio, createBufferSource } = await enabledAudio({
      state: "running",
    });

    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    audio.releaseDueTo(0);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("schedules cues when context state is undefined", async () => {
    const { audio, createBufferSource, context } = await enabledAudio();
    Object.defineProperty(context, "state", { value: undefined });

    audio.handleEvents([{ type: "swing", atMs: 0 }], 0, 250);
    audio.releaseDueTo(0);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("does not queue while muted and does not replay after re-enabling", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.setEnabled(false);
    audio.handleEvents([{ type: "swing", atMs: 0 }], 1000, 250);
    audio.setEnabled(true);
    audio.releaseDueTo(2000);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("drops due queued cues without playing when muted on release", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.handleEvents([{ type: "swing", atMs: 0 }], 1000, 250);
    audio.setEnabled(false);
    audio.releaseDueTo(1100);
    expect(createBufferSource).not.toHaveBeenCalled();

    audio.setEnabled(true);
    audio.releaseDueTo(2000);
    expect(createBufferSource).not.toHaveBeenCalled();
  });
});

describe("mining audio constants", () => {
  it("derives schedule lookahead and live window from pump interval", () => {
    expect(SCHEDULE_LOOKAHEAD_MS).toBe(PUMP_INTERVAL_MS);
    expect(MAX_LIVE_WINDOW_MS).toBe(2 * PUMP_INTERVAL_MS);
    expect(MIN_RETRIGGER_MS).toBe(60);
  });
});
