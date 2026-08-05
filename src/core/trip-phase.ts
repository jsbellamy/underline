import {
  HAUL_TRAVEL_MS,
  haulRoundTripMsFor,
  unloadMsFor,
  type MiningSnapshot,
} from "./mining-engine";

export type TripLeg = "out" | "unload" | "back";

export interface TripPhase {
  readonly leg: TripLeg;
  /** 0 at this leg's start, approaching 1 at its end. */
  readonly legProgress: number;
  /** 0 at Trip start, approaching 1 at round-trip end. */
  readonly tripProgress: number;
}

/** `null` when the Snapshot is not on a Trip (`haulRemainingMs === 0`). */
export function tripPhaseFor(snapshot: MiningSnapshot): TripPhase | null {
  const { haulRemainingMs, unloadSpeedUpgradeCount } = snapshot;
  if (haulRemainingMs === 0) {
    return null;
  }

  const unloadMs = unloadMsFor(unloadSpeedUpgradeCount);
  const halfTravel = HAUL_TRAVEL_MS / 2;
  const roundTripMs = haulRoundTripMsFor(unloadSpeedUpgradeCount);
  const tripProgress = 1 - haulRemainingMs / roundTripMs;

  if (haulRemainingMs > unloadMs + halfTravel) {
    const outLegMs = roundTripMs - (unloadMs + halfTravel);
    const legProgress = (roundTripMs - haulRemainingMs) / outLegMs;
    return { leg: "out", legProgress, tripProgress };
  }
  if (haulRemainingMs > halfTravel) {
    const legProgress = (unloadMs + halfTravel - haulRemainingMs) / unloadMs;
    return { leg: "unload", legProgress, tripProgress };
  }
  const legProgress = (halfTravel - haulRemainingMs) / halfTravel;
  return { leg: "back", legProgress, tripProgress };
}
