/** Adapted from Nightglass.

Source: nightglass/src/ui/bus.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

BroadcastChannel endpoint for Pane↔Dock. Channel `underline`; payloads follow
`docs/research/pane-dock-bus-schema.md`.
*/

import type { WireSnapshot } from "../core/wire-snapshot";
import { isUpgradeId } from "../data/upgrade-catalogue";
import { SCHEMA_VERSION, type UpgradeId } from "../core/mining-engine";

export const UNDERLINE_BUS_CHANNEL = "underline";

export type DockCommand =
  | { schemaVersion: typeof SCHEMA_VERSION; name: "buyUpgrade"; upgrade: UpgradeId }
  | { schemaVersion: typeof SCHEMA_VERSION; name: "requestSnapshot" };

export type BusMessage =
  | { type: "command"; command: DockCommand }
  | { type: "snapshot"; snapshot: WireSnapshot }
  | { type: "dock-opened" }
  | { type: "dock-closed" };

type BusHandlerMap = {
  [M in BusMessage as M["type"]]?: (message: M) => void;
};

export interface BusEndpoint {
  publish(message: BusMessage): void;
  close(): void;
}

function isSchemaVersion(value: unknown): value is typeof SCHEMA_VERSION {
  return value === SCHEMA_VERSION;
}

/** True when a Dock command carries schemaVersion 2. */
export function isDockCommand(value: unknown): value is DockCommand {
  if (!value || typeof value !== "object") {
    return false;
  }
  const command = value as { schemaVersion?: unknown; name?: unknown; upgrade?: unknown };
  if (!isSchemaVersion(command.schemaVersion)) {
    return false;
  }
  if (command.name === "requestSnapshot") {
    return true;
  }
  if (command.name === "buyUpgrade") {
    return isUpgradeId(command.upgrade);
  }
  return false;
}

/** True when a wire Snapshot carries schemaVersion 2. */
export function isWireSnapshot(value: unknown): value is WireSnapshot {
  if (!value || typeof value !== "object") {
    return false;
  }
  return isSchemaVersion((value as WireSnapshot).schemaVersion);
}

export function createBusEndpoint(
  handlers: BusHandlerMap,
  channelName: string = UNDERLINE_BUS_CHANNEL,
): BusEndpoint {
  const channel = new BroadcastChannel(channelName);

  channel.onmessage = (event: MessageEvent<BusMessage>) => {
    const message = event.data;
    if (!message || typeof message !== "object" || !("type" in message)) {
      return;
    }
    if (message.type === "snapshot" && !isWireSnapshot(message.snapshot)) {
      return;
    }
    if (message.type === "command" && !isDockCommand(message.command)) {
      return;
    }
    const handler = handlers[message.type];
    if (handler) {
      handler(message as never);
    }
  };

  return {
    publish(message) {
      channel.postMessage(message);
    },
    close() {
      channel.close();
    },
  };
}
