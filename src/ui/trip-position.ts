import {
  HAUL_TRAVEL_MS,
  initialSnapshot,
  unloadMsFor,
} from "../core/mining-engine";
import { tripPhaseFor } from "../core/trip-phase";
import {
  CART_MARK_X,
  HAULER_WALK_PX_PER_MS,
} from "./pane-layout";

export function tripLeftFor(
  haulRemainingMs: number,
  departureStation: number,
  unloadSpeedUpgradeCount: number,
  destinationMark: number = CART_MARK_X,
  returnStation: number = departureStation,
): number {
  const leg =
    tripPhaseFor({
      ...initialSnapshot(),
      haulRemainingMs,
      unloadSpeedUpgradeCount,
    })?.leg ?? "back";
  const unloadMs = unloadMsFor(unloadSpeedUpgradeCount);
  const halfTravel = HAUL_TRAVEL_MS / 2;
  const walkPxPerMs = HAULER_WALK_PX_PER_MS;
  const tripMs = HAUL_TRAVEL_MS + unloadMs;

  if (leg === "out") {
    return Math.max(
      destinationMark,
      Math.round(departureStation - (tripMs - haulRemainingMs) * walkPxPerMs),
    );
  }
  if (leg === "unload") {
    return destinationMark;
  }
  return Math.min(
    returnStation,
    Math.round(destinationMark + (halfTravel - haulRemainingMs) * walkPxPerMs),
  );
}
