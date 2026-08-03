/** Floating prototype switcher — not part of the design under evaluation. */

export interface PrototypeSwitcherOptions {
  variants: readonly { key: string; name: string }[];
  current: string;
  onChange(key: string): void;
}

export function mountPrototypeSwitcher(
  host: HTMLElement,
  options: PrototypeSwitcherOptions,
): () => void {
  const bar = document.createElement("div");
  bar.className = "msp-switcher";
  bar.setAttribute("role", "navigation");
  bar.setAttribute("aria-label", "Prototype variant switcher");

  const prev = document.createElement("button");
  prev.type = "button";
  prev.className = "msp-switcher-btn";
  prev.textContent = "←";
  prev.setAttribute("aria-label", "Previous variant");

  const label = document.createElement("span");
  label.className = "msp-switcher-label";

  const next = document.createElement("button");
  next.type = "button";
  next.className = "msp-switcher-btn";
  next.textContent = "→";
  next.setAttribute("aria-label", "Next variant");

  function renderLabel(key: string): void {
    const entry = options.variants.find((v) => v.key === key);
    label.textContent = entry ? `${key} — ${entry.name}` : key;
  }

  function cycle(delta: number): void {
    const keys = options.variants.map((v) => v.key);
    const idx = keys.indexOf(options.current);
    const nextIdx = (idx + delta + keys.length) % keys.length;
    const key = keys[nextIdx] ?? keys[0]!;
    options.onChange(key);
  }

  prev.addEventListener("click", () => cycle(-1));
  next.addEventListener("click", () => cycle(1));

  function onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (
      target &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable)
    ) {
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      cycle(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      cycle(1);
    }
  }

  renderLabel(options.current);
  bar.append(prev, label, next);
  host.append(bar);
  window.addEventListener("keydown", onKey);

  return () => {
    window.removeEventListener("keydown", onKey);
    bar.remove();
  };
}
