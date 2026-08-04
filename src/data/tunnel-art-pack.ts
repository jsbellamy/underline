/** Read `tunnel-art-pack/0` manifests — pack owns art keys and relative paths. */

const TUNNEL_ASSETS_PREFIX = "src/assets/tunnel/";

export interface TunnelArtEntry {
  relative_path: string;
  sha256: string;
  source_relative_path: string;
  source_sha256: string;
  content_box?: [number, number, number, number];
}

export interface TunnelArtPack {
  schema: string;
  entries: TunnelArtEntry[];
}

function tunnelArtKey(relativePath: string): string {
  if (!relativePath.startsWith(TUNNEL_ASSETS_PREFIX)) {
    throw new Error(`Unexpected tunnel art path: ${relativePath}`);
  }
  const withoutPrefix = relativePath.slice(TUNNEL_ASSETS_PREFIX.length);
  if (!withoutPrefix.endsWith(".png")) {
    throw new Error(`Unexpected tunnel art path: ${relativePath}`);
  }
  return withoutPrefix.slice(0, -".png".length);
}

export function tunnelArtPath(pack: TunnelArtPack, key: string): string {
  for (const entry of pack.entries) {
    if (tunnelArtKey(entry.relative_path) === key) {
      return entry.relative_path;
    }
  }
  throw new Error(`Unknown tunnel art key: ${key}`);
}

export function tunnelArtKeysUnder(pack: TunnelArtPack, prefix: string): string[] {
  const keys: string[] = [];
  for (const entry of pack.entries) {
    const key = tunnelArtKey(entry.relative_path);
    if (key.startsWith(prefix)) {
      keys.push(key);
    }
  }
  if (keys.length === 0) {
    throw new Error(`No tunnel art keys under prefix: ${prefix}`);
  }
  keys.sort();
  return keys;
}
