import { describe, expect, it, vi } from "vitest";
import type { AudioClipId } from "../data/audio-pack";
import type { MiningEvent } from "../core/mining-events";
import { PUMP_INTERVAL_MS } from "./pump";
import { createMiningAudio } from "./mining-audio";

function stubAudioContext(): {
  context: AudioContext;
  createBufferSource: ReturnType<typeof vi.fn>;
} {
  const source = {
    buffer: null as AudioBuffer | null,
    connect: vi.fn(),
    start: vi.fn(),
  };
  const createBufferSource = vi.fn(() => source);
  const context = {
    decodeAudioData: vi.fn(async () => ({} as AudioBuffer)),
    createBufferSource,
    destination: {},
  } as unknown as AudioContext;
  return { context, createBufferSource };
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
  it("starts disabled and ignores swing events until enabled", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    expect(audio.isEnabled()).toBe(false);
    audio.swing(3);
    expect(createAudioContext).not.toHaveBeenCalled();
  });

  it("does not construct AudioContext while disabled", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    audio.swing(3);
    audio.faceBroken(2);

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

  it("starts at most one swing voice when count exceeds 1", async () => {
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

    audio.swing(8);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));

    createBufferSource.mockClear();
    audio.faceBroken(5);
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
    audio.swing(1);
    await vi.waitFor(() =>
      expect(clipUrlFor).toHaveBeenCalledWith(testPack, "swing"),
    );

    clipUrlFor.mockClear();
    audio.faceBroken(1);
    await vi.waitFor(() =>
      expect(clipUrlFor).toHaveBeenCalledWith(testPack, "break"),
    );
  });
});

describe("mining audio cue queue", () => {
  async function enabledAudio() {
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
    return { audio, createBufferSource };
  }

  it("plays a queued swing cue when release time is due", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.handleEvents([{ type: "swing", atMs: 100 }], 1000);
    audio.releaseDueTo(1099);
    expect(createBufferSource).not.toHaveBeenCalled();

    audio.releaseDueTo(1100);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(1));
  });

  it("releases due cues in ascending atMs order and never replays them", async () => {
    const { audio, createBufferSource } = await enabledAudio();
    const events: MiningEvent[] = [
      { type: "faceBroken", atMs: 300 },
      { type: "swing", atMs: 100 },
      { type: "swing", atMs: 200 },
    ];

    audio.handleEvents(events, 1000);
    audio.releaseDueTo(1300);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(3));

    createBufferSource.mockClear();
    audio.releaseDueTo(1300);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("drops cues more than one pump tick overdue without playing them", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.handleEvents([{ type: "swing", atMs: 1000 }], 0);
    audio.releaseDueTo(1000 + PUMP_INTERVAL_MS + 50);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("plays at most four due cues per release and empties the queue", async () => {
    const { audio, createBufferSource } = await enabledAudio();
    const events: MiningEvent[] = Array.from({ length: 6 }, (_, i) => ({
      type: "swing" as const,
      atMs: i * 10,
    }));

    audio.handleEvents(events, 1000);
    audio.releaseDueTo(1100);
    await vi.waitFor(() => expect(createBufferSource).toHaveBeenCalledTimes(4));

    createBufferSource.mockClear();
    audio.releaseDueTo(1200);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("does not queue while muted and does not replay after re-enabling", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.setEnabled(false);
    audio.handleEvents([{ type: "swing", atMs: 0 }], 1000);
    audio.setEnabled(true);
    audio.releaseDueTo(2000);
    expect(createBufferSource).not.toHaveBeenCalled();
  });

  it("drops due queued cues without playing when muted on release", async () => {
    const { audio, createBufferSource } = await enabledAudio();

    audio.handleEvents([{ type: "swing", atMs: 0 }], 1000);
    audio.setEnabled(false);
    audio.releaseDueTo(1100);
    expect(createBufferSource).not.toHaveBeenCalled();

    audio.setEnabled(true);
    audio.releaseDueTo(2000);
    expect(createBufferSource).not.toHaveBeenCalled();
  });
});
