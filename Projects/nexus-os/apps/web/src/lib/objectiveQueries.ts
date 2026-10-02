import { unwrap } from "@nexus/shared";
import type { ObjectiveCreate, PlanEdit } from "@nexus/schemas";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

/** Statuses in which an objective is still changing on its own (so the page keeps refreshing). */
export const LIVE_OBJECTIVE = new Set(["RECEIVED", "PLANNING", "RUNNING", "VERIFYING"]);

export const ok = {
  objectives: (filter?: object) => ["objectives", filter ?? {}] as const,
  objective: (id: string) => ["objective", id] as const,
};

function invalidateObjectives(qc: QueryClient, id?: string): void {
  void qc.invalidateQueries({ queryKey: ["objectives"] });
  if (id) void qc.invalidateQueries({ queryKey: ok.objective(id) });
  for (const key of [["runs"], ["approvals"], ["artifacts"], ["tool-calls"]]) void qc.invalidateQueries({ queryKey: key });
}

export function useObjectives(filter: { projectId?: string; status?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ok.objectives(filter),
    refetchInterval: 10_000,
    queryFn: () =>
      unwrap(
        api.GET("/api/objectives", {
          params: { query: { project_id: filter.projectId, status_filter: filter.status, limit: filter.limit ?? 20 } },
        }),
      ),
  });
}

/** The event stream invalidates this as things happen; polling is the safety net while it is live. */
export function useObjective(id: string) {
  return useQuery({
    queryKey: ok.objective(id),
    queryFn: () => unwrap(api.GET("/api/objectives/{objective_id}", { params: { path: { objective_id: id } } })),
    refetchInterval: (q) => (q.state.data && LIVE_OBJECTIVE.has(q.state.data.objective.status) ? 2_000 : 8_000),
  });
}

export function useCreateObjective() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ObjectiveCreate) => unwrap(api.POST("/api/objectives", { body })),
    onSuccess: (o) => invalidateObjectives(qc, o.id),
  });
}

export function useStartDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/demo")),
    onSuccess: (o) => {
      invalidateObjectives(qc, o.id);
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: ["providers"] });
    },
  });
}

export function useRunObjective(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (mode: "normal" | "safe_only") =>
      unwrap(api.POST("/api/objectives/{objective_id}/run", { params: { path: { objective_id: id } }, body: { mode } })),
    onSettled: () => invalidateObjectives(qc, id),
  });
}

export function useEditPlan(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PlanEdit) =>
      unwrap(api.PUT("/api/objectives/{objective_id}/plan", { params: { path: { objective_id: id } }, body })),
    onSuccess: (detail) => qc.setQueryData(ok.objective(id), detail),
  });
}

export function useObjectiveAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "cancel" | "resume") =>
      unwrap(
        action === "cancel"
          ? api.POST("/api/objectives/{objective_id}/cancel", { params: { path: { objective_id: id } } })
          : api.POST("/api/objectives/{objective_id}/resume", { params: { path: { objective_id: id } } }),
      ),
    onSettled: () => invalidateObjectives(qc, id),
  });
}

export function useTaskAction(objectiveId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, action, text }: { taskId: string; action: "retry" | "skip" | "answer"; text?: string }) => {
      const path = { params: { path: { task_id: taskId } } };
      if (action === "answer") return unwrap(api.POST("/api/tasks/{task_id}/answer", { ...path, body: { text: text ?? "" } }));
      if (action === "retry") return unwrap(api.POST("/api/tasks/{task_id}/retry", path));
      return unwrap(api.POST("/api/tasks/{task_id}/skip", path));
    },
    onSettled: () => invalidateObjectives(qc, objectiveId),
  });
}
