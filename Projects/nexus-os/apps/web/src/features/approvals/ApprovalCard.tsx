import type { Approval } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, FieldError, Textarea, Tooltip, cn, toast } from "@nexus/ui";
import { Check, Pencil, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../../lib/queries";
import { useDecideApproval } from "../../lib/agentQueries";
import { RISK, parseArgumentsJson, prettyArgs } from "../agents/format";

interface Props {
  approval: Approval;
  agentName?: string | undefined;
  /** History rows show the decision instead of the buttons. */
  readOnly?: boolean;
}

const DECIDED_LABEL: Record<string, { label: string; tone: "success" | "danger" | "neutral" | "warning" }> = {
  APPROVED_ONCE: { label: "Approved once", tone: "success" },
  APPROVED_SESSION: { label: "Approved for session", tone: "success" },
  DENIED: { label: "Denied", tone: "danger" },
  EXPIRED: { label: "Expired", tone: "neutral" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
};

export function ApprovalCard({ approval, agentName, readOnly }: Props) {
  const decide = useDecideApproval();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(approval.arguments, null, 2));
  const [editError, setEditError] = useState<string | undefined>();
  const risk = RISK[approval.risk_level];
  const pending = approval.status === "PENDING" && !readOnly;
  const args = prettyArgs(approval.edited_arguments ?? approval.arguments);

  function send(decision: "approve_once" | "approve_session" | "deny", edited?: Record<string, unknown>) {
    decide.mutate(
      { id: approval.id, decision: { decision, ...(edited ? { edited_arguments: edited } : {}) } },
      {
        onSuccess: () => {
          setEditing(false);
          toast.success(decision === "deny" ? "Denied. The agent will be told." : "Approved. The agent is continuing.");
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  function approveEdited() {
    const parsed = parseArgumentsJson(draft);
    if (!parsed.ok) {
      setEditError(parsed.error);
      return;
    }
    setEditError(undefined);
    send("approve_once", parsed.value);
  }

  const decided = DECIDED_LABEL[approval.status];

  return (
    <article
      aria-label={`Approval request: ${approval.tool_name}`}
      className={cn(
        "rounded-lg border bg-surface p-3 text-[13px]",
        pending ? "border-warning/40" : "border-line",
        approval.risk_level === "VERY_HIGH" && pending && "border-danger/50",
      )}
    >
      <header className="flex flex-wrap items-center gap-2">
        <Badge tone={risk.tone}>{risk.label} risk</Badge>
        <code className="rounded bg-raised px-1.5 py-0.5 font-mono text-xs">{approval.tool_name}</code>
        <span className="ml-auto text-xs text-fg-subtle">{formatRelativeTime(approval.created_at)}</span>
      </header>

      <p className="mt-2 text-fg">
        <strong className="font-medium">{agentName ?? "An agent"}</strong> wants to run this
        {approval.reason ? <span className="text-fg-muted">: {approval.reason}</span> : null}
      </p>

      <p className="mt-2 rounded-md bg-raised px-2.5 py-2 text-fg">
        <span className="mb-0.5 block text-[11px] font-medium uppercase tracking-wider text-fg-subtle">What will happen</span>
        {approval.impact}
      </p>

      {approval.tainted ? (
        <p role="note" className="mt-2 flex gap-2 rounded-md border border-warning/30 bg-warning/10 px-2.5 py-2 text-warning">
          <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>
            This run has read outside content ({approval.taint_sources.slice(0, 3).join(", ")}). What the agent is asking for may have
            been influenced by it. Check the details before approving.
          </span>
        </p>
      ) : null}

      {!editing ? (
        <dl className="mt-2 space-y-1">
          {args.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[6rem_1fr] gap-2">
              <dt className="truncate font-mono text-xs text-fg-subtle">{k}</dt>
              <dd className="min-w-0 whitespace-pre-wrap break-words font-mono text-xs text-fg">{v}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <div className="mt-2">
          <label htmlFor={`edit-${approval.id}`} className="mb-1 block text-xs font-medium text-fg-muted">
            Edit the arguments (JSON)
          </label>
          <Textarea
            id={`edit-${approval.id}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
            spellCheck={false}
            className="font-mono text-xs"
            aria-invalid={!!editError}
          />
          <FieldError>{editError}</FieldError>
          <p className="mt-1 text-xs text-fg-subtle">Your version is checked and re-assessed for safety before anything runs.</p>
        </div>
      )}

      {pending ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {editing ? (
            <>
              <Button size="sm" variant="primary" loading={decide.isPending} onClick={approveEdited}>
                <Check /> Approve with changes
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(false);
                  setEditError(undefined);
                }}
              >
                Cancel edit
              </Button>
            </>
          ) : (
            <>
              <Button size="sm" variant="primary" loading={decide.isPending} onClick={() => send("approve_once")}>
                <Check /> Approve once
              </Button>
              {approval.session_grantable ? (
                <Tooltip label="Stop asking about this tool in this project until NEXUS restarts" side="top">
                  <Button size="sm" disabled={decide.isPending} onClick={() => send("approve_session")}>
                    <ShieldCheck /> For this session
                  </Button>
                </Tooltip>
              ) : null}
              <Button size="sm" disabled={decide.isPending} onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
              <Button size="sm" variant="danger" disabled={decide.isPending} onClick={() => send("deny")}>
                <X /> Deny
              </Button>
            </>
          )}
          {!approval.session_grantable && !editing ? (
            <p className="basis-full text-xs text-fg-subtle">This kind of action always asks; it can’t be approved for a whole session.</p>
          ) : null}
        </div>
      ) : decided ? (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
          <Badge tone={decided.tone}>{decided.label}</Badge>
          {approval.edited_arguments ? <Badge tone="info">Edited</Badge> : null}
          {approval.decision_note ? <span>“{approval.decision_note}”</span> : null}
        </p>
      ) : null}
    </article>
  );
}
