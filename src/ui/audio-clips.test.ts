import { describe, expect, it } from "vitest";
import audioManifest from "../audio/manifest.json";
import { type AudioPack } from "../data/audio-pack";
import { audioClipUrl, audioClipUrlFor } from "./audio-clips";

describe("audioClipUrl", () => {
  const pack = audioManifest as AudioPack;

  it("resolves every manifest relative_path via the pack glob, not hard-coded URLs", () => {
    for (const clip of pack.clips) {
      const url = audioClipUrl(clip.relative_path);
      expect(url.length).toBeGreaterThan(0);
      expect(audioClipUrlFor(pack, clip.id)).toBe(url);
    }
  });

  it("throws when a relative_path has no resolved Vite URL", () => {
    expect(() => audioClipUrl("missing.wav")).toThrow(/Vite URL/);
  });
});
