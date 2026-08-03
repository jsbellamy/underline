// @vitest-environment happy-dom

import { describe, expect, it, vi } from "vitest";
import { bindPressable } from "./keyboard";

function press(element: HTMLElement, key: "Enter" | " "): void {
  element.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

describe("Pressable control activation", () => {
  it("fires its action exactly once for a click, once for Enter, and once for Space on a button", () => {
    const button = document.createElement("button");
    button.type = "button";
    document.body.append(button);
    const action = vi.fn();
    bindPressable(button, action);

    button.click();
    expect(action).toHaveBeenCalledTimes(1);

    action.mockClear();
    press(button, "Enter");
    expect(action).toHaveBeenCalledTimes(1);

    action.mockClear();
    press(button, " ");
    expect(action).toHaveBeenCalledTimes(1);

    button.remove();
  });

  it("fires its action exactly once for a click, once for Enter, and once for Space on a non-button element with a role", () => {
    const chip = document.createElement("div");
    chip.setAttribute("role", "button");
    chip.tabIndex = 0;
    document.body.append(chip);
    const action = vi.fn();
    bindPressable(chip, action);

    chip.click();
    expect(action).toHaveBeenCalledTimes(1);

    action.mockClear();
    press(chip, "Enter");
    expect(action).toHaveBeenCalledTimes(1);

    action.mockClear();
    press(chip, " ");
    expect(action).toHaveBeenCalledTimes(1);

    chip.remove();
  });
});
