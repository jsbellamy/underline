/** Read `audio-pack/0` manifests — pack owns clip ids and relative paths. */

export type AudioClipId = "swing" | "break";

export interface AudioClipEntry {
  id: AudioClipId;
  relative_path: string;
  sha256: string;
  duration_ms: number;
  sample_rate: number;
  channels: number;
  license: string;
  source_url: string;
  source_title: string;
}

export interface AudioPack {
  schema: string;
  clips: AudioClipEntry[];
}

export function audioClipEntry(pack: AudioPack, id: AudioClipId): AudioClipEntry {
  const clip = pack.clips.find((entry) => entry.id === id);
  if (!clip) {
    throw new Error(`Unknown audio clip: ${id}`);
  }
  return clip;
}
