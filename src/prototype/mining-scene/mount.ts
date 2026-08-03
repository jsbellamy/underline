import {
  SCENE_MOMENTS,
  SCENE_MOMENT_LABELS,
  snapshotFor,
  type SceneMoment,
} from "./moments";
import { mountPrototypeSwitcher } from "./switcher";
import { mountVariantA, VARIANT_A_NAME } from "./variant-a";
import { mountVariantB, VARIANT_B_NAME } from "./variant-b";
import { mountVariantC, VARIANT_C_NAME } from "./variant-c";
import "./mining-scene.css";

const VARIANTS = [
  { key: "A", name: VARIANT_A_NAME },
  { key: "B", name: VARIANT_B_NAME },
  { key: "C", name: VARIANT_C_NAME },
] as const;

type VariantKey = (typeof VARIANTS)[number]["key"];

function readVariant(params: URLSearchParams): VariantKey {
  const raw = (params.get("variant") ?? "A").toUpperCase();
  if (raw === "B" || raw === "C" || raw === "A") {
    return raw;
  }
  return "A";
}

function readMoment(params: URLSearchParams): SceneMoment {
  const raw = params.get("moment") ?? "first-open";
  if ((SCENE_MOMENTS as readonly string[]).includes(raw)) {
    return raw as SceneMoment;
  }
  return "first-open";
}

function writeParams(variant: VariantKey, moment: SceneMoment): void {
  const url = new URL(window.location.href);
  url.searchParams.set("prototype", "mining-scene");
  url.searchParams.set("variant", variant);
  url.searchParams.set("moment", moment);
  window.history.replaceState({}, "", url);
}

/**
 * Three variants of the 480×112 mining Pane, switchable via ?variant=.
 * Scene moments via ?moment= so each layout can be judged at first-open,
 * swinging, advance-200, and ore-backed-up.
 */
export function mountMiningScenePrototype(root: HTMLElement): () => void {
  document.documentElement.classList.add("mining-scene-prototype");
  document.body.classList.add("mining-scene-prototype");

  const workspace = document.createElement("div");
  workspace.className = "msp-workspace";

  const frame = document.createElement("div");
  frame.className = "msp-frame";
  frame.setAttribute("aria-label", "Pane prototype frame 480 by 112");

  const stage = document.createElement("div");
  stage.className = "msp-stage";

  const readout = document.createElement("pre");
  readout.className = "msp-readout";

  const momentBar = document.createElement("div");
  momentBar.className = "msp-moments";
  momentBar.setAttribute("role", "toolbar");
  momentBar.setAttribute("aria-label", "Scene moment");

  workspace.append(frame, readout, momentBar);
  root.replaceChildren(workspace);

  let variant = readVariant(new URLSearchParams(window.location.search));
  let moment = readMoment(new URLSearchParams(window.location.search));
  let disposeSwitcher: (() => void) | null = null;

  function render(): void {
    const snap = snapshotFor(moment);
    writeParams(variant, moment);

    if (variant === "A") {
      mountVariantA(frame, snap);
    } else if (variant === "B") {
      mountVariantB(frame, snap);
    } else {
      mountVariantC(frame, snap);
    }

    readout.textContent = JSON.stringify(
      {
        variant,
        name: VARIANTS.find((v) => v.key === variant)?.name,
        momentLabel: SCENE_MOMENT_LABELS[moment],
        ...snap,
        dwarfScale: variant === "A" ? 4 : variant === "B" ? 3 : 2,
        camera:
          variant === "A"
            ? "dwarf-fixed / world-scrolls"
            : variant === "B"
              ? "face-pinned-east / camera-follows-advance"
              : "side-scroller / face-near-right-third",
      },
      null,
      2,
    );

    for (const btn of momentBar.querySelectorAll("button")) {
      const key = btn.getAttribute("data-moment");
      btn.classList.toggle("active", key === moment);
    }
  }

  for (const key of SCENE_MOMENTS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "msp-moment-btn";
    btn.dataset["moment"] = key;
    btn.textContent = key;
    btn.title = SCENE_MOMENT_LABELS[key];
    btn.addEventListener("click", () => {
      moment = key;
      render();
    });
    momentBar.append(btn);
  }

  function remountSwitcher(): void {
    disposeSwitcher?.();
    disposeSwitcher = mountPrototypeSwitcher(stage, {
      variants: VARIANTS,
      current: variant,
      onChange(key) {
        variant = key as VariantKey;
        remountSwitcher();
        render();
      },
    });
  }

  workspace.append(stage);
  remountSwitcher();
  render();

  return () => {
    disposeSwitcher?.();
    document.documentElement.classList.remove("mining-scene-prototype");
    document.body.classList.remove("mining-scene-prototype");
    root.replaceChildren();
  };
}

export function isMiningScenePrototype(): boolean {
  return (
    new URLSearchParams(window.location.search).get("prototype") ===
    "mining-scene"
  );
}
