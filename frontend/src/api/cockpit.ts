const CLI_CANDIDATES = [
  "/usr/libexec/dock-panel/cli.py",
  "/usr/local/libexec/dock-panel/cli.py",
  "/usr/share/cockpit/dock-panel/backend/cli.py",
];

let cachedCli: string | null = null;

export function hasCockpit(): boolean {
  return typeof window !== "undefined" && Boolean(window.cockpit);
}

export function getCockpit(): CockpitApi {
  if (!window.cockpit) {
    throw new Error("当前不在 Cockpit 环境中，无法调用系统命令");
  }
  return window.cockpit;
}

export async function waitTransport(): Promise<void> {
  const cockpit = getCockpit();
  await new Promise<void>((resolve) => {
    const result = cockpit.transport.wait(() => resolve());
    if (result && typeof (result as Promise<void>).then === "function") {
      (result as Promise<void>).then(() => resolve()).catch(() => resolve());
    }
  });
}

async function locateCli(): Promise<string> {
  if (cachedCli) {
    return cachedCli;
  }
  const cockpit = getCockpit();
  const script = [
    "set -e",
    `HOME_CLI="$HOME/.local/share/cockpit/dock-panel/backend/cli.py"`,
    `for p in ${CLI_CANDIDATES.map((p) => `"${p}"`).join(" ")} "$HOME_CLI"; do`,
    '  if [ -f "$p" ]; then echo "$p"; exit 0; fi',
    "done",
    "exit 1",
  ].join("\n");
  const found = (await cockpit.script(script, [], { err: "message" })).trim();
  if (!found) {
    throw new Error("找不到 Dock Panel 后端脚本，请先执行 make install 或 make devel-install");
  }
  cachedCli = found;
  return found;
}

export interface SpawnHandle {
  close: () => void;
  done: Promise<string>;
}

export async function spawnCli(
  args: string[],
  options: {
    payload?: unknown;
    stream?: (chunk: string) => void;
    raw?: boolean;
    superuser?: "try" | "require";
  } = {},
): Promise<string> {
  const cockpit = getCockpit();
  const cli = await locateCli();
  const argv = ["python3", "-u", cli, ...args];
  if (options.raw) {
    argv.push("--stream");
  }
  const proc = cockpit.spawn(argv, {
    superuser: options.superuser ?? "try",
    err: options.raw ? "out" : "message",
    environ: ["PYTHONUNBUFFERED=1"],
  });
  if (options.stream) {
    proc.stream(options.stream);
  }
  if (options.payload !== undefined) {
    proc.input(JSON.stringify(options.payload ?? {}));
  } else {
    proc.input("");
  }
  return proc;
}

export function spawnCliLive(
  args: string[],
  options: {
    payload?: unknown;
    onChunk: (chunk: string) => void;
    superuser?: "try" | "require";
  },
): SpawnHandle {
  const cockpit = getCockpit();
  let closed = false;
  let proc: SpawnProcess | null = null;
  const done = (async () => {
    const cli = await locateCli();
    if (closed) {
      return "";
    }
    proc = cockpit.spawn(["python3", "-u", cli, ...args, "--stream"], {
      superuser: options.superuser ?? "try",
      err: "out",
      environ: ["PYTHONUNBUFFERED=1"],
    });
    proc.stream(options.onChunk);
    proc.input(JSON.stringify(options.payload ?? {}));
    return proc;
  })();
  return {
    close: () => {
      closed = true;
      proc?.close();
    },
    done,
  };
}
