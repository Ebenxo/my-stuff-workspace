import { formatDuration, formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton, Textarea, toast } from "@nexus/ui";
import { Ban, ChevronLeft, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApprovalCard } from "../features/approvals/ApprovalCard";
import { RUN_STATUS, RISK, TOOL_STATUS, runDuration, totalTokens } from "../features/agents/format";
import { StepTimeline } from "../features/agents/StepTimeline";
import {
  isNotFound,
  useAgents,
  useAnswerRun,
  useApprovals,
  useCancelRun,
  useResumeRun,
  useRun,
} from "../lib/agentQueries";
import { errorMessage, useProject } from "../lib/queries";
import { Page, PageHeader, Section } from "./Page";

function Answer({ runId, question, options }: { runId: string; question: string; options: string[] }) {
  const answer = useAnswerRun(runId);
  const [text, setText] = useState("");
  function send(value: string) {
    answer.mutate(value, {
      onSuccess: () => {
        setText("");
        toast.success("Sent. The agent is continuing.");
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  }
  return (
    <Card className="mb-6 border-warning/40">
      <CardHeader>
        <CardTitle>The agent has a question</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{question}</p>
        {options.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {options.map((o) => (
              <Button key={o} size="sm" disabled={answer.isPending} onClick={() => send(o)}>
                {o}
              </Button>
            ))}
          </div>
        ) : null}
        <form
          className="mt-3 flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) send(text.trim());
          }}
        >
          <label htmlFor="answer" className="sr-only">
            Your answer
          </label>
          <Textarea id="answer" value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder="Type your answer…" />
          <Button type="submit" variant="primary" loading={answer.isPending} disabled={!text.trim()} className="sm:self-end">
            Send answer
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function RunRoute() {
  const { runId = "" } = useParams();
  const detail = useRun(runId);
  const agents = useAgents();
  const run = detail.data?.run;
  const project = useProject(run?.project_id ?? "");
  const approvals = useApprovals("PENDING", run?.project_id ?? undefined);
  const cancel = useCancelRun();
  const resume = useResumeRun();

  if (detail.isPending) {
    return (
      <Page>
        <Skeleton className="mb-3 h-8 w-72" />
        <Skeleton className="h-48" />
      </Page>
    );
  }
  if (detail.isError) {
    return (
      <Page>
        {isNotFound(detail.error) ? (
          <EmptyState
            title="Run not found"
            description="It may have been removed, or the link is wrong."
            action={
              <Button asChild variant="primary">
                <Link to="/agents">Back to agents</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState message={errorMessage(detail.error)} onRetry={() => void detail.refetch()} />
        )}
      </Page>
    );
  }

  const { run: r, steps, tool_calls: calls } = detail.data;
  const agent = agents.data?.find((a) => a.id === r.agent_id);
  const status = RUN_STATUS[r.status];
  const waitingQuestion =
    r.status === "WAITING_INPUT" && r.result && typeof r.result["question"] === "string" ? String(r.result["question"]) : undefined;
  const options = Array.isArray(r.result?.["options"]) ? (r.result["options"] as unknown[]).filter((o): o is string => typeof o === "string") : [];
  const mine = (approvals.data ?? []).filter((a) => a.run_id === r.id);
  const canResume = r.status === "INTERRUPTED" || r.status === "FAILED" || r.status === "TIMED_OUT";
  const result = r.result && typeof r.result["summary"] === "string" ? r.result : undefined;
  const artifacts = Array.isArray(result?.["artifacts"]) ? (result["artifacts"] as { artifact_id: string; name: string; version: number }[]) : [];
  const errors = Array.isArray(result?.["errors"]) ? (result["errors"] as unknown[]).filter((e): e is string => typeof e === "string") : [];

  return (
    <Page>
      <p className="mb-3">
        <Link to={r.project_id ? `/projects/${r.project_id}` : "/agents"} className="inline-flex items-center gap-1 text-[13px] text-fg-muted hover:text-fg">
          <ChevronLeft className="size-4" aria-hidden="true" />
          {project.data?.name ?? "Back"}
        </Link>
      </p>
      <PageHeader
        title={agent?.name ?? "Agent run"}
        description={r.prompt || undefined}
        badges={<Badge tone={status.tone}>{status.label}</Badge>}
        actions={
          <>
            {status.live ? (
              <Button
                size="sm"
                variant="danger"
                loading={cancel.isPending}
                onClick={() => cancel.mutate(r.id, { onSuccess: () => toast.success("Run cancelled"), onError: (e) => toast.error(errorMessage(e)) })}
              >
                <Ban /> Cancel run
              </Button>
            ) : null}
            {canResume ? (
              <Button
                size="sm"
                variant="primary"
                loading={resume.isPending}
                onClick={() => resume.mutate(r.id, { onSuccess: () => toast.success("Resumed from where it stopped"), onError: (e) => toast.error(errorMessage(e)) })}
              >
                <RotateCcw /> Resume
              </Button>
            ) : null}
          </>
        }
      />

      <dl className="mb-6 flex flex-wrap gap-x-6 gap-y-1 text-xs text-fg-subtle">
        <div className="flex gap-1.5">
          <dt>Started</dt>
          <dd className="text-fg-muted">{formatRelativeTime(r.started_at)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Time</dt>
          <dd className="text-fg-muted">{formatDuration(runDuration(r))}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Steps</dt>
          <dd className="text-fg-muted">{r.step_count}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt>Tokens</dt>
          <dd className="text-fg-muted">{totalTokens(r).toLocaleString()}</dd>
        </div>
        {r.model ? (
          <div className="flex gap-1.5">
            <dt>Model</dt>
            <dd className="font-mono text-fg-muted">{r.model}</dd>
          </div>
        ) : null}
        {r.attempt > 1 ? (
          <div className="flex gap-1.5">
            <dt>Attempt</dt>
            <dd className="text-fg-muted">{r.attempt}</dd>
          </div>
        ) : null}
      </dl>

      {waitingQuestion ? <Answer runId={r.id} question={waitingQuestion} options={options} /> : null}

      {mine.length ? (
        <Section title="Waiting for your approval">
          <ul className="space-y-3">
            {mine.map((a) => (
              <li key={a.id}>
                <ApprovalCard approval={a} agentName={agent?.name} />
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {r.error ? (
        <div role="alert" className="mb-6 rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-[13px]">
          <p className="font-medium text-danger">{status.label}</p>
          <p className="mt-0.5 text-fg">{String(r.error["message"] ?? "The run did not finish.")}</p>
          {r.error["category"] ? <p className="mt-1 text-xs text-fg-subtle">Category: {String(r.error["category"]).toLowerCase().replaceAll("_", " ")}</p> : null}
        </div>
      ) : null}

      {result ? (
        <Section title="Result">
          <Card>
            <CardContent className="pt-4">
              <p className="whitespace-pre-wrap text-sm">{String(result["summary"])}</p>
              {errors.length ? (
                <ul className="mt-2 list-disc pl-5 text-[13px] text-danger">
                  {errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              ) : null}
              {artifacts.length ? (
                <div className="mt-3">
                  <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">Saved</p>
                  <ul className="mt-1 flex flex-wrap gap-2">
                    {artifacts.map((a) => (
                      <li key={a.artifact_id}>
                        <Link to={`/projects/${r.project_id}?tab=artifacts&artifact=${a.artifact_id}`} className="rounded-md border border-line-strong bg-raised px-2 py-1 text-[13px] hover:bg-overlay">
                          {a.name} <span className="text-fg-subtle">v{a.version}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </CardContent>
          </Card>
        </Section>
      ) : null}

      <Section title={`What it did (${steps.length})`}>
        {steps.length === 0 ? <p className="text-[13px] text-fg-muted">Getting started…</p> : <StepTimeline steps={steps} />}
      </Section>

      {calls.length ? (
        <Section title="Tool calls">
          <Card>
            <ul className="divide-y divide-line text-[13px]">
              {calls.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
                  <code className="font-mono text-xs">{c.tool_name}</code>
                  <Badge tone={TOOL_STATUS[c.status].tone}>{TOOL_STATUS[c.status].label}</Badge>
                  <Badge tone={RISK[c.risk_level].tone}>{RISK[c.risk_level].label}</Badge>
                  {c.duration_ms != null ? <span className="font-mono text-[11px] text-fg-subtle">{c.duration_ms} ms</span> : null}
                  {c.error ? <span className="min-w-0 truncate text-xs text-danger">{String(c.error["message"] ?? "")}</span> : null}
                </li>
              ))}
            </ul>
          </Card>
        </Section>
      ) : null}
    </Page>
  );
}
