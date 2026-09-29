import type { MemoryItem, ScoreBreakdown } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Tooltip, cn, toast } from "@nexus/ui";
import { Check, Pencil, Pin, PinOff, RotateCcw, Trash2, Undo2, X } from "lucide-react";
import { useMemoryAction, useUpdateMemory, type MemoryAction } from "../../lib/memoryQueries";
import { errorMessage } from "../../lib/queries";
import { explainScore, flagsOf, provenance } from "./format";

const DONE: Record<MemoryAction, string> = {
  confirm: "Kept",
  dismiss: "Dismissed",
  restore: "Restored",
  delete: "Deleted. You can restore it from Deleted.",
  purge: "Erased for good",
  "undo-compression": "Original notes restored",
};

export function MemoryCard({
  item,
  score,
  highlighted,
  onEdit,
}: {
  item: MemoryItem;
  score?: ScoreBreakdown | undefined;
  highlighted?: boolean;
  onEdit?: (item: MemoryItem) => void;
}) {
  const act = useMemoryAction();
  const update = useUpdateMemory();
  const run = (action: MemoryAction) =>
    act.mutate({ id: item.id, action }, { onSuccess: () => toast.success(DONE[action]), onError: (e) => toast.error(errorMessage(e)) });
  const pinned = item.importance >= 1;
  const busy = act.isPending || update.isPending;

  return (
    <li
      id={`memory-${item.id}`}
      className={cn("px-3 py-3 text-[13px] transition-colors", highlighted && "bg-accent/10 shadow-[inset_2px_0_0_var(--nx-accent)]")}
    >
      <p className="whitespace-pre-wrap break-words text-sm text-fg">{item.content}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {flagsOf(item).map((f) => (
          <Tooltip key={f.label} label={f.hint}>
            <span tabIndex={0} className="rounded focus-visible:outline-2 focus-visible:outline-ring">
              <Badge tone={f.tone}>{f.label}</Badge>
            </span>
          </Tooltip>
        ))}
        {item.tags.map((t) => (
          <span key={t} className="rounded bg-raised px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
            #{t}
          </span>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-fg-subtle">
        {provenance(item)} · {formatRelativeTime(item.created_at)}
        {item.access_count ? ` · used ${item.access_count} ${item.access_count === 1 ? "time" : "times"}` : ""}
      </p>
      {score ? (
        <p className="mt-1 text-xs text-fg-muted">
          Match {Math.round(score.total * 100)}%
          {explainScore(score).length ? ` · ${explainScore(score).map((p) => `${p.label} ${p.share}`).join(", ")}` : ""}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.status === "pending" ? (
          <>
            <Button size="sm" variant="primary" disabled={busy} onClick={() => run("confirm")}>
              <Check /> Keep
            </Button>
            {onEdit ? (
              <Button size="sm" disabled={busy} onClick={() => onEdit(item)}>
                <Pencil /> Edit
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => run("dismiss")}>
              <X /> Dismiss
            </Button>
          </>
        ) : item.status === "active" ? (
          <>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                update.mutate(
                  { id: item.id, body: { pinned: !pinned } },
                  { onSuccess: () => toast.success(pinned ? "Unpinned" : "Pinned"), onError: (e) => toast.error(errorMessage(e)) },
                )
              }
            >
              {pinned ? <PinOff /> : <Pin />} {pinned ? "Unpin" : "Pin"}
            </Button>
            {onEdit ? (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => onEdit(item)}>
                <Pencil /> Edit
              </Button>
            ) : null}
            {item.source.kind === "summary" ? (
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => run("undo-compression")}>
                <Undo2 /> Restore the originals
              </Button>
            ) : null}
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => run("delete")}>
              <Trash2 /> Delete
            </Button>
          </>
        ) : (
          <>
            <Button size="sm" disabled={busy} onClick={() => run("restore")}>
              <RotateCcw /> Restore
            </Button>
            <Button size="sm" variant="danger" disabled={busy} onClick={() => run("purge")}>
              <Trash2 /> Erase for good
            </Button>
          </>
        )}
      </div>
    </li>
  );
}
