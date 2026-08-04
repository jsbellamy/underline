/** Domain-event → clip playback for mining Swing and Face break. */

import type { MiningEvent } from "../core/mining-events";
import {
  type AudioClipId,
  type AudioPack,
} from "../data/audio-pack";
import { AUDIO_PACK, audioClipUrlFor } from "./audio-clips";
import { PUMP_INTERVAL_MS } from "./pump";

const MAX_CUES_PER_RELEASE = 4;

interface QueuedCue {
  atMs: number;
  clip: AudioClipId;
}

function clipForEvent(type: MiningEvent["type"]): AudioClipId {
  switch (type) {
    case "swing":
      return "swing";
    case "faceBroken":
      return "break";
  }
}

export interface MiningAudioDeps {
  createAudioContext: () => AudioContext;
  fetch?: typeof fetch;
  pack?: AudioPack;
  clipUrlFor?: (pack: AudioPack, id: AudioClipId) => string;
}

export interface MiningAudio {
  swing(count: number): void;
  faceBroken(count: number): void;
  /** Queues cues from a tick batch, keyed by each event's atMs. Does not play them. */
  handleEvents(events: readonly MiningEvent[], baseMs: number): void;
  /** Plays every queued cue with atMs <= nowMs, in atMs order, then drops them. */
  releaseDueTo(nowMs: number): void;
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
  const cueQueue: QueuedCue[] = [];

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
    if (!enabled) {
      return;
    }
    void ensureLoaded()
      .then(() => {
        const buffer = buffers.get(id);
        if (!buffer || !context) {
          return;
        }
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        source.start();
      })
      .catch(() => {});
  }

  function handleEvents(events: readonly MiningEvent[], baseMs: number): void {
    if (!enabled) {
      return;
    }
    for (const event of events) {
      cueQueue.push({
        atMs: baseMs + event.atMs,
        clip: clipForEvent(event.type),
      });
    }
  }

  function releaseDueTo(nowMs: number): void {
    const staleBefore = nowMs - PUMP_INTERVAL_MS;
    for (let i = cueQueue.length - 1; i >= 0; i--) {
      if (cueQueue[i]!.atMs < staleBefore) {
        cueQueue.splice(i, 1);
      }
    }

    const due: QueuedCue[] = [];
    for (let i = cueQueue.length - 1; i >= 0; i--) {
      const cue = cueQueue[i]!;
      if (cue.atMs <= nowMs) {
        due.push(cue);
        cueQueue.splice(i, 1);
      }
    }

    due.sort((a, b) => a.atMs - b.atMs);
    const toPlay = due.slice(0, MAX_CUES_PER_RELEASE);

    for (const cue of toPlay) {
      if (enabled) {
        playClip(cue.clip);
      }
    }
  }

  return {
    isEnabled() {
      return enabled;
    },
    setEnabled(next: boolean) {
      enabled = next;
      if (next) {
        void ensureLoaded().catch(() => {});
      }
    },
    swing(count: number) {
      if (!enabled || count < 1) {
        return;
      }
      playClip("swing");
    },
    faceBroken(count: number) {
      if (!enabled || count < 1) {
        return;
      }
      playClip("break");
    },
    handleEvents,
    releaseDueTo,
    destroy() {
      enabled = false;
      cueQueue.length = 0;
      void context?.close();
      context = null;
      buffers.clear();
      loadPromise = null;
    },
  };
}
