/** Map `audio-pack/0` relative_path → Vite URL via glob (no hard-coded clip paths). */

import audioManifest from "../audio/manifest.json";
import {
  audioClipEntry,
  type AudioClipId,
  type AudioPack,
} from "../data/audio-pack";

const clipModules = import.meta.glob("../audio/*.wav", {
  eager: true,
  import: "default",
}) as Record<string, string>;

const urlByRelativePath = new Map<string, string>();
for (const [modulePath, url] of Object.entries(clipModules)) {
  const marker = "/audio/";
  const at = modulePath.lastIndexOf(marker);
  if (at < 0) {
    continue;
  }
  const relative = modulePath.slice(at + marker.length);
  urlByRelativePath.set(relative, url);
}

export function audioClipUrl(relativePath: string): string {
  const url = urlByRelativePath.get(relativePath);
  if (!url) {
    throw new Error(`No Vite URL for audio clip: ${relativePath}`);
  }
  return url;
}

export function audioClipUrlFor(pack: AudioPack, id: AudioClipId): string {
  return audioClipUrl(audioClipEntry(pack, id).relative_path);
}

export const AUDIO_PACK = audioManifest as AudioPack;
