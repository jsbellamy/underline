/** Map `tunnel-art-pack/0` relative_path → Vite URL via glob (no hard-coded art paths). */

import tunnelManifest from "../assets/tunnel/manifest.json";
import type { TunnelArtPack } from "../data/tunnel-art-pack";

const artModules = import.meta.glob("../assets/tunnel/**/*.png", {
  eager: true,
  import: "default",
}) as Record<string, string>;

const urlByRelativePath = new Map<string, string>();
for (const [modulePath, url] of Object.entries(artModules)) {
  const marker = "/assets/tunnel/";
  const at = modulePath.lastIndexOf(marker);
  if (at < 0) {
    continue;
  }
  const relative = `src/assets/tunnel/${modulePath.slice(at + marker.length)}`;
  urlByRelativePath.set(relative, url);
}

export function tunnelArtUrl(relativePath: string): string {
  const url = urlByRelativePath.get(relativePath);
  if (!url) {
    throw new Error(`No Vite URL for tunnel art: ${relativePath}`);
  }
  return url;
}

export const TUNNEL_ART_PACK = tunnelManifest as TunnelArtPack;
