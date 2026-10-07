/**
 * The browser preview's model: Claude, through the claude.ai page's `sample` capability, on the
 * viewer's own Claude account (the first call asks them to allow it). Each call is independent: the
 * prompt carries the instructions, the material and the output format.
 */

export type AiTier = "quick" | "default" | "complex";

export interface AiOptions {
  tier?: AiTier;
  signal?: AbortSignal;
}

export interface Ai {
  /** Whether a model is available in this view at all. */
  readonly available: boolean;
  text(prompt: string, opts?: AiOptions): Promise<string>;
  json<T>(prompt: string, opts?: AiOptions): Promise<T>;
}

export class AiError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AiError";
  }
}

const MESSAGES: Record<string, string> = {
  not_granted: "This page was not allowed to use Claude. Reload the page and allow it when asked.",
  rate_limited: "Claude is busy for this account right now. Try again in a minute.",
  cancelled: "Stopped.",
  invalid_json: "Claude's answer was not in the expected form. Try again.",
  prompt_too_large: "There was too much material to send at once. Try with fewer or shorter files.",
  usage_limit: "Your Claude usage limit has been reached for now.",
};

function wrap(error: unknown): AiError {
  const e = error as { code?: unknown; message?: unknown };
  const code = typeof e?.code === "string" ? e.code : "unavailable";
  const message = MESSAGES[code] ?? (typeof e?.message === "string" && e.message ? e.message : "Claude could not answer just now.");
  return new AiError(code, message);
}

export interface SampleFn {
  (input: string, options?: Record<string, unknown>): Promise<{ text: string; truncated: boolean }>;
  json<T>(input: string, options?: Record<string, unknown>): Promise<T>;
}

/** Claude through the claude.ai runtime, or a stand-in that says no model is available. */
export function claudeAi(sample: SampleFn | null): Ai {
  if (!sample) {
    const no = () => Promise.reject(new AiError("unavailable", "No model is available in this view. Open the page on claude.ai."));
    return { available: false, text: no, json: no };
  }
  const options = (o?: AiOptions) => ({ modelTier: o?.tier ?? "default", cache: false, ...(o?.signal ? { signal: o.signal } : {}) });
  return {
    available: true,
    async text(prompt, o) {
      try {
        return (await sample(prompt, options(o))).text;
      } catch (error) {
        throw wrap(error);
      }
    },
    async json<T>(prompt: string, o?: AiOptions) {
      try {
        return await sample.json<T>(prompt, options(o));
      } catch (error) {
        throw wrap(error);
      }
    },
  };
}

/** Rough token count for usage figures (about four characters per token). */
export const estimateTokens = (text: string): number => Math.ceil(text.length / 4);
