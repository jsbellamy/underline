import { isTauriRuntime } from "./dock-window";

export interface AppExitPort {
  exit(): Promise<void>;
}

export interface AppExitDeps {
  isTauri?: boolean;
  beforeExit?: () => void;
  invoke?: (command: string) => Promise<unknown>;
}

export function createProductionAppExitPort(deps: AppExitDeps = {}): AppExitPort {
  const isTauri = deps.isTauri ?? isTauriRuntime();

  return {
    async exit() {
      if (deps.beforeExit) {
        deps.beforeExit();
      }
      if (!isTauri) {
        return;
      }
      const invoke = deps.invoke ?? defaultInvoke;
      await invoke("quit_app");
    },
  };
}

async function defaultInvoke(command: string): Promise<unknown> {
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke(command);
}
