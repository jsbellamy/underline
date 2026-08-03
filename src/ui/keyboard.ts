/** Vendored from Nightglass.

Source: nightglass/src/ui/keyboard.ts
Nightglass commit: 7047b2a28565d28598a4420b8762c7f49b1898f5
Vendored: 2026-08-03

Behaviour changes belong upstream in Nightglass and are re-vendored here;
do not edit this copy in place.
*/

export function bindPressable(element: HTMLElement, action: () => void): void {
  element.addEventListener("click", action);
  element.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      action();
    }
  });
}
