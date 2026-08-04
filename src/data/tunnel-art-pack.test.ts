import { describe, expect, it } from "vitest";
import tunnelManifest from "../assets/tunnel/manifest.json";
import {
  tunnelArtPath,
  type TunnelArtPack,
} from "./tunnel-art-pack";

describe("tunnel-art-pack", () => {
  const pack = tunnelManifest as TunnelArtPack;

  it("reads the on-disk tunnel-art-pack/0 manifest", () => {
    expect(pack.schema).toBe("tunnel-art-pack/0");
    expect(pack.entries).toHaveLength(5);
  });

  it("resolves a known key to the manifest relative_path", () => {
    expect(tunnelArtPath(pack, "background/tunnel-interior")).toBe(
      "src/assets/tunnel/background/tunnel-interior.png",
    );
  });

  it("throws for an unknown key", () => {
    expect(() => tunnelArtPath(pack, "background/missing")).toThrow(
      "Unknown tunnel art key: background/missing",
    );
  });
});
