// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { initialSnapshot, SCHEMA_VERSION } from "../core/mining-engine";
import { toWireSnapshot } from "../core/wire-snapshot";
import { createBusEndpoint, isDockCommand, type BusMessage } from "./bus";

/** Drain BroadcastChannel delivery (command hop + snapshot hop). */
async function flushBus(): Promise<void> {
  for (let i = 0; i < 2; i += 1) {
    await new Promise((resolve) => {
      setTimeout(resolve, 0);
    });
  }
}

describe("isDockCommand", () => {
  it.each([
    { upgrade: "digRate" as const },
    { upgrade: "smelter" as const },
    { upgrade: "carryCapacity" as const },
  ])("accepts buyUpgrade with upgrade $upgrade", ({ upgrade }) => {
    expect(
      isDockCommand({ schemaVersion: SCHEMA_VERSION, name: "buyUpgrade", upgrade }),
    ).toBe(true);
  });

  it("accepts requestSnapshot", () => {
    expect(isDockCommand({ schemaVersion: SCHEMA_VERSION, name: "requestSnapshot" })).toBe(
      true,
    );
  });

  it.each([
    { label: "missing upgrade", command: { schemaVersion: SCHEMA_VERSION, name: "buyUpgrade" } },
    {
      label: "unknown upgrade",
      command: { schemaVersion: SCHEMA_VERSION, name: "buyUpgrade", upgrade: "hardness" },
    },
    { label: "wrong schemaVersion", command: { schemaVersion: 2, name: "buyUpgrade", upgrade: "digRate" } },
    { label: "non-object", command: null },
  ])("rejects $label", ({ command }) => {
    expect(isDockCommand(command)).toBe(false);
  });
});

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

  it("round-trips a schemaVersion 3 Snapshot to dock listeners", async () => {
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
    const snapshot = toWireSnapshot(initialSnapshot());
    paneBus.publish({ type: "snapshot", snapshot });
    await flushBus();

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ type: "snapshot", snapshot });

    paneBus.close();
    dockBus.close();
  });

  it("ignores Snapshots with a mismatched schemaVersion", async () => {
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
    paneBus.publish({
      type: "snapshot",
      snapshot: { schemaVersion: 99 } as never,
    });
    await flushBus();
    expect(received).toHaveLength(0);

    paneBus.close();
    dockBus.close();
  });
});
