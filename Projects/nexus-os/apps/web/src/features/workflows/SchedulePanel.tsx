import type { Schedule, Workflow } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, FieldError, Input, Label, Select, Switch, toast } from "@nexus/ui";
import { CalendarClock, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { errorMessage } from "../../lib/queries";
import { useCronPreview, useScheduleMutations, useSchedules } from "../../lib/workflowQueries";
import { PRESETS, inputDefaults, inputValues } from "./model";


const localZone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
};

function ScheduleRow({ s }: { s: Schedule }) {
  const m = useScheduleMutations();
  const onError = (e: unknown) => toast.error(errorMessage(e));
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5 text-[13px]">
      <CalendarClock className="size-4 text-fg-subtle" aria-hidden="true" />
      <span className="min-w-0 flex-1 basis-48">
        <span className="font-medium">{s.description}</span>{" "}
        <span className="font-mono text-xs text-fg-subtle">
          {s.cron} · {s.timezone}
        </span>
        <span className="block text-xs text-fg-muted">
          {s.enabled && s.next_run_at ? `Next ${formatRelativeTime(s.next_run_at)}` : "Off"}
          {s.last_run_at ? ` · last ${formatRelativeTime(s.last_run_at)}` : ""}
          {s.last_status ? ` (${s.last_status.toLowerCase().replaceAll("_", " ")})` : ""}
          {s.last_run_id ? (
            <>
              {" · "}
              <Link to={`/workflow-runs/${s.last_run_id}`} className="text-accent-text hover:underline">
                last run
              </Link>
            </>
          ) : null}
        </span>
      </span>
      <Switch
        checked={s.enabled}
        onCheckedChange={(enabled) => m.update.mutate({ id: s.id, body: { enabled } }, { onError })}
        aria-label={`Schedule ${s.description} is on`}
      />
      <Button size="sm" variant="ghost" disabled={m.runNow.isPending} onClick={() => m.runNow.mutate(s.id, { onSuccess: () => toast.success("Started"), onError })}>
        <Play /> Run now
      </Button>
      <Button size="icon-sm" variant="ghost" aria-label="Delete schedule" onClick={() => m.remove.mutate(s.id, { onSuccess: () => toast.success("Schedule deleted"), onError })}>
        <Trash2 />
      </Button>
    </li>
  );
}

export function SchedulePanel({ workflow }: { workflow: Workflow }) {
  const schedules = useSchedules(workflow.id);
  const m = useScheduleMutations();
  const inputs = workflow.definition.inputs ?? [];
  const [cronText, setCron] = useState(PRESETS[1]!.cron);
  const [tz, setTz] = useState(localZone);
  const [form, setForm] = useState(() => inputDefaults(inputs));
  const preview = useCronPreview(cronText, tz);

  return (
    <div className="space-y-4">
      <p className="text-[13px] text-fg-muted">
        Scheduled runs happen while NEXUS is open; a time missed while it was closed runs once when it starts. They are unattended: anything
        risky waits for your approval, and a run is skipped while the previous one is still going.
      </p>
      {schedules.data?.length ? (
        <ul className="divide-y divide-line rounded-lg border border-line" aria-label="Schedules">
          {schedules.data.map((s) => (
            <ScheduleRow key={s.id} s={s} />
          ))}
        </ul>
      ) : null}
      <form
        className="space-y-3 rounded-lg border border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          m.create.mutate(
            { workflow_id: workflow.id, cron: cronText, timezone: tz, inputs: inputValues(inputs, form) },
            { onSuccess: () => toast.success("Scheduled") },
          );
        }}
      >
        <p className="text-[13px] font-medium">Add a schedule</p>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <Button key={p.cron} size="sm" variant={cronText === p.cron ? "primary" : "ghost"} onClick={() => setCron(p.cron)}>
              {p.label}
            </Button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="sch-cron">Cron (minute hour day month weekday)</Label>
            <Input id="sch-cron" className="font-mono" value={cronText} onChange={(e) => setCron(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="sch-tz">Time zone</Label>
            <Select id="sch-tz" value={tz} onChange={(e) => setTz(e.target.value)}>
              {[...new Set([localZone(), "UTC", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Asia/Tokyo", "Australia/Sydney"])].map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <p className="text-xs text-fg-muted" aria-live="polite">
          {preview.isError ? (
            <span className="text-danger">{errorMessage(preview.error)}</span>
          ) : preview.data ? (
            <>
              <strong className="font-medium text-fg">{preview.data.description}.</strong> Next:{" "}
              {preview.data.next_runs.slice(0, 3).map((t) => new Date(t).toLocaleString()).join(" · ")}
            </>
          ) : null}
        </p>
        {inputs.map((i) =>
          i.type === "boolean" ? (
            <label key={i.name} className="flex items-center gap-2 text-[13px]">
              <Switch checked={form[i.name] === true} onCheckedChange={(v) => setForm({ ...form, [i.name]: v })} aria-label={i.name} />
              {i.name}
            </label>
          ) : (
            <div key={i.name}>
              <Label htmlFor={`sch-in-${i.name}`}>{i.name}</Label>
              <Input id={`sch-in-${i.name}`} value={String(form[i.name] ?? "")} onChange={(e) => setForm({ ...form, [i.name]: e.target.value })} />
            </div>
          ),
        )}
        <FieldError>{m.create.isError ? errorMessage(m.create.error) : undefined}</FieldError>
        <div className="flex items-center gap-2">
          <Button type="submit" size="sm" variant="primary" loading={m.create.isPending} disabled={preview.isError}>
            Add schedule
          </Button>
          {!workflow.enabled ? <Badge tone="warning">This workflow is turned off</Badge> : null}
        </div>
      </form>
    </div>
  );
}
