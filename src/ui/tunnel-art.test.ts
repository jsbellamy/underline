import { describe, expect, it } from "vitest";
import tunnelManifest from "../assets/tunnel/manifest.json";
import { tunnelArtPath, type TunnelArtPack } from "../data/tunnel-art-pack";
import { TUNNEL_ART_PACK, tunnelArtUrl } from "./tunnel-art";

const pack = tunnelManifest as TunnelArtPack;

describe("tunnel-art", () => {
  it("resolves a manifest relative_path to a Vite URL", () => {
    const relativePath = tunnelArtPath(pack, "background/tunnel-interior");
    const url = tunnelArtUrl(relativePath);
    expect(url.length).toBeGreaterThan(0);
    expect(TUNNEL_ART_PACK.schema).toBe("tunnel-art-pack/0");
  });

  it("throws for an unknown relative path", () => {
    expect(() => tunnelArtUrl("src/assets/tunnel/background/missing.png")).toThrow(
      "No Vite URL for tunnel art: src/assets/tunnel/background/missing.png",
    );
  });
});
