/** Pane→Dock wire Snapshot helpers (`docs/research/pane-dock-bus-schema.md`). */

import { SCHEMA_VERSION, type MiningSnapshot } from "./mining-engine";

export interface OfflineSummary {
  offlineMs: number;
  advanceGained: number;
  oreProduced: number;
  oreSmelted: number;
  oreBacklog: number;
}

export interface WireSnapshot {
  schemaVersion: typeof SCHEMA_VERSION;
  advance: number;
  ore: number;
  ingots: number;
  digRateUpgradeCount: number;
  smelterUpgradeCount: number;
  faceSwingProgress: number;
  smelterProgress: number;
  offlineSummary?: OfflineSummary;
}

export function toWireSnapshot(
  snapshot: MiningSnapshot,
  offlineSummary?: OfflineSummary,
): WireSnapshot {
  const wire: WireSnapshot = {
    schemaVersion: SCHEMA_VERSION,
    advance: snapshot.advance,
    ore: snapshot.ore,
    ingots: snapshot.ingots,
    digRateUpgradeCount: snapshot.digRateUpgradeCount,
    smelterUpgradeCount: snapshot.smelterUpgradeCount,
    faceSwingProgress: snapshot.faceSwingProgress,
    smelterProgress: snapshot.smelterProgress,
  };
  if (offlineSummary) {
    wire.offlineSummary = offlineSummary;
  }
  return wire;
}

export function buildOfflineSummary(args: {
  before: MiningSnapshot;
  after: MiningSnapshot;
  offlineMs: number;
}): OfflineSummary {
  const advanceGained = args.after.advance - args.before.advance;
  const oreSmelted = args.after.ingots - args.before.ingots;
  const oreProduced = args.after.ore - args.before.ore + oreSmelted;
  return {
    offlineMs: args.offlineMs,
    advanceGained,
    oreProduced,
    oreSmelted,
    oreBacklog: args.after.ore,
  };
}
