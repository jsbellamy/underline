/** Vendored from Nightglass.

Source: nightglass/src/ui/frame-metrics.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit this copy in place.
*/

export const FRAME_METRICS_WINDOW = 120;

export type TickPhase = "advance" | "applyEvents" | "legality" | "publish";

export interface DurationStats {
  p50Ms: number;
  p95Ms: number;
  maxMs: number;
}

export interface FrameSample {
  /** Wall-clock ms since the previous render started. */
  intervalMs: number;
  /** Wall-clock ms the render callback itself took. */
  durationMs: number;
}

export interface FrameMetricsReport {
  sampleCount: number;
  intervalP50Ms: number;
  intervalP95Ms: number;
  intervalMaxMs: number;
  durationP50Ms: number;
  durationP95Ms: number;
  durationMaxMs: number;
  tickSampleCount: number;
  tickTotal: DurationStats;
  tickPhases: Record<TickPhase, DurationStats>;
}

export interface FrameMetrics {
  /** Wraps `render`; records interval since last call and the call's duration. */
  measure(render: () => void): void;
  /** Wraps one whole sim tick; records total tick duration. */
  measureTick(tick: () => void): void;
  /** Times `fn` under `phase` and returns its result. Call inside `measureTick`. */
  time<T>(phase: TickPhase, fn: () => T): T;
  report(): FrameMetricsReport;
  reset(): void;
}

export interface FrameMetricsDeps {
  now?: () => number;
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const len = sorted.length;
  return sorted[Math.min(len - 1, Math.ceil(p * len) - 1)]!;
}

function durationStats(samples: number[]): DurationStats {
  return {
    p50Ms: percentile(samples, 0.5),
    p95Ms: percentile(samples, 0.95),
    maxMs: samples.length === 0 ? 0 : Math.max(...samples),
  };
}

function pushRolling(samples: number[], value: number): void {
  samples.push(value);
  if (samples.length > FRAME_METRICS_WINDOW) {
    samples.shift();
  }
}

const TICK_PHASES: TickPhase[] = [
  "advance",
  "applyEvents",
  "legality",
  "publish",
];

export function createFrameMetrics(deps?: FrameMetricsDeps): FrameMetrics {
  const now = deps?.now ?? performance.now.bind(performance);
  const durationSamples: number[] = [];
  const intervalSamples: number[] = [];
  const tickTotalSamples: number[] = [];
  const phaseSamples: Record<TickPhase, number[]> = {
    advance: [],
    applyEvents: [],
    legality: [],
    publish: [],
  };
  let lastRenderStartMs: number | null = null;

  function measure(render: () => void): void {
    const startMs = now();
    if (lastRenderStartMs !== null) {
      pushRolling(intervalSamples, startMs - lastRenderStartMs);
    }
    lastRenderStartMs = startMs;
    try {
      render();
    } finally {
      pushRolling(durationSamples, now() - startMs);
    }
  }

  function measureTick(tick: () => void): void {
    const startMs = now();
    try {
      tick();
    } finally {
      pushRolling(tickTotalSamples, now() - startMs);
    }
  }

  function time<T>(phase: TickPhase, fn: () => T): T {
    const startMs = now();
    try {
      return fn();
    } finally {
      pushRolling(phaseSamples[phase], now() - startMs);
    }
  }

  function report(): FrameMetricsReport {
    const tickPhases = {} as Record<TickPhase, DurationStats>;
    for (const phase of TICK_PHASES) {
      tickPhases[phase] = durationStats(phaseSamples[phase]);
    }
    return {
      sampleCount: durationSamples.length,
      intervalP50Ms: percentile(intervalSamples, 0.5),
      intervalP95Ms: percentile(intervalSamples, 0.95),
      intervalMaxMs:
        intervalSamples.length === 0 ? 0 : Math.max(...intervalSamples),
      durationP50Ms: percentile(durationSamples, 0.5),
      durationP95Ms: percentile(durationSamples, 0.95),
      durationMaxMs:
        durationSamples.length === 0 ? 0 : Math.max(...durationSamples),
      tickSampleCount: tickTotalSamples.length,
      tickTotal: durationStats(tickTotalSamples),
      tickPhases,
    };
  }

  function reset(): void {
    durationSamples.length = 0;
    intervalSamples.length = 0;
    tickTotalSamples.length = 0;
    for (const phase of TICK_PHASES) {
      phaseSamples[phase].length = 0;
    }
    lastRenderStartMs = null;
  }

  return { measure, measureTick, time, report, reset };
}
