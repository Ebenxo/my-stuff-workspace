import type { IdeaKind } from "@nexus/schemas";
import { cn } from "@nexus/ui";
import { KIND_LABEL } from "./format";
import { KIND_ICON } from "./icons";

/** Idea, note or to-do, as one radio group. */
export function KindPicker({ value, onChange, idPrefix }: { value: IdeaKind; onChange: (k: IdeaKind) => void; idPrefix: string }) {
  return (
    <div role="radiogroup" aria-label="Kind" className="inline-flex rounded-md border border-line-strong bg-canvas p-0.5">
      {(Object.keys(KIND_LABEL) as IdeaKind[]).map((k) => {
        const Icon = KIND_ICON[k];
        const on = value === k;
        return (
          <button
            key={k}
            id={`${idPrefix}-${k}`}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(k)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded px-2.5 text-[13px] font-medium transition-colors",
              on ? "bg-raised text-fg shadow-sm" : "text-fg-muted hover:text-fg",
            )}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {KIND_LABEL[k]}
          </button>
        );
      })}
    </div>
  );
}

