import type { WorkflowNodeType } from "@nexus/schemas";
import { Bot, Braces, Flag, GitBranch, Play, Repeat, ShieldCheck, Timer, Workflow, Wrench, type LucideIcon } from "lucide-react";

export const NODE_ICON: Record<WorkflowNodeType, LucideIcon> = {
  trigger: Play,
  agent: Bot,
  tool: Wrench,
  condition: GitBranch,
  approval: ShieldCheck,
  transform: Braces,
  output: Flag,
  delay: Timer,
  loop: Repeat,
  subworkflow: Workflow,
};
