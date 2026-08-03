/** Domain-event → clip playback for mining Swing and Face break. */

import {
  type AudioClipId,
  type AudioPack,
} from "../data/audio-pack";
import { AUDIO_PACK, audioClipUrlFor } from "./audio-clips";

export interface MiningAudioDeps {
  createAudioContext: () => AudioContext;
  fetch?: typeof fetch;
  pack?: AudioPack;
  clipUrlFor?: (pack: AudioPack, id: AudioClipId) => string;
}

export interface MiningAudio {
  swing(count: number): void;
  faceBroken(count: number): void;
  setEnabled(enabled: boolean): void;
  isEnabled(): boolean;
  destroy(): void;
}

export function createMiningAudio(deps: MiningAudioDeps): MiningAudio {
  const fetchFn = deps.fetch ?? fetch;
  const pack = deps.pack ?? AUDIO_PACK;
  const clipUrlFor = deps.clipUrlFor ?? audioClipUrlFor;

  let enabled = false;
  let context: AudioContext | null = null;
  const buffers = new Map<AudioClipId, AudioBuffer>();
  let loadPromise: Promise<void> | null = null;

  async function ensureLoaded(): Promise<void> {
    if (loadPromise) {
      return loadPromise;
    }
    if (!context) {
      context = deps.createAudioContext();
    }
    loadPromise = (async () => {
      const ids: AudioClipId[] = ["swing", "break"];
      for (const id of ids) {
        const url = clipUrlFor(pack, id);
        const response = await fetchFn(url);
        if (!response.ok) {
          throw new Error(`Failed to fetch audio clip: ${id}`);
        }
        const data = await response.arrayBuffer();
        const buffer = await context!.decodeAudioData(data);
        buffers.set(id, buffer);
      }
    })();
    return loadPromise;
  }

  function playClip(id: AudioClipId): void {
    if (!enabled || !context) {
      return;
    }
    void ensureLoaded().then(() => {
      const buffer = buffers.get(id);
      if (!buffer || !context) {
        return;
      }
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      source.start();
    });
  }

  return {
    isEnabled() {
      return enabled;
    },
    setEnabled(next: boolean) {
      enabled = next;
      if (next) {
        void ensureLoaded();
      }
    },
    swing(count: number) {
      if (!enabled || count < 1) {
        return;
      }
      if (!context) {
        context = deps.createAudioContext();
      }
      playClip("swing");
    },
    faceBroken(count: number) {
      if (!enabled || count < 1) {
        return;
      }
      if (!context) {
        context = deps.createAudioContext();
      }
      playClip("break");
    },
    destroy() {
      enabled = false;
      void context?.close();
      context = null;
      buffers.clear();
      loadPromise = null;
    },
  };
}
