import { beforeEach } from "vitest";

const backing = new Map<string, string>();

if (typeof globalThis.localStorage === "undefined") {
  globalThis.localStorage = {
    getItem: (key: string) => backing.get(key) ?? null,
    setItem: (key: string, value: string) => {
      backing.set(key, value);
    },
    removeItem: (key: string) => {
      backing.delete(key);
    },
    clear: () => {
      backing.clear();
    },
    key: () => null,
    get length() {
      return backing.size;
    },
  } as Storage;
}

beforeEach(() => {
  backing.clear();
});
