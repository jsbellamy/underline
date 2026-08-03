import { describe, expect, it } from "vitest";
import {
  createFrameMetrics,
  FRAME_METRICS_WINDOW,
} from "./frame-metrics";

function percentileNearestRank(values: number[], p: number): number {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const len = sorted.length;
  return sorted[Math.min(len - 1, Math.ceil(p * len) - 1)]!;
}

describe("createFrameMetrics", () => {
  it("reports intervalP50Ms from a hand-driven sequence of known frame gaps", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });
    const renderDurationMs = 2;
    const gapsBeforeRender = [16, 20, 16, 33, 16];
    const intervals: number[] = [];
    let previousStart: number | null = null;

    for (const gap of gapsBeforeRender) {
      clock += gap;
      const start = clock;
      if (previousStart !== null) {
        intervals.push(start - previousStart);
      }
      metrics.measure(() => {
        clock += renderDurationMs;
      });
      previousStart = start;
    }

    const durations = gapsBeforeRender.map(() => renderDurationMs);
    const report = metrics.report();

    expect(report.intervalP50Ms).toBe(percentileNearestRank(intervals, 0.5));
    expect(report.sampleCount).toBe(gapsBeforeRender.length);
    expect(report.intervalP95Ms).toBe(percentileNearestRank(intervals, 0.95));
    expect(report.intervalMaxMs).toBe(Math.max(...intervals));
    expect(report.durationP50Ms).toBe(percentileNearestRank(durations, 0.5));
  });

  it("records duration on the first measure but no interval; one frame yields intervalP50Ms 0", () => {
    let clock = 100;
    const metrics = createFrameMetrics({ now: () => clock });

    metrics.measure(() => {
      clock += 5;
    });

    const report = metrics.report();
    expect(report.sampleCount).toBe(1);
    expect(report.intervalP50Ms).toBe(0);
    expect(report.intervalP95Ms).toBe(0);
    expect(report.intervalMaxMs).toBe(0);
    expect(report.durationP50Ms).toBe(5);
  });

  it("never keeps more than FRAME_METRICS_WINDOW samples after many measured frames", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    const totalFrames = FRAME_METRICS_WINDOW + 50;
    for (let i = 0; i < totalFrames; i++) {
      clock += 16;
      metrics.measure(() => {
        clock += 1;
      });
    }

    expect(metrics.report().sampleCount).toBe(FRAME_METRICS_WINDOW);
  });

  it("propagates render errors and still records that frame duration", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    clock += 16;
    expect(() =>
      metrics.measure(() => {
        clock += 7;
        throw new Error("render failed");
      }),
    ).toThrow("render failed");

    const report = metrics.report();
    expect(report.sampleCount).toBe(1);
    expect(report.durationMaxMs).toBe(7);
  });

  it("clears interval baseline after reset so the next measure has no interval", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    clock += 16;
    metrics.measure(() => {
      clock += 1;
    });
    clock += 20;
    metrics.measure(() => {
      clock += 1;
    });

    metrics.reset();

    clock += 99;
    metrics.measure(() => {
      clock += 3;
    });

    expect(metrics.report().sampleCount).toBe(1);
    expect(metrics.report().intervalP50Ms).toBe(0);
    expect(metrics.report().durationP50Ms).toBe(3);
  });

  it("reports tickSampleCount matching the number of completed sim ticks", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    metrics.measureTick(() => {
      clock += 4;
    });
    metrics.measureTick(() => {
      clock += 6;
    });

    const report = metrics.report();
    expect(report.tickSampleCount).toBe(2);
    expect(report.tickTotal.p50Ms).toBe(4);
    expect(report.tickTotal.maxMs).toBe(6);
  });

  it("attributes injected advance, legality, and publish costs to their tick phases", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    metrics.measureTick(() => {
      metrics.time("advance", () => {
        clock += 5;
      });
      metrics.time("legality", () => {
        clock += 10;
      });
      metrics.time("publish", () => {
        clock += 20;
      });
    });

    const report = metrics.report();
    expect(report.tickPhases.advance.p50Ms).toBe(5);
    expect(report.tickPhases.legality.p50Ms).toBe(10);
    expect(report.tickPhases.publish.p50Ms).toBe(20);
  });

  it("keeps tick total independent of phase sums when unmeasured gaps exist", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    metrics.measureTick(() => {
      metrics.time("advance", () => {
        clock += 2;
      });
      clock += 50;
      metrics.time("publish", () => {
        clock += 3;
      });
    });

    const report = metrics.report();
    expect(report.tickTotal.p50Ms).toBe(55);
    expect(report.tickPhases.advance.p50Ms).toBe(2);
    expect(report.tickPhases.publish.p50Ms).toBe(3);
  });

  it("returns phase work unchanged and still records duration when phase work throws", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    expect(
      metrics.time("legality", () => {
        clock += 4;
        return 99;
      }),
    ).toBe(99);

    expect(() =>
      metrics.time("advance", () => {
        clock += 7;
        throw new Error("phase failed");
      }),
    ).toThrow("phase failed");

    const report = metrics.report();
    expect(report.tickPhases.legality.p50Ms).toBe(4);
    expect(report.tickPhases.advance.p50Ms).toBe(7);
  });

  it("drops the oldest tick sample once the rolling window is full", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    const totalTicks = FRAME_METRICS_WINDOW + 30;
    for (let i = 0; i < totalTicks; i++) {
      metrics.measureTick(() => {
        clock += 1;
      });
    }

    expect(metrics.report().tickSampleCount).toBe(FRAME_METRICS_WINDOW);
  });

  it("clears tick, phase, and frame samples together on reset", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    clock += 16;
    metrics.measure(() => {
      clock += 2;
    });
    metrics.measureTick(() => {
      metrics.time("advance", () => {
        clock += 5;
      });
    });

    metrics.reset();

    const report = metrics.report();
    expect(report.sampleCount).toBe(0);
    expect(report.tickSampleCount).toBe(0);
    expect(report.tickPhases.advance.p50Ms).toBe(0);
    expect(report.intervalP50Ms).toBe(0);
  });

  it("still exposes frame interval and duration percentiles on the instrumentation report", () => {
    let clock = 0;
    const metrics = createFrameMetrics({ now: () => clock });

    clock += 16;
    metrics.measure(() => {
      clock += 1;
    });

    const report = metrics.report();
    expect(report).toHaveProperty("intervalP50Ms");
    expect(report).toHaveProperty("durationP95Ms");
    expect(typeof report.intervalP50Ms).toBe("number");
    expect(typeof report.durationP95Ms).toBe("number");
  });
});
