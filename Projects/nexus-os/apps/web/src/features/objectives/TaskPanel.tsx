import type { TaskNode } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, Textarea, toast } from "@nexus/ui";
import { ExternalLink, RotateCcw, SkipForward } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { errorMessage } from "../../lib/queries";
import { useTaskAction } from "../../lib/objectiveQueries";
import { KIND_LABEL, TASK_STATUS, needsOf } from "./format";

const rec = (v: unknown): Record<string, unknown> => (typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.map(rec) : []);
const s = (v: unknown) => (typeof v === "string" ? v : "");

function Needs({ task, objectiveId }: { task: TaskNode; objectiveId: string }) {
  const needs = needsOf(task);
  const act = useTaskAction(objectiveId);
  const [text, setText] = useState("");
  if (!needs.kind) return null;
  const send = (action: "retry" | "skip" | "answer", answer?: string) =>
    act.mutate(
      { taskId: task.id, action, ...(answer ? { text: answer } : {}) },
      {
        onSuccess: () => toast.success(action === "answer" ? "Sent. The agent is continuing." : action === "retry" ? "Retrying the task" : "Skipped; the rest continues"),
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  return (
    <div role="region" aria-label="Needs your decision" className="rounded-lg border border-warning/40 bg-warning/10 p-3">
      <p className="text-[11px] font-medium uppercase tracking-wider text-warning">{needs.kind === "question" ? "Question for you" : "Needs your decision"}</p>
      <p className="mt-1 text-sm text-fg">{needs.message}</p>
      {needs.kind === "question" ? (
        <>
          {needs.options.length ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {needs.options.map((o) => (
                <Button key={o} size="sm" disabled={act.isPending} onClick={() => send("answer", o)}>
                  {o}
                </Button>
              ))}
            </div>
          ) : null}
          <form
            className="mt-2 flex flex-col gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim()) send("answer", text.trim());
            }}
          >
            <label htmlFor={`answer-${task.id}`} className="sr-only">
              Your answer
            </label>
            <Textarea id={`answer-${task.id}`} rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your answer…" />
            <Button type="submit" size="sm" variant="primary" loading={act.isPending} disabled={!text.trim()} className="self-start">
              Send answer
            </Button>
          </form>
        </>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          <Button size="sm" variant="primary" loading={act.isPending} onClick={() => send("retry")}>
            <RotateCcw /> Retry
          </Button>
          <Button size="sm" disabled={act.isPending} onClick={() => send("skip")}>
            <SkipForward /> Skip it
          </Button>
          <p className="basis-full text-xs text-fg-muted">Skipping lets the tasks after it continue without its output.</p>
        </div>
      )}
    </div>
  );
}

export function TaskPanel({ task, objectiveId }: { task: TaskNode; objectiveId: string }) {
  const status = TASK_STATUS[task.status];
  const out = rec(task.outputs);
  const err = rec(task.error);
  const issues = list(out["issues"]);
  const outputs = list(out["outputs"]).filter((o) => s(o["value"]));
  const artifacts = list(out["artifacts"]);
  const criteria = list(out["criteria"]);
  return (
    <Card>
      <CardContent className="space-y-3 pt-4 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-fg-subtle">{task.key}</span>
          <Badge>{KIND_LABEL[task.kind] ?? task.kind}</Badge>
          <Badge tone={status.tone}>{status.label}</Badge>
          {task.approval_required ? <Badge tone="warning">Will ask for approval</Badge> : null}
          {task.optional ? <Badge>Optional</Badge> : null}
        </div>
        <div>
          <h3 className="text-sm font-semibold">{task.title}</h3>
          <p className="text-fg-muted">
            Assigned to <strong className="font-medium text-fg">{task.assigned_agent.replaceAll("_", " ")}</strong>
            {task.attempts > 1 ? ` · attempt ${task.attempts}` : ""}
            {task.started_at ? ` · started ${formatRelativeTime(task.started_at)}` : ""}
          </p>
        </div>
        {task.description ? <p className="whitespace-pre-wrap text-fg">{task.description}</p> : null}

        <Needs task={task} objectiveId={objectiveId} />

        {s(out["summary"]) ? (
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">{task.kind === "review" ? "Review" : "Result"}</p>
            <p className="mt-0.5 whitespace-pre-wrap">{s(out["summary"])}</p>
          </div>
        ) : null}
        {s(out["verdict"]) ? (
          <p>
            Verdict: <Badge tone={["approve", "PASS"].includes(s(out["verdict"])) ? "success" : s(out["verdict"]) === "FAIL" ? "danger" : "warning"}>{s(out["verdict"])}</Badge>
          </p>
        ) : null}
        {issues.length ? (
          <ul className="space-y-1.5" aria-label="Issues found">
            {issues.map((i, n) => (
              <li key={n} className="rounded-md bg-raised px-2.5 py-1.5">
                <Badge tone={["blocker", "major"].includes(s(i["severity"])) ? "danger" : "neutral"}>{s(i["severity"])}</Badge>{" "}
                {s(i["location"]) ? <span className="text-fg-subtle">{s(i["location"])}: </span> : null}
                {s(i["description"])}
                {s(i["suggestion"]) ? <span className="block text-xs text-fg-muted">Fix: {s(i["suggestion"])}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
        {criteria.length ? (
          <ul className="space-y-1" aria-label="Criteria checked">
            {criteria.map((c, n) => (
              <li key={n}>
                {c["met"] === true ? "✓" : "✗"} {s(c["criterion"])}
                {s(c["evidence"]) ? <span className="block text-xs text-fg-subtle">{s(c["evidence"])}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
        {outputs.length ? (
          <details>
            <summary className="cursor-pointer select-none text-fg-subtle hover:text-fg">Outputs ({outputs.length})</summary>
            {outputs.map((o, n) => (
              <p key={n} className="mt-1.5 whitespace-pre-wrap break-words rounded-md bg-canvas p-2 font-mono text-xs">
                <span className="text-fg-subtle">{s(o["name"])}: </span>
                {s(o["value"]).slice(0, 3000)}
              </p>
            ))}
          </details>
        ) : null}
        {artifacts.length ? (
          <p className="flex flex-wrap gap-2">
            {artifacts.map((a) => (
              <span key={s(a["artifact_id"])} className="rounded-md border border-line-strong bg-raised px-2 py-0.5">
                {s(a["name"])} <span className="text-fg-subtle">v{String(a["version"] ?? 1)}</span>
              </span>
            ))}
          </p>
        ) : null}
        {task.error && !needsOf(task).kind ? (
          <p className="text-xs text-fg-muted">
            {s(err["message"])}
            {s(err["reason"]) ? <span className="block">{s(err["reason"])}</span> : null}
          </p>
        ) : null}
        {task.run_id ? (
          <Link to={`/runs/${task.run_id}`} className="inline-flex items-center gap-1 text-accent-text hover:underline">
            See every step <ExternalLink className="size-3.5" aria-hidden="true" />
          </Link>
        ) : null}
      </CardContent>
    </Card>
  );
}
