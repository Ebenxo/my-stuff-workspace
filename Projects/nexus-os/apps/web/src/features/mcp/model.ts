import type { McpServer, McpServerCreate, McpServerUpdate, McpStatus, McpTransport, RiskLevel } from "@nexus/schemas";
import type { Tone } from "../events/describe";

export const MCP_STATUS: Record<McpStatus, { label: string; tone: Tone }> = {
  running: { label: "Running", tone: "success" },
  starting: { label: "Starting", tone: "accent" },
  stopped: { label: "Stopped", tone: "neutral" },
  error: { label: "Problem", tone: "danger" },
};

/** Risk levels a server's tools may have. Safe is not offered: MCP tools act outside NEXUS's own checks. */
export const MCP_RISKS: RiskLevel[] = ["MODERATE", "HIGH", "VERY_HIGH"];

export const SERVER_NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]{0,59}$/;
const HEADER_NAME = /^[A-Za-z0-9][A-Za-z0-9-]{0,59}$/;

export interface Pair {
  key: string;
  value: string;
}

/** A secret row. ``saved`` rows already have a value stored; leaving ``value`` empty keeps it. */
export interface SecretRow extends Pair {
  saved: boolean;
}

export interface ServerForm {
  name: string;
  description: string;
  transport: McpTransport;
  command: string;
  args: string; // one per line
  cwd: string;
  env: Pair[];
  secretEnv: SecretRow[];
  url: string;
  headers: Pair[];
  secretHeaders: SecretRow[];
  riskLevel: RiskLevel;
  timeout: string;
  enabled: boolean;
}

export const EMPTY_FORM: ServerForm = {
  name: "",
  description: "",
  transport: "stdio",
  command: "",
  args: "",
  cwd: "",
  env: [],
  secretEnv: [],
  url: "",
  headers: [],
  secretHeaders: [],
  riskLevel: "HIGH",
  timeout: "60",
  enabled: true,
};

const pairs = (r: Record<string, string>): Pair[] => Object.entries(r).map(([key, value]) => ({ key, value }));
const saved = (names: string[]): SecretRow[] => names.map((key) => ({ key, value: "", saved: true }));

export function toForm(s: McpServer): ServerForm {
  return {
    name: s.name,
    description: s.description,
    transport: s.transport,
    command: s.command,
    args: s.args.join("\n"),
    cwd: s.cwd ?? "",
    env: pairs(s.env),
    secretEnv: saved(s.secret_env),
    url: s.url,
    headers: pairs(s.headers),
    secretHeaders: saved(s.secret_headers),
    riskLevel: s.risk_level,
    timeout: String(s.timeout_s),
    enabled: s.enabled,
  };
}

export function argsFromText(text: string): string[] {
  return text
    .split("\n")
    .map((a) => a.trim())
    .filter(Boolean);
}

function record(rows: Pair[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) if (r.key.trim()) out[r.key.trim()] = r.value;
  return out;
}

export type FormErrors = Partial<Record<"name" | "command" | "url" | "env" | "headers" | "timeout", string>>;

function checkNames(plain: Pair[], secret: SecretRow[], pattern: RegExp, label: string): string | undefined {
  const seen = new Set<string>();
  for (const r of [...plain, ...secret]) {
    const key = r.key.trim();
    if (!key) continue;
    if (!pattern.test(key)) return `“${key}” is not a valid ${label} name.`;
    if (seen.has(key.toLowerCase())) return `${key} is listed twice.`;
    seen.add(key.toLowerCase());
  }
  const missing = secret.find((r) => r.key.trim() && !r.saved && !r.value);
  return missing ? `Enter the secret value for ${missing.key.trim()}.` : undefined;
}

