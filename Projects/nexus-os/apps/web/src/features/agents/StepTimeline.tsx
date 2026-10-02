import { Badge, cn } from "@nexus/ui";
import { ShieldAlert } from "lucide-react";
import { formatToolText, clip, parseStep, stepHeadline, type StepView } from "./format";

const OBS_TONE: Record<string, "success" | "danger" | "warning" | "neutral"> = {
  ok: "success",
  failed: "danger",
  invalid: "danger",
  denied: "danger",
  refused: "warning",
  interrupted: "warning",
  answered: "success",
};

function StepCard({ step }: { step: StepView }) {
  const obs = step.observation;
  return (
    <li className="relative pl-8">
      <span
        className="absolute left-0 top-0.5 grid size-6 place-items-center rounded-full border border-line-strong bg-raised font-mono text-[11px] text-fg-muted"
        aria-hidden="true"
      >
        {step.n}
      </span>
      <div className="rounded-lg border border-line bg-surface p-3">
        <p className="text-[13px] font-medium">
          {stepHeadline(step)}
          {step.kind === "tool_call" && obs ? (
            <Badge className="ml-2" tone={OBS_TONE[obs.status] ?? "neutral"}>
              {obs.status}
            </Badge>
          ) : null}
        </p>
        {step.summary ? <p className="mt-0.5 text-[13px] text-fg-muted">{step.summary}</p> : null}

        {step.kind === "tool_call" && step.args.length ? (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer select-none text-fg-subtle hover:text-fg">Arguments</summary>
            <dl className="mt-1.5 space-y-1">
              {step.args.map(([k, v]) => (
                <div key={k} className="grid grid-cols-[6rem_1fr] gap-2">
                  <dt className="truncate font-mono text-fg-subtle">{k}</dt>
                  <dd className="min-w-0 whitespace-pre-wrap break-words font-mono text-fg">{v}</dd>
                </div>
              ))}
            </dl>
          </details>
        ) : null}

        {step.kind === "ask_human" && step.question ? (
          <p className="mt-2 rounded-md bg-raised px-2.5 py-2 text-[13px]">{step.question}</p>
        ) : null}
        {step.kind === "finish" && step.resultSummary ? (
          <p className="mt-2 rounded-md bg-raised px-2.5 py-2 text-[13px]">
            {step.resultStatus && step.resultStatus !== "completed" ? <Badge className="mr-2">{step.resultStatus}</Badge> : null}
            {step.resultSummary}
          </p>
        ) : null}

        {obs && obs.text ? (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer select-none text-fg-subtle hover:text-fg">
              Result{obs.errorCode ? ` (${obs.errorCode})` : ""}
              {obs.untrusted ? " · outside content" : ""}
            </summary>
            {obs.flags.length ? (
              <p role="note" className="mt-1.5 flex items-center gap-1.5 text-warning">
                <ShieldAlert className="size-3.5" aria-hidden="true" />
                Contained text that looked like instructions ({obs.flags.join(", ")}). It was treated as data.
              </p>
            ) : null}
            <pre className={cn("mt-1.5 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md bg-canvas p-2 font-mono text-fg")}>
              {clip(formatToolText(obs.text), 4000)}
            </pre>
          </details>
        ) : null}

        {step.notes.map((n) => (
          <p key={n} className="mt-2 text-xs italic text-fg-subtle">
            Guidance sent to the agent: {n}
          </p>
        ))}
      </div>
    </li>
  );
}

export function StepTimeline({ steps }: { steps: unknown[] }) {
  const parsed = steps.map(parseStep).filter((s): s is StepView => s !== null);
  return (
    <ol aria-label="What the agent did" className="relative space-y-3 before:absolute before:bottom-2 before:left-3 before:top-2 before:w-px before:bg-line">
      {parsed.map((s) => (
        <StepCard key={s.n} step={s} />
      ))}
    </ol>
  );
}
