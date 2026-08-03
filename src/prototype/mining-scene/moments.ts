/** Shared scene moments — every variant must render each honestly. */

export type SceneMoment = "first-open" | "swinging" | "advance-200" | "ore-backed-up";

export const SCENE_MOMENTS: readonly SceneMoment[] = [
  "first-open",
  "swinging",
  "advance-200",
  "ore-backed-up",
] as const;

export const SCENE_MOMENT_LABELS: Record<SceneMoment, string> = {
  "first-open": "First open — nothing earned",
  swinging: "Swinging the Face",
  "advance-200": "Advance 200 — long Tunnel",
  "ore-backed-up": "Ore backed up at the Smelter",
};

export interface SceneSnapshot {
  moment: SceneMoment;
  advance: number;
  digRate: number;
  ore: number;
  ingots: number;
  hardness: number;
  swingProgress: number;
  anim: "idle" | "swing";
}

export function snapshotFor(moment: SceneMoment): SceneSnapshot {
  switch (moment) {
    case "first-open":
      return {
        moment,
        advance: 0,
        digRate: 1,
        ore: 0,
        ingots: 0,
        hardness: 4,
        swingProgress: 0,
        anim: "idle",
      };
    case "swinging":
      return {
        moment,
        advance: 12,
        digRate: 1.5,
        ore: 8,
        ingots: 3,
        hardness: 4,
        swingProgress: 0.65,
        anim: "swing",
      };
    case "advance-200":
      return {
        moment,
        advance: 200,
        digRate: 4,
        ore: 24,
        ingots: 40,
        hardness: 4,
        swingProgress: 0.2,
        anim: "swing",
      };
    case "ore-backed-up":
      return {
        moment,
        advance: 48,
        digRate: 6,
        ore: 120,
        ingots: 2,
        hardness: 4,
        swingProgress: 0.4,
        anim: "idle",
      };
  }
}
