/// <reference types="vite/client" />

interface SpawnOptions {
  superuser?: "require" | "try";
  err?: "out" | "message" | "ignore";
  environ?: string[];
  directory?: string;
  pty?: boolean;
  binary?: boolean;
}

interface SpawnProcess extends Promise<string> {
  stream(callback: (data: string) => void): SpawnProcess;
  input(data: string | Uint8Array, stream?: boolean): SpawnProcess;
  close(problem?: string): void;
}

interface CockpitApi {
  spawn(args: string[] | string, options?: SpawnOptions): SpawnProcess;
  script(script: string, args?: string[], options?: SpawnOptions): SpawnProcess;
  transport: {
    wait(callback?: () => void): Promise<void> | void;
  };
}

interface Window {
  cockpit?: CockpitApi;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
