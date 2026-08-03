/** Vendored from Nightglass.

Source: nightglass/src/ui/tab-strip.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit this copy in place.
*/

import { bindPressable } from "./keyboard";

export interface TabDef<Id extends string> {
  id: Id;
  label: string;
}

export interface TabStripOptions<Id extends string> {
  tabs: readonly TabDef<Id>[];
  initial: Id;
  /**
   * Styling stem shared by the strip: the tablist receives `${className}s` and
   * each tab receives `${className} focus-ring` (e.g. `"dock-tab"`).
   */
  className: string;
  ariaLabel: string;
  /** Panel element id per tab, for aria-controls / aria-labelledby wiring. */
  panelId(id: Id): string;
  onActivate(id: Id): void;
  /** Called when the already-active tab is activated again. Dock closes on this. */
  onReactivate?(id: Id): void;
}

export interface TabStrip<Id extends string> {
  element: HTMLElement;
  setActive(id: Id): void;
  activeId(): Id;
  focus(id: Id): void;
  destroy(): void;
}

function cycleTab<Id extends string>(
  tabs: readonly TabDef<Id>[],
  current: Id,
  delta: number,
): Id {
  const index = tabs.findIndex((entry) => entry.id === current);
  const next = (index + delta + tabs.length) % tabs.length;
  return tabs[next]!.id;
}

export function mountTabStrip<Id extends string>(
  options: TabStripOptions<Id>,
): TabStrip<Id> {
  let active: Id = options.initial;
  const buttons = new Map<Id, HTMLButtonElement>();

  const tabList = document.createElement("div");
  tabList.className = `${options.className}s`;
  tabList.setAttribute("role", "tablist");
  tabList.setAttribute("aria-label", options.ariaLabel);

  function sync(): void {
    for (const { id } of options.tabs) {
      const selected = id === active;
      const button = buttons.get(id)!;
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", selected ? "true" : "false");
      button.tabIndex = selected ? 0 : -1;
    }
  }

  /**
   * @param fromPress — true for click / Enter / Space activation. Only presses
   * of the already-active tab invoke `onReactivate` (Dock close). Keyboard
   * Home/End on the current ends must not.
   */
  function select(id: Id, moveFocus: boolean, fromPress: boolean): void {
    if (id === active) {
      if (fromPress) {
        options.onReactivate?.(id);
      } else if (moveFocus) {
        buttons.get(id)?.focus();
      }
      return;
    }
    active = id;
    sync();
    if (moveFocus) {
      buttons.get(id)?.focus();
    }
    options.onActivate(id);
  }

  function onTabKeydown(event: KeyboardEvent, tab: Id): void {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      select(cycleTab(options.tabs, tab, 1), true, false);
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      select(cycleTab(options.tabs, tab, -1), true, false);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      select(options.tabs[0]!.id, true, false);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      select(options.tabs[options.tabs.length - 1]!.id, true, false);
    }
  }

  for (const { id, label } of options.tabs) {
    const tabButton = document.createElement("button");
    tabButton.type = "button";
    tabButton.className = `${options.className} focus-ring`;
    tabButton.setAttribute("role", "tab");
    tabButton.setAttribute("aria-controls", options.panelId(id));
    tabButton.id = `${options.className}-${id}`;
    tabButton.textContent = label;

    bindPressable(tabButton, () => select(id, false, true));
    tabButton.addEventListener("keydown", (event) => onTabKeydown(event, id));

    tabList.append(tabButton);
    buttons.set(id, tabButton);
  }

  sync();

  return {
    element: tabList,
    setActive(id) {
      active = id;
      sync();
    },
    activeId: () => active,
    focus(id) {
      buttons.get(id)?.focus();
    },
    destroy() {
      tabList.replaceChildren();
      buttons.clear();
    },
  };
}
