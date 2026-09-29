import type { HealthCheck, PermissionLevel, UserSettings } from "@nexus/schemas";
import { formatBytes, formatDuration } from "@nexus/shared";
import { Badge, Button, Card, CardContent, EmptyState, ErrorState, FieldError, Input, Label, Skeleton, StatusDot, cn, toast, type StatusTone } from "@nexus/ui";
import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { NavLink, Outlet } from "react-router";
import { PERMISSION_COPY } from "../features/projects/permissions";
import { errorMessage, useHealth, useProjects, useSettings, useUpdateSettings, useVerifyEvents } from "../lib/queries";
import { Page, PageHeader } from "./Page";

const SETTINGS_NAV = [
  { to: "/settings", label: "General", end: true },
  { to: "/settings/health", label: "System health", end: false },
];

export function SettingsLayout() {
  return (
    <Page>
      <PageHeader title="Settings" />
      <div className="flex flex-col gap-6 md:flex-row">
        <nav aria-label="Settings" className="flex shrink-0 gap-1 overflow-x-auto md:sticky md:top-6 md:w-44 md:flex-col md:self-start">
          {SETTINGS_NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors",
                  isActive ? "bg-raised text-fg" : "text-fg-muted hover:bg-raised/60 hover:text-fg",
                )
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="min-w-0 flex-1">
          <Outlet />
        </div>
      </div>
    </Page>
  );
}

export function GeneralSettingsRoute() {
  const settings = useSettings();
  const projects = useProjects();
  if (settings.isPending) return <Skeleton className="h-64" />;
  if (settings.isError) return <ErrorState message={errorMessage(settings.error)} onRetry={() => void settings.refetch()} />;
  return <GeneralSettingsForm settings={settings.data} locked={(projects.data?.length ?? 0) > 0} />;
}

