// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { mountTabStrip, type TabDef } from "./tab-strip";

type DemoId = "alpha" | "beta" | "gamma";

const DEMO_TABS: readonly TabDef<DemoId>[] = [
  { id: "alpha", label: "Alpha" },
  { id: "beta", label: "Beta" },
  { id: "gamma", label: "Gamma" },
];

function mountDemo(
  extras: {
    onActivate?: ReturnType<typeof vi.fn<(id: DemoId) => void>>;
    onReactivate?: ReturnType<typeof vi.fn<(id: DemoId) => void>>;
    initial?: DemoId;
  } = {},
) {
  const host = document.createElement("div");
  document.body.append(host);
  const onActivate = extras.onActivate ?? vi.fn<(id: DemoId) => void>();
  const strip = mountTabStrip<DemoId>({
    tabs: DEMO_TABS,
    initial: extras.initial ?? "alpha",
    className: "demo-tab",
    ariaLabel: "Demo surfaces",
    panelId: (id) => `demo-panel-${id}`,
    onActivate,
    ...(extras.onReactivate ? { onReactivate: extras.onReactivate } : {}),
  });
  host.append(strip.element);
  return { host, strip, onActivate, onReactivate: extras.onReactivate };
}

function tabButton(host: HTMLElement, id: DemoId): HTMLButtonElement {
  return host.querySelector<HTMLButtonElement>(`#demo-tab-${id}`)!;
}

function rovingState(host: HTMLElement): { selected: DemoId; tabIndex0: DemoId[] } {
  const buttons = [...host.querySelectorAll<HTMLButtonElement>('[role="tab"]')];
  const selected = buttons.find((button) => button.getAttribute("aria-selected") === "true");
  return {
    selected: selected!.id.replace(/^demo-tab-/, "") as DemoId,
    tabIndex0: buttons
      .filter((button) => button.tabIndex === 0)
      .map((button) => button.id.replace(/^demo-tab-/, "") as DemoId),
  };
}

describe("Tab strip keyboard and selection", () => {
  it("ArrowRight and ArrowDown advance and wrap; ArrowLeft and ArrowUp retreat and wrap; Home selects the first tab; End selects the last; each moves focus as well as selection", () => {
    const { host, strip, onActivate } = mountDemo();
    const alpha = tabButton(host, "alpha");
    alpha.focus();

    alpha.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
    expect(strip.activeId()).toBe("beta");
    expect(document.activeElement).toBe(tabButton(host, "beta"));
    expect(onActivate).toHaveBeenLastCalledWith("beta");

    tabButton(host, "beta").dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }),
    );
    expect(strip.activeId()).toBe("gamma");
    expect(document.activeElement).toBe(tabButton(host, "gamma"));

    tabButton(host, "gamma").dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
    );
    expect(strip.activeId()).toBe("alpha");
    expect(document.activeElement).toBe(tabButton(host, "alpha"));

    tabButton(host, "alpha").dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }),
    );
    expect(strip.activeId()).toBe("gamma");
    expect(document.activeElement).toBe(tabButton(host, "gamma"));

    tabButton(host, "gamma").dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }),
    );
    expect(strip.activeId()).toBe("beta");
    expect(document.activeElement).toBe(tabButton(host, "beta"));

    tabButton(host, "beta").dispatchEvent(
      new KeyboardEvent("keydown", { key: "Home", bubbles: true }),
    );
    expect(strip.activeId()).toBe("alpha");
    expect(document.activeElement).toBe(tabButton(host, "alpha"));

    tabButton(host, "alpha").dispatchEvent(
      new KeyboardEvent("keydown", { key: "End", bubbles: true }),
    );
    expect(strip.activeId()).toBe("gamma");
    expect(document.activeElement).toBe(tabButton(host, "gamma"));

    strip.destroy();
    host.remove();
  });

  it("keeps exactly one tab at tabIndex 0 and matches aria-selected to the active tab", () => {
    const { host, strip } = mountDemo();

    expect(rovingState(host)).toEqual({ selected: "alpha", tabIndex0: ["alpha"] });
    for (const id of DEMO_TABS.map((tab) => tab.id)) {
      const button = tabButton(host, id);
      expect(button.tabIndex).toBe(id === "alpha" ? 0 : -1);
      expect(button.getAttribute("aria-selected")).toBe(id === "alpha" ? "true" : "false");
    }

    strip.setActive("gamma");
    expect(rovingState(host)).toEqual({ selected: "gamma", tabIndex0: ["gamma"] });

    tabButton(host, "gamma").dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }),
    );
    expect(rovingState(host)).toEqual({ selected: "beta", tabIndex0: ["beta"] });

    strip.destroy();
    host.remove();
  });

  it("calls onReactivate when the already-active tab is pressed and skips onActivate when onReactivate is omitted", () => {
    const onReactivate = vi.fn<(id: DemoId) => void>();
    const withReactivate = mountDemo({ onReactivate });
    tabButton(withReactivate.host, "alpha").click();
    expect(onReactivate).toHaveBeenCalledTimes(1);
    expect(onReactivate).toHaveBeenCalledWith("alpha");
    expect(withReactivate.onActivate).not.toHaveBeenCalled();

    // Home on the already-first tab must not reactivate (Dock must not close).
    onReactivate.mockClear();
    tabButton(withReactivate.host, "alpha").dispatchEvent(
      new KeyboardEvent("keydown", { key: "Home", bubbles: true }),
    );
    expect(onReactivate).not.toHaveBeenCalled();

    withReactivate.strip.destroy();
    withReactivate.host.remove();

    const without = mountDemo();
    without.onActivate.mockClear();
    tabButton(without.host, "alpha").click();
    expect(without.onActivate).not.toHaveBeenCalled();
    without.strip.destroy();
    without.host.remove();
  });
});
