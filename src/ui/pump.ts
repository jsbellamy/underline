/** Adapted from Nightglass.

Source: nightglass/src/ui/pump.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Sim/render pump with visibility catch-up. EngineEvent replaced with opaque
unknown[] until the mining event schema lands.
*/

import type { FrameMetrics, FrameMetricsReport } from "./frame-metrics";

export const PUMP_INTERVAL_MS = 250;
export const HIDDEN_HEARTBEAT_MS = 5000;
export const MAX_CATCH_UP_CHUNK_MS = 60_000;
export const MAX_CATCH_UP_BUDGET_MS = 8;

export interface PumpController {
  stop(): void;
  frameMetrics(): FrameMetricsReport | null;
}

export interface PumpDeps {
  advanceBy: (ms: number) => unknown[];
  onAdvance: (events: unknown[]) => void;
  render: () => void;
  frameMetrics?: FrameMetrics;
  now?: () => number;
  setInterval?: typeof setInterval;
  clearInterval?: typeof clearInterval;
  requestAnimationFrame?: typeof requestAnimationFrame;
  cancelAnimationFrame?: typeof cancelAnimationFrame;
  document?: Document;
}

function clampPumpElapsedMs(rawMs: number): number {
  return Math.min(Math.max(0, Math.floor(rawMs)), MAX_CATCH_UP_CHUNK_MS);
}

export function startPump(deps: PumpDeps): PumpController {
  const now = deps.now ?? (() => Date.now());
  const setIntervalFn = deps.setInterval ?? setInterval;
  const clearIntervalFn = deps.clearInterval ?? clearInterval;
  const requestFrame = deps.requestAnimationFrame ?? requestAnimationFrame.bind(window);
  const cancelFrame = deps.cancelAnimationFrame ?? cancelAnimationFrame.bind(window);
  const doc = deps.document ?? document;

  let pumpTimer: ReturnType<typeof setInterval> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  let rafId: number | null = null;
  let catchUpRafId: number | null = null;
  let catchUpDraining = false;
  let lastPumpAtMs = now();
  let lastHiddenPumpAtMs = now();
  let stopped = false;

  function isHidden(): boolean {
    return doc.hidden;
  }

  function pump(elapsedMs: number): void {
    const run = () => {
      const events = deps.frameMetrics
        ? deps.frameMetrics.time("advance", () => deps.advanceBy(elapsedMs))
        : deps.advanceBy(elapsedMs);
      if (events.length > 0) {
        deps.onAdvance(events);
      }
      scheduleRender();
    };
    if (deps.frameMetrics) {
      deps.frameMetrics.measureTick(run);
    } else {
      run();
    }
  }

  function maybeRender(): void {
    if (stopped || isHidden()) {
      return;
    }
    if (deps.frameMetrics) {
      deps.frameMetrics.measure(deps.render);
    } else {
      deps.render();
    }
  }

  function scheduleRender(): void {
    if (stopped || isHidden() || rafId !== null) {
      return;
    }
    rafId = requestFrame(() => {
      rafId = null;
      maybeRender();
      if (!stopped && !isHidden()) {
        scheduleRender();
      }
    });
  }

  function stopRendering(): void {
    if (rafId !== null) {
      cancelFrame(rafId);
      rafId = null;
    }
  }

  function stopCatchUpDrain(): void {
    if (catchUpRafId !== null) {
      cancelFrame(catchUpRafId);
      catchUpRafId = null;
    }
    catchUpDraining = false;
  }

  function finishCatchUpDrain(): void {
    stopCatchUpDrain();
    startLivePump();
    scheduleRender();
  }

  function drainCatchUpFrame(): void {
    if (stopped || isHidden()) {
      return;
    }

    const budgetStartMs = now();
    while (now() - budgetStartMs < MAX_CATCH_UP_BUDGET_MS) {
      const at = now();
      const elapsed = clampPumpElapsedMs(at - lastPumpAtMs);
      if (elapsed <= 0) {
        finishCatchUpDrain();
        return;
      }
      pump(elapsed);
      lastPumpAtMs += elapsed;
    }

    const remaining = clampPumpElapsedMs(now() - lastPumpAtMs);
    if (remaining > 0) {
      scheduleCatchUpFrame();
    } else {
      finishCatchUpDrain();
    }
  }

  function scheduleCatchUpFrame(): void {
    if (catchUpRafId !== null) {
      return;
    }
    catchUpDraining = true;
    catchUpRafId = requestFrame(() => {
      catchUpRafId = null;
      drainCatchUpFrame();
    });
  }

  function beginCatchUpDrain(): void {
    const debt = clampPumpElapsedMs(now() - lastPumpAtMs);
    if (debt <= 0) {
      lastPumpAtMs = now();
      startLivePump();
      scheduleRender();
      return;
    }
    scheduleCatchUpFrame();
  }

  function startLivePump(): void {
    if (pumpTimer !== null || catchUpDraining) {
      return;
    }
    lastPumpAtMs = now();
    pumpTimer = setIntervalFn(() => {
      if (stopped || isHidden() || catchUpDraining) {
        return;
      }
      const at = now();
      const elapsed = clampPumpElapsedMs(at - lastPumpAtMs);
      lastPumpAtMs = at;
      if (elapsed > 0) {
        pump(elapsed);
      }
    }, PUMP_INTERVAL_MS);
  }

  function stopLivePump(): void {
    if (pumpTimer !== null) {
      clearIntervalFn(pumpTimer);
      pumpTimer = null;
    }
  }

  function startHeartbeat(hiddenAnchorMs?: number): void {
    if (heartbeatTimer !== null) {
      return;
    }
    lastHiddenPumpAtMs = hiddenAnchorMs ?? now();
    heartbeatTimer = setIntervalFn(() => {
      if (stopped || !isHidden()) {
        return;
      }
      const at = now();
      const elapsed = clampPumpElapsedMs(at - lastHiddenPumpAtMs);
      lastHiddenPumpAtMs = at;
      if (elapsed > 0) {
        pump(elapsed);
        lastPumpAtMs += elapsed;
      }
    }, HIDDEN_HEARTBEAT_MS);
  }

  function stopHeartbeat(): void {
    if (heartbeatTimer !== null) {
      clearIntervalFn(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function onVisibilityChange(): void {
    if (stopped) {
      return;
    }
    if (isHidden()) {
      stopRendering();
      stopLivePump();
      const hiddenAnchor = catchUpDraining ? now() : undefined;
      stopCatchUpDrain();
      startHeartbeat(hiddenAnchor);
      return;
    }

    stopHeartbeat();
    beginCatchUpDrain();
  }

  doc.addEventListener("visibilitychange", onVisibilityChange);

  if (isHidden()) {
    startHeartbeat();
  } else {
    startLivePump();
    scheduleRender();
  }

  const frameMetricsRecorder = deps.frameMetrics ?? null;

  return {
    stop() {
      stopped = true;
      stopRendering();
      stopCatchUpDrain();
      stopLivePump();
      stopHeartbeat();
      doc.removeEventListener("visibilitychange", onVisibilityChange);
    },
    frameMetrics() {
      return frameMetricsRecorder ? frameMetricsRecorder.report() : null;
    },
  };
}
