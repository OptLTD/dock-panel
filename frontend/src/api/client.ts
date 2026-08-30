import { hasCockpit, spawnCli, spawnCliLive, waitTransport, type SpawnHandle } from "./cockpit";
import type { ApiResult, Certificate, HealthInfo, Project, ScanHit } from "./types";

const MOCK_PROJECTS: Project[] = [
  {
    name: "homepage",
    compose_file: "/var/lib/dock-panel/projects/homepage/compose.yaml",
    workdir: "/var/lib/dock-panel/projects/homepage",
    managed: true,
    notes: "示例项目",
    certs: ["lab.local"],
    summary: "running",
    running: 2,
    total: 2,
    ports: ["8080:80", "8443:443"],
    services: [
      {
        id: "a1",
        name: "homepage-web-1",
        service: "web",
        image: "nginx:alpine",
        state: "running",
        status: "Up 3 hours",
        ports: ["8080:80", "8443:443"],
      },
      {
        id: "a2",
        name: "homepage-app-1",
        service: "app",
        image: "ghcr.io/example/app:latest",
        state: "running",
        status: "Up 3 hours",
        ports: [],
      },
    ],
    compose_yaml: "services:\n  web:\n    image: nginx:alpine\n",
    env_text: "DOMAIN=lab.local\n",
  },
];

const MOCK_CERTS: Certificate[] = [
  {
    name: "lab.local",
    path: "/var/lib/dock-panel/certs/lab.local/cert.pem",
    key_path: "/var/lib/dock-panel/certs/lab.local/key.pem",
    has_key: true,
    source: "self-signed",
    subject: "CN = lab.local",
    issuer: "CN = lab.local",
    not_after: "Nov  8 12:00:00 2026 GMT",
    fingerprint: "AA:BB:CC",
    sans: ["lab.local", "*.lab.local"],
    days_left: 70,
    expired: false,
    self_signed: true,
  },
];

async function call<T>(command: string, extra: string[] = [], payload: unknown = {}): Promise<T> {
  if (!hasCockpit()) {
    throw new Error("请在 Cockpit 中打开此页面，或使用 make devel-install 安装后访问");
  }
  await waitTransport();
  const raw = await spawnCli([command, ...extra], { payload });
  let parsed: ApiResult<T>;
  try {
    parsed = JSON.parse(raw) as ApiResult<T>;
  } catch {
    throw new Error(raw || "后端返回了无法解析的内容");
  }
  if (!parsed.ok) {
    throw new Error(parsed.error || "后端调用失败");
  }
  return parsed.data as T;
}

export const api = {
  async health(): Promise<HealthInfo> {
    if (!hasCockpit()) {
      return {
        version: "0.1.0-dev",
        state_dir: "/var/lib/dock-panel",
        engine: {
          docker: true,
          compose: true,
          version: "27.0.0",
          compose_version: "2.29.0",
          error: null,
        },
        projects: MOCK_PROJECTS.length,
        certs: MOCK_CERTS.length,
      };
    }
    return call<HealthInfo>("health");
  },

  async listProjects(): Promise<Project[]> {
    if (!hasCockpit()) return MOCK_PROJECTS;
    return call<Project[]>("projects.list");
  },

  async getProject(name: string): Promise<Project> {
    if (!hasCockpit()) {
      const found = MOCK_PROJECTS.find((item) => item.name === name);
      if (!found) throw new Error(`项目不存在: ${name}`);
      return found;
    }
    return call<Project>("projects.get", ["--name", name]);
  },

  async registerProject(payload: {
    name?: string;
    compose_file: string;
    workdir?: string;
    env_file?: string;
    notes?: string;
  }): Promise<Project> {
    return call<Project>("projects.register", [], payload);
  },

  async createProject(payload: Record<string, unknown>): Promise<Project> {
    return call<Project>("projects.create", [], payload);
  },

  async updateProject(name: string, payload: { compose_yaml: string; env_text?: string; notes?: string }): Promise<Project> {
    return call<Project>("projects.update", ["--name", name], payload);
  },

  async unregisterProject(name: string, options: { destroy?: boolean; remove_files?: boolean } = {}): Promise<void> {
    await call("projects.unregister", ["--name", name], options);
  },

  async scanProjects(): Promise<ScanHit[]> {
    if (!hasCockpit()) {
      return [
        {
          name: "gitea",
          compose_file: "/opt/gitea/compose.yaml",
          workdir: "/opt/gitea",
          registered: false,
        },
      ];
    }
    return call<ScanHit[]>("projects.scan");
  },

  streamProjectAction(
    name: string,
    action: "up" | "down" | "restart" | "pull" | "start" | "stop",
    onChunk: (chunk: string) => void,
    service?: string,
  ): SpawnHandle {
    if (!hasCockpit()) {
      onChunk(`[dev] ${action} ${name}\n`);
      return { close: () => undefined, done: Promise.resolve("") };
    }
    const extra = ["--name", name];
    if (service) extra.push("--service", service);
    return spawnCliLive([`projects.${action}`, ...extra], { onChunk, payload: { stream: true } });
  },

  async listCerts(): Promise<Certificate[]> {
    if (!hasCockpit()) return MOCK_CERTS;
    return call<Certificate[]>("certs.list");
  },

  async getCert(name: string, includePem = false): Promise<Certificate> {
    if (!hasCockpit()) {
      const found = MOCK_CERTS.find((item) => item.name === name);
      if (!found) throw new Error(`证书不存在: ${name}`);
      return found;
    }
    return call<Certificate>("certs.get", ["--name", name], { include_pem: includePem });
  },

  async importCert(payload: Record<string, unknown>): Promise<Certificate> {
    return call<Certificate>("certs.import", [], payload);
  },

  async generateCert(payload: Record<string, unknown>): Promise<Certificate> {
    return call<Certificate>("certs.generate", [], payload);
  },

  async deleteCert(name: string): Promise<void> {
    await call("certs.delete", ["--name", name]);
  },

  async assignCert(name: string, project: string, unassign = false): Promise<void> {
    await call("certs.assign", ["--name", name, "--project", project], { project, unassign });
  },

  async tailLogs(name: string, service?: string, lines = 200): Promise<string> {
    if (!hasCockpit()) {
      return `${new Date().toISOString()} web-1  | listening on :80\n${new Date().toISOString()} app-1  | ready\n`;
    }
    const extra = ["--name", name, "--lines", String(lines)];
    if (service) extra.push("--service", service);
    const result = await call<{ text: string }>("logs.tail", extra, { lines, service });
    return result.text;
  },

  followLogs(name: string, onChunk: (chunk: string) => void, service?: string, lines = 200): SpawnHandle {
    if (!hasCockpit()) {
      onChunk("[dev] follow logs...\n");
      return { close: () => undefined, done: Promise.resolve("") };
    }
    const extra = ["--name", name, "--lines", String(lines)];
    if (service) extra.push("--service", service);
    return spawnCliLive(["logs.follow", ...extra], { onChunk });
  },
};
