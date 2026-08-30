export type ProjectSummary = "running" | "stopped" | "partial" | "empty" | "missing" | "error";

export interface ServiceInfo {
  id: string;
  name: string;
  service: string;
  image: string;
  state: string;
  status: string;
  ports: string[];
}

export interface Project {
  name: string;
  compose_file: string;
  workdir: string;
  env_file?: string;
  managed: boolean;
  unregistered?: boolean;
  notes?: string;
  certs: string[];
  created_at?: string;
  updated_at?: string;
  compose_exists?: boolean;
  summary: ProjectSummary;
  running: number;
  total: number;
  ports: string[];
  services: ServiceInfo[];
  error?: string;
  compose_yaml?: string;
  env_text?: string;
}

export interface Certificate {
  name: string;
  path: string;
  key_path: string;
  has_key: boolean;
  source?: string;
  notes?: string;
  subject?: string;
  issuer?: string;
  not_before?: string;
  not_after?: string;
  not_after_iso?: string;
  fingerprint?: string;
  sans: string[];
  days_left: number | null;
  expired?: boolean;
  self_signed?: boolean;
  cert_pem?: string;
  error?: string;
}

export interface EngineInfo {
  docker: boolean;
  compose: boolean;
  version: string | null;
  compose_version: string | null;
  error: string | null;
}

export interface HealthInfo {
  version: string;
  state_dir: string;
  engine: EngineInfo;
  projects: number;
  certs: number;
}

export interface ScanHit {
  name: string;
  compose_file: string;
  workdir: string;
  registered: boolean;
}

export interface ApiResult<T> {
  ok: boolean;
  data?: T;
  error?: string;
  code?: number;
}
