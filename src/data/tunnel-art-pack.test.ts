import { describe, expect, it } from "vitest";
import tunnelManifest from "../assets/tunnel/manifest.json";
import {
  tunnelArtKeysUnder,
  tunnelArtPath,
  type TunnelArtPack,
} from "./tunnel-art-pack";

describe("tunnel-art-pack", () => {
  const pack = tunnelManifest as TunnelArtPack;

  it("reads the on-disk tunnel-art-pack/0 manifest", () => {
    expect(pack.schema).toBe("tunnel-art-pack/0");
    expect(pack.entries.length).toBeGreaterThan(0);
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

  it("lists keys under a prefix in ascending lexicographic order", () => {
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
});
