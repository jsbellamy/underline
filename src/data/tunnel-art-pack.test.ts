import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import tunnelManifest from "../assets/tunnel/manifest.json";
import { ORE_SIZE } from "../ui/pane-layout";
import {
  tunnelArtContentBottomGap,
  tunnelArtKeysUnder,
  tunnelArtPath,
  type TunnelArtPack,
} from "./tunnel-art-pack";

describe("tunnel-art-pack", () => {
  const pack = tunnelManifest as TunnelArtPack;

  it("reads the on-disk tunnel-art-pack/0 manifest", () => {
    expect(pack.schema).toBe("tunnel-art-pack/0");
    expect(pack.entries).toHaveLength(26);
  });

  it("resolves a known key to the manifest relative_path", () => {
    expect(tunnelArtPath(pack, "background/tunnel-interior")).toBe(
      "src/assets/tunnel/background/tunnel-interior.png",
    );
    expect(tunnelArtPath(pack, "objects/ore/gold-small")).toBe(
      "src/assets/tunnel/objects/ore/gold-small.png",
    );
  });

  it("throws for an unknown key", () => {
    expect(() => tunnelArtPath(pack, "background/missing")).toThrow(
      "Unknown tunnel art key: background/missing",
    );
  });

  it("lists gold ore keys the Heap may draw in stable order", () => {
    const keys = tunnelArtKeysUnder(pack, "objects/ore/gold-");
    expect(keys).toEqual([
      "objects/ore/gold-large-a",
      "objects/ore/gold-large-b",
      "objects/ore/gold-large-c",
      "objects/ore/gold-medium-a",
      "objects/ore/gold-medium-b",
      "objects/ore/gold-small",
    ]);
  });

  it("filters keys by prefix against mixed tile and object entries", () => {
    const keys = tunnelArtKeysUnder(pack, "tiles/face/");
    expect(keys.every((key) => key.startsWith("tiles/face/"))).toBe(true);
    expect(keys).toEqual([
      "tiles/face/chipped",
      "tiles/face/cracked",
      "tiles/face/crumbling",
      "tiles/face/intact",
    ]);
  });

  it("throws when no keys match the prefix", () => {
    expect(() => tunnelArtKeysUnder(pack, "objects/ore/missing-")).toThrow(
      "No tunnel art keys under prefix: objects/ore/missing-",
    );
  });

  it("binds gold ore object canvases to ORE_SIZE", () => {
    const keys = tunnelArtKeysUnder(pack, "objects/ore/gold-");
    for (const key of keys) {
      const path = tunnelArtPath(pack, key);
      const buf = readFileSync(path);
      const width = buf.readUInt32BE(16);
      const height = buf.readUInt32BE(20);
      expect(width).toBe(ORE_SIZE);
      expect(height).toBe(ORE_SIZE);
    }
  });

  it("throws when content_box is missing for bottom-gap lookup", () => {
    const fixture: TunnelArtPack = {
      schema: "tunnel-art-pack/0",
      entries: [
        {
          relative_path: "src/assets/tunnel/objects/ore/gold-large-a.png",
          sha256: "abc",
          source_relative_path: "assets-raw/tunnel/object-set/gold-large-a.png",
          source_sha256: "def",
        },
      ],
    };
    expect(() =>
      tunnelArtContentBottomGap(fixture, "objects/ore/gold-large-a", ORE_SIZE),
    ).toThrow(
      "Tunnel art entry missing content_box: objects/ore/gold-large-a",
    );
  });
});
