import { Button, Card, FieldError, Input, Label, toast } from "@nexus/ui";
import { ArrowRight, Pin } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { useCreateIdea, useIdeas } from "../../lib/ideaQueries";
import { errorMessage } from "../../lib/queries";
import { KIND_LABEL, parseQuickCapture } from "./format";

/** A one-line inbox on the Command Center: type, press Enter, and it is in Ideas & notes. */
export function QuickCapture() {
  const create = useCreateIdea();
  const pinned = useIdeas({ status: "open" }).data?.filter((i) => i.pinned) ?? [];
  const [text, setText] = useState("");
  const { kind, text: body } = parseQuickCapture(text);

  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    create.mutate(
      { text: body.trim(), kind },
      {
        onSuccess: (idea) => {
          setText("");
          toast.success(`${KIND_LABEL[idea.kind]} saved to Ideas & notes`);
        },
      },
    );
  }

  return (
    <Card className="flex flex-col">
      <header className="flex items-center justify-between gap-2 border-b border-line px-3 py-2">
        <h3 className="text-[13px] font-medium text-fg">Jot something down</h3>
        <Button asChild variant="ghost" size="sm">
          <Link to="/ideas">
            Ideas & notes <ArrowRight />
          </Link>
        </Button>
      </header>
      <form onSubmit={save} className="p-3">
        <Label htmlFor="quick-capture" className="sr-only">
          Jot something down
        </Label>
        <Input
          id="quick-capture"
          value={text}
          maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          placeholder="An idea, or “todo: …” / “note: …”, then Enter"
        />
        <p className="mt-1.5 text-xs text-fg-subtle">
          Saves as {kind === "todo" ? "a to-do" : `an ${KIND_LABEL[kind].toLowerCase()}`}. Add due times and projects in Ideas & notes.
        </p>
        <FieldError>{create.isError ? errorMessage(create.error) : null}</FieldError>
      </form>
      {pinned.length > 0 ? (
        <ul className="border-t border-line px-3 py-2 text-[13px]" aria-label="Pinned">
          {pinned.slice(0, 3).map((i) => (
            <li key={i.id} className="py-0.5">
              <Link to={`/ideas?idea=${i.id}`} className="flex items-center gap-1.5 text-fg-muted hover:text-fg hover:underline">
                <Pin className="size-3.5 shrink-0 text-accent-text" aria-hidden="true" />
                <span className="truncate">{i.text.split("\n")[0]}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