export function validateForm(f: ServerForm, creating: boolean): FormErrors {
  const e: FormErrors = {};
  if (creating && !SERVER_NAME.test(f.name)) e.name = "Use lowercase letters, digits and hyphens (up to 40), e.g. “github”.";
  const timeout = Number(f.timeout);
  if (!Number.isFinite(timeout) || timeout < 1 || timeout > 600) e.timeout = "Between 1 and 600 seconds.";
  if (f.transport === "stdio") {
    if (!f.command.trim()) e.command = "Give the command that starts the server, e.g. npx or uvx.";
    const env = checkNames(f.env, f.secretEnv, ENV_NAME, "variable");
    if (env) e.env = env;
  } else {
    if (!/^https?:\/\/\S+$/.test(f.url.trim())) e.url = "Enter the server's address, starting with https://.";
    const headers = checkNames(f.headers, f.secretHeaders, HEADER_NAME, "header");
    if (headers) e.headers = headers;
  }
  return e;
}

function newSecrets(rows: SecretRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) if (r.key.trim() && r.value) out[r.key.trim()] = r.value;
  return out;
}

export function toCreate(f: ServerForm): McpServerCreate {
  const base = {
    name: f.name.trim(),
    description: f.description.trim(),
    transport: f.transport,
    risk_level: f.riskLevel,
    timeout_s: Number(f.timeout),
    enabled: f.enabled,
  };
  if (f.transport === "stdio") {
    return {
      ...base,
      command: f.command.trim(),
      args: argsFromText(f.args),
      cwd: f.cwd.trim() || null,
      env: record(f.env),
      secret_env: newSecrets(f.secretEnv),
    };
  }
  return { ...base, url: f.url.trim(), headers: record(f.headers), secret_headers: newSecrets(f.secretHeaders) };
}

function secretChanges(before: string[], rows: SecretRow[]): Record<string, string | null> | undefined {
  const out: Record<string, string | null> = {};
  const kept = new Set(rows.filter((r) => r.saved).map((r) => r.key));
  for (const name of before) if (!kept.has(name)) out[name] = null; // removed
  for (const [k, v] of Object.entries(newSecrets(rows))) out[k] = v; // new or replaced
  return Object.keys(out).length ? out : undefined;
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Only what changed. Secret values are sent only when typed; a removed saved secret is sent as null. */
export function toUpdate(s: McpServer, f: ServerForm): McpServerUpdate {
  const next = toCreate(f);
  const patch: McpServerUpdate = {};
  if (next.description !== s.description) patch.description = next.description ?? "";
  if (next.risk_level !== s.risk_level) patch.risk_level = next.risk_level ?? "HIGH";
  if (next.timeout_s !== s.timeout_s) patch.timeout_s = next.timeout_s ?? 60;
  if (next.enabled !== s.enabled) patch.enabled = next.enabled ?? true;
  if (f.transport === "stdio") {
    if (next.command !== s.command) patch.command = next.command ?? "";
    if (!same(next.args, s.args)) patch.args = next.args ?? [];
    if ((next.cwd ?? null) !== (s.cwd ?? null)) patch.cwd = next.cwd ?? "";
    if (!same(next.env, s.env)) patch.env = next.env ?? {};
    const secrets = secretChanges(s.secret_env, f.secretEnv);
    if (secrets) patch.secret_env = secrets;
  } else {
    if (next.url !== s.url) patch.url = next.url ?? "";
    if (!same(next.headers, s.headers)) patch.headers = next.headers ?? {};
    const secrets = secretChanges(s.secret_headers, f.secretHeaders);
    if (secrets) patch.secret_headers = secrets;
  }
  return patch;
}

/** What starts the server, in one line. */
export function launchLine(s: Pick<McpServer, "transport" | "command" | "args" | "url">): string {
  if (s.transport === "http") return s.url;
  const quoted = s.args.map((a) => (/\s/.test(a) ? `"${a}"` : a));
  return [s.command, ...quoted].join(" ");
}

export function countLine(s: Pick<McpServer, "tools" | "resources" | "prompts">): string {
  const n = (count: number | undefined, one: string) => `${count ?? 0} ${one}${count === 1 ? "" : "s"}`;
  return [n(s.tools, "tool"), n(s.resources, "resource"), n(s.prompts, "prompt")].join(" · ");
}
