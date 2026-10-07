import type { AgentMessage } from "@nexus/schemas";
import { cn } from "@nexus/ui";
import { formatClock } from "../events/describe";
import { MESSAGE_LABEL, agentName, messageText } from "./format";

const TONE: Partial<Record<AgentMessage["type"], string>> = {
  QUESTION: "border-l-warning",
  ERROR: "border-l-danger",
  REVIEW_RESULT: "border-l-info",
  TASK_RESULT: "border-l-success",
};

/**
 * How the agents handed work to each other. These are structured records (who, to whom, what kind,
 * a short summary); agents' private reasoning is never part of them.
 */
export function MessageFeed({ messages, onSelectTask }: { messages: AgentMessage[]; onSelectTask?: (taskId: string) => void }) {
  if (!messages.length) return <p className="px-3 py-4 text-[13px] text-fg-muted">No hand-offs yet.</p>;
  return (
    <ol className="divide-y divide-line" aria-label="Agent messages">
      {messages.map((m) => {
        const text = messageText(m);
        return (
          <li key={m.id} className={cn("border-l-2 border-l-transparent px-3 py-2 text-[13px]", TONE[m.type])}>
            <p className="flex flex-wrap items-baseline gap-x-1.5">
              <strong className="font-medium capitalize">{agentName(m.sender)}</strong>
              <span className="text-fg-muted">{MESSAGE_LABEL[m.type]}</span>
              {m.recipient !== "orchestrator" || m.type === "TASK_REQUEST" ? (
                <span className="text-fg-muted">
                  → <span className="capitalize">{agentName(m.recipient)}</span>
                </span>
              ) : null}
              <time dateTime={m.timestamp} className="ml-auto font-mono text-[11px] text-fg-subtle">
                {formatClock(m.timestamp)}
              </time>
            </p>
            {text ? (
              m.task_id && onSelectTask ? (
                <button type="button" onClick={() => onSelectTask(m.task_id!)} className="mt-0.5 text-left text-fg hover:underline">
                  {text}
                </button>
              ) : (
                <p className="mt-0.5 text-fg">{text}</p>
              )
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