function GeneralSettingsForm({ settings, locked }: { settings: UserSettings; locked: boolean }) {
  const update = useUpdateSettings();
  const [name, setName] = useState(settings.display_name);
  const [root, setRoot] = useState(settings.workspace_root);
  const [level, setLevel] = useState<PermissionLevel>(settings.default_permission_level);

  function save(e: FormEvent) {
    e.preventDefault();
    update.mutate(
      {
        display_name: name.trim(),
        default_permission_level: level,
        ...(locked ? {} : { workspace_root: root.trim() }),
      },
      {
        onSuccess: () => toast.success("Settings saved"),
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  }

  return (
    <form onSubmit={save} className="space-y-6">
      <Card>
        <CardContent className="space-y-4 pt-4">
          <div>
            <Label htmlFor="display-name">Your name</Label>
            <Input id="display-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="Used in greetings" />
          </div>
          <div>
            <Label htmlFor="workspace-root">Workspace folder</Label>
            <Input id="workspace-root" value={root} disabled={locked} onChange={(e) => setRoot(e.target.value)} className="font-mono text-[13px]" />
            <p className="mt-1.5 text-xs text-fg-muted">
              {locked
                ? "Fixed once projects exist, because their files live inside it."
                : "Agents can only read and write inside this folder. Choose it before creating projects."}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-4">
          <fieldset>
            <legend className="mb-1 text-[13px] font-medium text-fg-muted">Default permission level</legend>
            <p className="mb-3 text-xs text-fg-muted">Applies to every project unless it sets its own. Very high-risk actions always ask.</p>
            <div className="space-y-2">
              {(Object.keys(PERMISSION_COPY) as PermissionLevel[]).map((k) => (
                <label
                  key={k}
                  className={cn(
                    "flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors",
                    level === k ? "border-accent bg-accent/10" : "border-line hover:border-line-strong",
                  )}
                >
                  <input type="radio" name="permission" value={k} checked={level === k} onChange={() => setLevel(k)} className="mt-1 accent-[var(--nx-accent)]" />
                  <span>
                    <span className="block text-sm font-medium">{PERMISSION_COPY[k].label}</span>
                    <span className="block text-xs text-fg-muted">{PERMISSION_COPY[k].help}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </CardContent>
      </Card>

      <FieldError>{update.isError ? errorMessage(update.error) : undefined}</FieldError>
      <Button type="submit" variant="primary" loading={update.isPending}>
        Save changes
      </Button>
    </form>
  );
}

const TONE: Record<string, StatusTone> = { ok: "ok", degraded: "warn", down: "bad", unavailable: "idle" };

function detailRows(c: HealthCheck): [string, string][] {
  const d = c.data as Record<string, unknown>;
  const rows: [string, string][] = [];
  const num = (k: string) => (typeof d[k] === "number" ? (d[k] as number) : undefined);
  if (c.name === "backend") {
    if (num("uptime_s") !== undefined) rows.push(["Uptime", formatDuration(num("uptime_s")!)]);
    rows.push(["Bind", String(d["bind"] ?? "")], ["Python", String(d["python"] ?? "")]);
  }
  if (c.name === "database") {
    if (num("size_bytes") !== undefined) rows.push(["Size", formatBytes(num("size_bytes")!)]);
    if (d["path"]) rows.push(["File", String(d["path"])]);
  }
  if (c.name === "disk") {
    rows.push(["Free", formatBytes(num("free") ?? 0)], ["Workspace", formatBytes(num("workspace_bytes") ?? 0)]);
  }
  if (c.name === "queue") {
    rows.push(["Running", String(num("running") ?? 0)], ["Pending", String(num("pending") ?? 0)], ["Failed", String(num("failed") ?? 0)]);
  }
  if (c.name === "events") {
    rows.push(["Live subscribers", String(num("live_subscribers") ?? 0)]);
  }
  return rows;
}

export function HealthRoute() {
  const health = useHealth(5_000);
  const verify = useVerifyEvents();

  if (health.isPending) return <Skeleton className="h-64" />;
  if (health.isError)
    return <ErrorState title="Backend unreachable" message={errorMessage(health.error)} onRetry={() => void health.refetch()} />;

  const report = health.data;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={report.status === "ok" ? "success" : report.status === "degraded" ? "warning" : "danger"}>
          {report.status === "ok" ? "All systems normal" : report.status}
        </Badge>
        <span className="text-xs text-fg-muted">NEXUS API v{report.version} · refreshes every few seconds</span>
      </div>
      <ul className="space-y-2">
        {report.checks.map((c) => {
          const rows = detailRows(c);
          return (
            <li key={c.name}>
              <Card>
                <CardContent className="pt-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-1.5">
                      <StatusDot tone={TONE[c.status] ?? "idle"} label={c.status} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-3">
                        <h3 className="text-sm font-medium">{c.label}</h3>
                        <span className="text-xs text-fg-subtle">{c.status}</span>
                      </div>
                      <p className="text-[13px] text-fg-muted">{c.detail}</p>
                      {rows.length ? (
                        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-xs">
                          {rows.map(([k, v]) => (
                            <div key={k} className="contents">
                              <dt className="text-fg-subtle">{k}</dt>
                              <dd className="min-w-0 break-all font-mono text-fg-muted">{v}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : null}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ul>
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-4">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-medium">
              <ShieldCheck className="size-4 text-fg-subtle" aria-hidden="true" />
              Audit log integrity
            </h3>
            <p className="text-[13px] text-fg-muted">Recomputes the hash chain over every recorded event.</p>
            {verify.data ? (
              <p className={cn("mt-1 text-[13px]", verify.data.ok ? "text-success" : "text-danger")} role="status">
                {verify.data.ok
                  ? `Verified ${verify.data.events_checked} events across ${verify.data.chains_checked} chain(s).`
                  : `Chain broken at event #${verify.data.first_bad_seq}.`}
              </p>
            ) : null}
            {verify.isError ? <FieldError>{errorMessage(verify.error)}</FieldError> : null}
          </div>
          <Button loading={verify.isPending} onClick={() => verify.mutate()}>
            Verify now
          </Button>
        </CardContent>
      </Card>
      {report.checks.length === 0 ? <EmptyState title="No checks registered" /> : null}
    </div>
  );
}
