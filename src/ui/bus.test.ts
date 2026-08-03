// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { createBusEndpoint, type BusMessage } from "./bus";

/** Drain BroadcastChannel delivery (command hop + snapshot hop). */
async function flushBus(): Promise<void> {
  for (let i = 0; i < 2; i += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  }
}

describe("underline BroadcastChannel bus", () => {
  it("round-trips dock-opened to a peer endpoint", async () => {
    const busChannel = `underline-test-${crypto.randomUUID()}`;
    const onOpened = vi.fn();

    const paneBus = createBusEndpoint(
      {
        "dock-opened": (message) => {
          onOpened(message);
        },
      },
      busChannel,
    );

    const dockBus = createBusEndpoint({}, busChannel);
    dockBus.publish({ type: "dock-opened" });
    await flushBus();

    expect(onOpened).toHaveBeenCalledTimes(1);
    expect(onOpened.mock.calls[0]?.[0]).toEqual({ type: "dock-opened" });

    paneBus.close();
    dockBus.close();
  });

  it("round-trips a snapshot message to dock listeners", async () => {
    const busChannel = `underline-test-${crypto.randomUUID()}`;
    const received: BusMessage[] = [];
    const dockBus = createBusEndpoint(
      {
        snapshot: (message) => {
          received.push(message);
        },
      },
      busChannel,
    );

    const paneBus = createBusEndpoint({}, busChannel);
    const snapshot = { digRate: 1, ore: 0 };
    paneBus.publish({ type: "snapshot", snapshot });
    await flushBus();

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ type: "snapshot", snapshot });

    paneBus.close();
    dockBus.close();
  });
});
