import { describe, expect, it, vi } from "vitest";
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

describe("mining audio", () => {
  it("exports swing, faceBroken, setEnabled, isEnabled, and destroy (C1)", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    expect(audio.isEnabled()).toBe(false);
    expect(typeof audio.swing).toBe("function");
    expect(typeof audio.faceBroken).toBe("function");
    expect(typeof audio.setEnabled).toBe("function");
    expect(typeof audio.destroy).toBe("function");
  });

  it("does not construct AudioContext while disabled (C2)", () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const audio = createMiningAudio({ createAudioContext });

    audio.swing(3);
    audio.faceBroken(2);

    expect(createAudioContext).not.toHaveBeenCalled();
  });

  it("constructs AudioContext once on first enable and reuses it (C3)", async () => {
    const createAudioContext = vi.fn(() => stubAudioContext().context);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: {
        schema: "test",
        clips: [
          {
            id: "swing",
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
            id: "break",
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
      },
      clipUrlFor: (_pack, id) => `${id}.wav`,
    });

    audio.setEnabled(true);
    await vi.waitFor(() => expect(createAudioContext).toHaveBeenCalledTimes(1));

    audio.setEnabled(false);
    audio.setEnabled(true);
    expect(createAudioContext).toHaveBeenCalledTimes(1);
  });

  it("starts at most one swing voice when count exceeds 1 (C6)", async () => {
    const { context: ctx, createBufferSource } = stubAudioContext();
    const createAudioContext = vi.fn(() => ctx);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => new ArrayBuffer(8),
    }));
    const audio = createMiningAudio({
      createAudioContext,
      fetch: fetchMock as unknown as typeof fetch,
      pack: {
        schema: "test",
        clips: [
          {
            id: "swing",
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
            id: "break",
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
      },
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
});
