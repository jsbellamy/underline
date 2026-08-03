import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import audioManifest from "../audio/manifest.json";
import {
  audioClipEntry,
  type AudioClipId,
  type AudioPack,
} from "./audio-pack";
import { audioClipUrl, audioClipUrlFor } from "../ui/audio-clips";

const REQUIRED_CLIP_IDS: AudioClipId[] = ["swing", "break"];
const AUDIO_ROOT = resolve(import.meta.dirname, "../audio");

function sha256Hex(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

describe("audio-pack", () => {
  const pack = audioManifest as AudioPack;

  it("validates the on-disk audio-pack/0 manifest against every clip file", () => {
    expect(pack.schema).toBe("audio-pack/0");

    const clipIds = pack.clips.map((clip) => clip.id);
    for (const id of REQUIRED_CLIP_IDS) {
      expect(clipIds).toContain(id);
    }

    for (const clip of pack.clips) {
      const filePath = resolve(AUDIO_ROOT, clip.relative_path);
      const bytes = readFileSync(filePath);
      expect(sha256Hex(bytes)).toBe(clip.sha256);

      expect(clip.channels).toBe(1);
      expect([22050, 44100]).toContain(clip.sample_rate);
      expect(clip.duration_ms).toBeGreaterThan(0);
      if (clip.id === "swing") {
        expect(clip.duration_ms).toBeLessThanOrEqual(300);
      }
      if (clip.id === "break") {
        expect(clip.duration_ms).toBeLessThanOrEqual(600);
      }

      expect(clip.license.length).toBeGreaterThan(0);
      expect(clip.source_url.length).toBeGreaterThan(0);
      expect(clip.source_title.length).toBeGreaterThan(0);
    }
  });

  it("throws for an unknown clip id", () => {
    expect(() => audioClipEntry(pack, "lunge" as AudioClipId)).toThrow(/clip/);
  });

  it("resolves each manifest relative_path to a Vite URL via glob", () => {
    for (const clip of pack.clips) {
      const url = audioClipUrl(clip.relative_path);
      expect(url.length).toBeGreaterThan(0);
    }
    expect(audioClipUrlFor(pack, "swing")).toBe(audioClipUrl("swing.wav"));
    expect(audioClipUrlFor(pack, "break")).toBe(audioClipUrl("break.wav"));
  });

  it("throws when a relative_path has no resolved Vite URL", () => {
    expect(() => audioClipUrl("missing.wav")).toThrow(/Vite URL/);
  });
});
