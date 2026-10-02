import type { IdeaKind } from "@nexus/schemas";
import { Lightbulb, ListTodo, StickyNote, type LucideIcon } from "lucide-react";

export const KIND_ICON: Record<IdeaKind, LucideIcon> = { idea: Lightbulb, note: StickyNote, todo: ListTodo };
