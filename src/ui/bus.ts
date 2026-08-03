/** Adapted from Nightglass.

Source: nightglass/src/ui/bus.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Transport-only BroadcastChannel endpoint. Channel renamed to `underline`;
BusMessage payloads are opaque until the mining command schema lands (#323).
Dropped TileCommand* / applyTileCommand / Engine imports.
*/

export const UNDERLINE_BUS_CHANNEL = "underline";

export type BusMessage =
  | { type: "command"; command: unknown }
  | { type: "snapshot"; snapshot: unknown }
  | { type: "pump"; events: unknown[]; snapshot: unknown }
  | { type: "dock-opened" }
  | { type: "dock-closed" };

type BusHandlerMap = {
  [M in BusMessage as M["type"]]?: (message: M) => void;
};

export interface BusEndpoint {
  publish(message: BusMessage): void;
  close(): void;
}

export function createBusEndpoint(
  handlers: BusHandlerMap,
  channelName: string = UNDERLINE_BUS_CHANNEL,
): BusEndpoint {
  const channel = new BroadcastChannel(channelName);

  channel.onmessage = (event: MessageEvent<BusMessage>) => {
    const message = event.data;
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
