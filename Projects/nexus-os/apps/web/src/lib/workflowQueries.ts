import { unwrap } from "@nexus/shared";
import type { ScheduleCreate, ScheduleUpdate, WorkflowCreate, WorkflowDefinition, WorkflowUpdate } from "@nexus/schemas";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const LIVE_RUN = new Set(["RUNNING"]);

export const wk = {
  workflows: (projectId?: string) => ["workflows", projectId ?? null] as const,
  workflow: (id: string) => ["workflow", id] as const,
  versions: (id: string) => ["workflow", id, "versions"] as const,
  runs: (filter: object) => ["workflow-runs", filter] as const,
  run: (id: string) => ["workflow-run", id] as const,
  schedules: (workflowId?: string) => ["schedules", workflowId ?? null] as const,
  preview: (cron: string, tz: string) => ["schedule-preview", cron, tz] as const,
};

function invalidateWorkflows(qc: QueryClient): void {
  for (const key of [["workflows"], ["workflow"], ["workflow-runs"], ["workflow-run"], ["schedules"]]) {
    void qc.invalidateQueries({ queryKey: key });
  }
}

export function useWorkflows(projectId?: string) {
  return useQuery({
    queryKey: wk.workflows(projectId),
    queryFn: () => unwrap(api.GET("/api/workflows", { params: { query: { project_id: projectId } } })),
  });
}

export function useWorkflow(id: string) {
  return useQuery({
    queryKey: wk.workflow(id),
    enabled: !!id,
    queryFn: () => unwrap(api.GET("/api/workflows/{workflow_id}", { params: { path: { workflow_id: id } } })),
  });
}

export function useWorkflowVersions(id: string) {
  return useQuery({
    queryKey: wk.versions(id),
    queryFn: () => unwrap(api.GET("/api/workflows/{workflow_id}/versions", { params: { path: { workflow_id: id } } })),
  });
}

export function useCreateWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkflowCreate) => unwrap(api.POST("/api/workflows", { body })),
    onSuccess: () => invalidateWorkflows(qc),
  });
}

export function useSaveWorkflow(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: WorkflowUpdate) =>
      unwrap(api.PUT("/api/workflows/{workflow_id}", { params: { path: { workflow_id: id } }, body })),
    onSuccess: (wf) => {
      qc.setQueryData(wk.workflow(id), wf);
      invalidateWorkflows(qc);
    },
  });
}

export function useDeleteWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await unwrap(api.DELETE("/api/workflows/{workflow_id}", { params: { path: { workflow_id: id } } }));
    },
    onSuccess: () => invalidateWorkflows(qc),
  });
}

/** Checks a draft as the person edits (not saved). */
export function useValidation(projectId: string, workflowId: string, definition: WorkflowDefinition | undefined) {
  return useQuery({
    queryKey: ["workflow-validate", workflowId, definition],
    enabled: !!definition && !!projectId,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.POST("/api/workflows/validate", {
          body: { project_id: projectId, workflow_id: workflowId, definition: definition! },
        }),
      ),
  });
}

export function useRunWorkflow(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inputs: Record<string, unknown>) =>
      unwrap(api.POST("/api/workflows/{workflow_id}/run", { params: { path: { workflow_id: id } }, body: { inputs } })),
    onSuccess: () => invalidateWorkflows(qc),
  });
}

export function useWorkflowRuns(filter: { workflowId?: string; projectId?: string; limit?: number }) {
  return useQuery({
    queryKey: wk.runs(filter),
    refetchInterval: 10_000,
    queryFn: () =>
      filter.workflowId
        ? unwrap(
            api.GET("/api/workflows/{workflow_id}/runs", {
              params: { path: { workflow_id: filter.workflowId }, query: { limit: filter.limit ?? 30 } },
            }),
          )
        : unwrap(api.GET("/api/workflow-runs", { params: { query: { project_id: filter.projectId, limit: filter.limit ?? 30 } } })),
  });
}

export function useWorkflowRun(id: string) {
  return useQuery({
    queryKey: wk.run(id),
    queryFn: () => unwrap(api.GET("/api/workflow-runs/{run_id}", { params: { path: { run_id: id } } })),
    refetchInterval: (q) => (q.state.data && LIVE_RUN.has(q.state.data.run.status) ? 1_500 : 8_000),
  });
}

export function useRunAction(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "cancel" | "retry") =>
      unwrap(
        action === "cancel"
          ? api.POST("/api/workflow-runs/{run_id}/cancel", { params: { path: { run_id: runId } } })
          : api.POST("/api/workflow-runs/{run_id}/retry", { params: { path: { run_id: runId } } }),
      ),
    onSettled: () => invalidateWorkflows(qc),
  });
}

export function useNodeDecision(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ node, action, text }: { node: string; action: "approve" | "reject" | "answer"; text?: string }) => {
      const params = { path: { run_id: runId, node_id: node } };
      if (action === "answer") {
        return unwrap(api.POST("/api/workflow-runs/{run_id}/nodes/{node_id}/answer", { params, body: { text: text ?? "" } }));
      }
      const body = { note: text ?? "" };
      return unwrap(
        action === "approve"
          ? api.POST("/api/workflow-runs/{run_id}/nodes/{node_id}/approve", { params, body })
          : api.POST("/api/workflow-runs/{run_id}/nodes/{node_id}/reject", { params, body }),
      );
    },
    onSettled: () => invalidateWorkflows(qc),
  });
}

export function useSchedules(workflowId?: string) {
  return useQuery({
    queryKey: wk.schedules(workflowId),
    queryFn: () => unwrap(api.GET("/api/schedules", { params: { query: { workflow_id: workflowId } } })),
  });
}

export function useCronPreview(cron: string, timezone: string) {
  const expr = cron.trim();
  return useQuery({
    queryKey: wk.preview(expr, timezone),
    enabled: expr.length > 0,
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/schedules/preview", { params: { query: { cron: expr, timezone } } })),
  });
}

export function useScheduleMutations() {
  const qc = useQueryClient();
  const done = { onSuccess: () => invalidateWorkflows(qc) };
  return {
    create: useMutation({ mutationFn: (body: ScheduleCreate) => unwrap(api.POST("/api/schedules", { body })), ...done }),
    update: useMutation({
      mutationFn: ({ id, body }: { id: string; body: ScheduleUpdate }) =>
        unwrap(api.PATCH("/api/schedules/{schedule_id}", { params: { path: { schedule_id: id } }, body })),
      ...done,
    }),
    remove: useMutation({
      mutationFn: async (id: string) => {
        await unwrap(api.DELETE("/api/schedules/{schedule_id}", { params: { path: { schedule_id: id } } }));
      },
      ...done,
    }),
    runNow: useMutation({
      mutationFn: (id: string) => unwrap(api.POST("/api/schedules/{schedule_id}/run-now", { params: { path: { schedule_id: id } } })),
      ...done,
    }),
  };
}
