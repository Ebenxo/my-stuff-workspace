import { z } from "zod";

/** Runtime validation for events arriving over SSE (the wire is untrusted input to the UI). */
export const EventRecordSchema = z.object({
  seq: z.number().int(),
  id: z.string(),
  ts: z.string(),
  type: z.string(),
  project_id: z.string().nullable().optional(),
  objective_id: z.string().nullable().optional(),
  task_id: z.string().nullable().optional(),
  run_id: z.string().nullable().optional(),
  agent_id: z.string().nullable().optional(),
  actor: z.string(),
  payload: z.record(z.string(), z.unknown()),
  prev_hash: z.string(),
  hash: z.string(),
});

export type EventRecord = z.infer<typeof EventRecordSchema>;

export function parseEventRecord(raw: unknown): EventRecord | null {
  const result = EventRecordSchema.safeParse(raw);
  return result.success ? result.data : null;
}
