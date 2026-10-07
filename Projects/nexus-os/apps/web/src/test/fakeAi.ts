import type { Ai } from "../preview/ai";
import { AiError } from "../preview/ai";

export type Answer = string | object | AiError;

/** A stand-in for Claude: answers each prompt with what ``reply`` returns, and records the prompts. */
export function fakeAi(reply: (prompt: string, n: number) => Answer | Promise<Answer>): Ai & { prompts: string[] } {
  const prompts: string[] = [];
  const answer = async (prompt: string, signal?: AbortSignal): Promise<Answer> => {
    prompts.push(prompt);
    if (signal?.aborted) throw new AiError("cancelled", "Stopped.");
    const r = await reply(prompt, prompts.length);
    if (signal?.aborted) throw new AiError("cancelled", "Stopped.");
    if (r instanceof AiError) throw r;
    return r;
  };
  return {
    available: true,
    prompts,
    async text(prompt, o) {
      const r = await answer(prompt, o?.signal);
      return typeof r === "string" ? r : JSON.stringify(r);
    },
    async json<T>(prompt: string, o?: { signal?: AbortSignal }) {
      const r = await answer(prompt, o?.signal);
      return (typeof r === "string" ? JSON.parse(r) : r) as T;
    },
  };
}

/** Which NEXUS role a prompt is for. */
export function roleOf(prompt: string): "planner" | "critic" | "verifier" | "agent" {
  if (prompt.startsWith("You are the Planner")) return "planner";
  if (prompt.startsWith("You are the Critic")) return "critic";
  if (prompt.startsWith("You are the Verifier")) return "verifier";
  return "agent";
}
