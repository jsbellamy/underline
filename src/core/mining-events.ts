export type MiningEventType = "swing" | "faceBroken";

export interface MiningEvent {
  readonly type: MiningEventType;
  /** Offset in real (unscaled) ms from the start of the advance window. */
  readonly atMs: number;
}
