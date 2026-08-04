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

function tunnelArtEntryWithContentBox(
  pack: TunnelArtPack,
  key: string,
): TunnelArtEntry & { content_box: [number, number, number, number] } {
  const path = tunnelArtPath(pack, key);
  const entry = pack.entries.find((e) => e.relative_path === path);
  if (!entry) {
    throw new Error(`Unknown tunnel art key: ${key}`);
  }
  if (!entry.content_box) {
    throw new Error(`Tunnel art entry missing content_box: ${key}`);
  }
  return entry as TunnelArtEntry & { content_box: [number, number, number, number] };
}

export function tunnelArtContentRadius(pack: TunnelArtPack, key: string): number {
  const entry = tunnelArtEntryWithContentBox(pack, key);
  const [x0, y0, x1, y1] = entry.content_box;
  return (x1 - x0 + 1 + (y1 - y0 + 1)) / 4;
}

export function tunnelArtContentCenter(
  pack: TunnelArtPack,
  key: string,
  canvasSize: number,
): { cx: number; cyFromBottom: number } {
  const entry = tunnelArtEntryWithContentBox(pack, key);
  const [x0, y0, x1, y1] = entry.content_box;
  return {
    cx: (x0 + x1 + 1) / 2,
    cyFromBottom: canvasSize - (y0 + y1 + 1) / 2,
  };
}

export function tunnelArtContentBottomGap(
  pack: TunnelArtPack,
  key: string,
  canvasSize: number,
): number {
  const entry = tunnelArtEntryWithContentBox(pack, key);
  const [, , , y1] = entry.content_box;
  return canvasSize - 1 - y1;
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
