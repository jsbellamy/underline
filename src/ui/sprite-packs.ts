/** Map `external-sprite-pack/0` relative_path → Vite URL via one character glob. */

import dwarfManifest from "../../assets/characters/dwarf/manifest.json";
import haulerManifest from "../../assets/characters/hauler/manifest.json";
import {
  framePaths,
  type ExternalSpritePack,
} from "../data/external-sprite-pack";

const frameModules = import.meta.glob("../../assets/characters/**/*.png", {
  eager: true,
  import: "default",
}) as Record<string, string>;

const urlByCharacterAndPath = new Map<string, string>();
for (const [modulePath, url] of Object.entries(frameModules)) {
  const marker = "/assets/characters/";
  const at = modulePath.lastIndexOf(marker);
  if (at < 0) {
    continue;
  }
  const key = modulePath.slice(at + marker.length);
  urlByCharacterAndPath.set(key, url);
}

export function frameUrl(character: string, relativePath: string): string {
  const key = `${character}/${relativePath}`;
  const url = urlByCharacterAndPath.get(key);
  if (!url) {
    throw new Error(`No Vite URL for ${character} frame: ${relativePath}`);
  }
  return url;
}

export function frameUrlsFor(
  character: string,
  pack: ExternalSpritePack,
  animationId: string,
  facing: string,
): string[] {
  return framePaths(pack, animationId, facing).map((path) =>
    frameUrl(character, path),
  );
}

export const DWARF_PACK = dwarfManifest as ExternalSpritePack;
export const HAULER_PACK = haulerManifest as ExternalSpritePack;
