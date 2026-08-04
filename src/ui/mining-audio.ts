/** Domain-event → clip playback for mining Swing and Face break. */

import type { MiningEvent } from "../core/mining-events";
import {
  type AudioClipId,
  type AudioPack,
} from "../data/audio-pack";
import { AUDIO_PACK, audioClipUrlFor } from "./audio-clips";
import { PUMP_INTERVAL_MS } from "./pump";

export const SCHEDULE_LOOKAHEAD_MS = PUMP_INTERVAL_MS;
export const MAX_LIVE_WINDOW_MS = 2 * PUMP_INTERVAL_MS;
export const MIN_RETRIGGER_MS = 60;

interface QueuedCue {
  atMs: number;
  clip: AudioClipId;
}

function clipForEvent(type: MiningEvent["type"]): AudioClipId | null {
  switch (type) {
    case "swing":
      return "swing";
    case "faceBroken":
      return "break";
    case "loadDropped":
      return null;
  }
}

function isContextRunning(context: AudioContext): boolean {
  const state = context.state as string | undefined;
  return state !== "suspended" && state !== "interrupted";
}

export interface MiningAudioDeps {
  createAudioContext: () => AudioContext;
  fetch?: typeof fetch;
  pack?: AudioPack;
  clipUrlFor?: (pack: AudioPack, id: AudioClipId) => string;
}

export interface MiningAudio {
  /** Queues cues from a tick batch, keyed by each event's atMs. Does not play them. */
  handleEvents(
    events: readonly MiningEvent[],
    baseMs: number,
    dtMs: number,
  ): void;
  /** Schedules queued cues on the AudioContext timeline up to the lookahead window. */
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
  const lastScheduledStartSec: Partial<Record<AudioClipId, number>> = {};

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

  function playClip(id: AudioClipId, whenSec: number): void {
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
        source.start(whenSec);
      })
      .catch(() => {});
  }

  function handleEvents(
    events: readonly MiningEvent[],
    baseMs: number,
    dtMs: number,
  ): void {
    if (!enabled) {
      return;
    }
    const minEventAtMs =
      dtMs <= MAX_LIVE_WINDOW_MS ? 0 : dtMs - PUMP_INTERVAL_MS;
    for (const event of events) {
      if (event.atMs < minEventAtMs) {
        continue;
      }
      const clip = clipForEvent(event.type);
      if (clip === null) {
        continue;
      }
      cueQueue.push({
        atMs: baseMs + event.atMs,
        clip,
      });
    }
  }

  function releaseDueTo(nowMs: number): void {
    const scheduleBeforeMs = nowMs + SCHEDULE_LOOKAHEAD_MS;
    const toSchedule: QueuedCue[] = [];
    for (let i = cueQueue.length - 1; i >= 0; i--) {
      const cue = cueQueue[i]!;
      if (cue.atMs <= scheduleBeforeMs) {
        toSchedule.push(cue);
        cueQueue.splice(i, 1);
      }
    }

    if (!enabled || !context) {
      return;
    }

    toSchedule.sort((a, b) => a.atMs - b.atMs);

    if (!isContextRunning(context)) {
      void context.resume?.();
      return;
    }

    const anchor = context.currentTime;

    for (const cue of toSchedule) {
      const whenSec = Math.max(anchor, anchor + (cue.atMs - nowMs) / 1000);
      const lastStart = lastScheduledStartSec[cue.clip];
      if (
        lastStart !== undefined &&
        whenSec - lastStart < MIN_RETRIGGER_MS / 1000
      ) {
        continue;
      }
      lastScheduledStartSec[cue.clip] = whenSec;
      playClip(cue.clip, whenSec);
    }
  }

  return {
    isEnabled() {
      return enabled;
    },
    setEnabled(next: boolean) {
      enabled = next;
      if (next) {
        void ensureLoaded()
          .then(() => {
            void context?.resume?.();
          })
          .catch(() => {});
      } else {
        for (const key of Object.keys(lastScheduledStartSec)) {
          delete lastScheduledStartSec[key as AudioClipId];
        }
      }
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
      for (const key of Object.keys(lastScheduledStartSec)) {
        delete lastScheduledStartSec[key as AudioClipId];
      }
    },
  };
}
