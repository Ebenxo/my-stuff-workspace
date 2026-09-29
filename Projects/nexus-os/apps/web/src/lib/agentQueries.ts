import { ApiError, unwrap } from "@nexus/shared";
import type { AgentCreate, AgentRunRequest, AgentUpdate, ApprovalDecision } from "@nexus/schemas";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const TERMINAL_RUN_STATUSES = new Set(["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]);

export const ak = {
  agents: ["agents"] as const,
  runs: (filter?: object) => ["runs", filter ?? {}] as const,
  run: (id: string) => ["run", id] as const,
  approvals: (status?: string, projectId?: string) => ["approvals", status ?? "all", projectId ?? "all"] as const,
  grants: ["approval-grants"] as const,
  tools: ["tools"] as const,
  toolCalls: (filter?: object) => ["tool-calls", filter ?? {}] as const,
  artifacts: (projectId: string) => ["artifacts", projectId] as const,
  artifact: (id: string, version?: number) => ["artifact", id, version ?? "latest"] as const,
  files: (projectId: string, path: string) => ["files", projectId, path] as const,
  file: (projectId: string, path: string) => ["file", projectId, path] as const,
  models: ["models"] as const,
};

/** Whatever changed on the server, refresh what depends on it. */
export function invalidateRuntime(qc: QueryClient): void {
  for (const key of [["runs"], ["run"], ["approvals"], ["tool-calls"], ["artifacts"], ["files"], ["approval-grants"]]) {
    void qc.invalidateQueries({ queryKey: key });
  }
}

export function useAgents() {
  return useQuery({ queryKey: ak.agents, queryFn: () => unwrap(api.GET("/api/agents")) });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentCreate) => unwrap(api.POST("/api/agents", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ak.agents }),
  });
}

export function useUpdateAgent(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentUpdate) =>
      unwrap(api.PATCH("/api/agents/{agent_id}", { params: { path: { agent_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ak.agents }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await unwrap(api.DELETE("/api/agents/{agent_id}", { params: { path: { agent_id: id } } }));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ak.agents }),
  });
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AgentRunRequest) => unwrap(api.POST("/api/agents/run", { body })),
    onSuccess: () => invalidateRuntime(qc),
  });
}

export interface RunFilter {
  projectId?: string;
  agent?: string;
  status?: string;
  limit?: number;
}

export function useRuns(filter: RunFilter = {}, refetchMs?: number) {
  return useQuery({
    queryKey: ak.runs(filter),
    refetchInterval: refetchMs,
    queryFn: () =>
      unwrap(
        api.GET("/api/runs", {
          params: {
            query: {
              project_id: filter.projectId,
              agent: filter.agent,
              status_filter: filter.status,
              limit: filter.limit ?? 30,
            },
          },
        }),
      ),
  });
}

/** Polls while the run is live; the event stream also invalidates it as things happen. */
export function useRun(id: string) {
  return useQuery({
    queryKey: ak.run(id),
    queryFn: () => unwrap(api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } })),
    refetchInterval: (q) => {
      const status = q.state.data?.run.status;
      return status && TERMINAL_RUN_STATUSES.has(status) ? false : 2_000;
    },
  });
}

function runAction(action: "cancel" | "resume") {
  return (id: string) =>
    unwrap(
      action === "cancel"
        ? api.POST("/api/runs/{run_id}/cancel", { params: { path: { run_id: id } } })
        : api.POST("/api/runs/{run_id}/resume", { params: { path: { run_id: id } } }),
    );
}

export function useCancelRun() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: runAction("cancel"), onSettled: () => invalidateRuntime(qc) });
}

export function useResumeRun() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: runAction("resume"), onSettled: () => invalidateRuntime(qc) });
}

export function useAnswerRun(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (text: string) =>
      unwrap(api.POST("/api/runs/{run_id}/answer", { params: { path: { run_id: id } }, body: { text } })),
    onSettled: () => invalidateRuntime(qc),
  });
}

export function useApprovals(status: "PENDING" | undefined, projectId?: string, limit = 50) {
  return useQuery({
    queryKey: ak.approvals(status, projectId),
    refetchInterval: status === "PENDING" ? 10_000 : false, // the event stream is primary; this is a safety net
    queryFn: () =>
      unwrap(
        api.GET("/api/approvals", {
          params: { query: { status_filter: status, project_id: projectId, limit } },
        }),
      ),
  });
}

export function usePendingApprovalCount(): number {
  return useApprovals("PENDING").data?.length ?? 0;
}

export function useDecideApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: ApprovalDecision }) =>
      unwrap(
        api.POST("/api/approvals/{approval_id}/decision", {
          params: { path: { approval_id: id } },
          body: decision,
        }),
      ),
    onSettled: () => invalidateRuntime(qc),
  });
}

export function useSessionGrants() {
  return useQuery({ queryKey: ak.grants, queryFn: () => unwrap(api.GET("/api/approvals/grants")) });
}

export function useRevokeGrant() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      await unwrap(api.DELETE("/api/approvals/grants/{grant_id}", { params: { path: { grant_id: id } } }));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ak.grants }),
  });
}

export function useTools() {
  return useQuery({ queryKey: ak.tools, queryFn: () => unwrap(api.GET("/api/tools")) });
}

export function useToggleTool() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      unwrap(api.PATCH("/api/tools/{name}", { params: { path: { name } }, body: { enabled } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ak.tools }),
  });
}

export function useToolCalls(filter: { projectId?: string; runId?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ak.toolCalls(filter),
    queryFn: () =>
      unwrap(
        api.GET("/api/tool-calls", {
          params: { query: { project_id: filter.projectId, run_id: filter.runId, limit: filter.limit ?? 50 } },
        }),
      ),
  });
}

export function useArtifacts(projectId: string) {
  return useQuery({
    queryKey: ak.artifacts(projectId),
    queryFn: () =>
      unwrap(api.GET("/api/projects/{project_id}/artifacts", { params: { path: { project_id: projectId }, query: {} } })),
  });
}

export function useArtifactContent(id: string | undefined, version?: number) {
  return useQuery({
    queryKey: ak.artifact(id ?? "", version),
    enabled: !!id,
    queryFn: () =>
      unwrap(
        api.GET("/api/artifacts/{artifact_id}/content", {
          params: { path: { artifact_id: id! }, query: version ? { version } : {} },
        }),
      ),
  });
}

export function useArtifactVersions(id: string | undefined) {
  return useQuery({
    queryKey: ["artifact-versions", id],
    enabled: !!id,
    queryFn: () => unwrap(api.GET("/api/artifacts/{artifact_id}/versions", { params: { path: { artifact_id: id! } } })),
  });
}

export function useFiles(projectId: string, path: string) {
  return useQuery({
    queryKey: ak.files(projectId, path),
    queryFn: () =>
      unwrap(api.GET("/api/projects/{project_id}/files", { params: { path: { project_id: projectId }, query: { path } } })),
  });
}

export function useFileContent(projectId: string, path: string | undefined) {
  return useQuery({
    queryKey: ak.file(projectId, path ?? ""),
    enabled: !!path,
    retry: false,
    queryFn: () =>
      unwrap(
        api.GET("/api/projects/{project_id}/files/content", {
          params: { path: { project_id: projectId }, query: { path: path! } },
        }),
      ),
  });
}

export function useWriteFile(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      unwrap(
        api.PUT("/api/projects/{project_id}/files/content", {
          params: { path: { project_id: projectId }, query: { path } },
          body: { content },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["files", projectId] });
      void qc.invalidateQueries({ queryKey: ["file", projectId] });
    },
  });
}

export function useDeleteFile(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (path: string) =>
      unwrap(
        api.DELETE("/api/projects/{project_id}/files", {
          params: { path: { project_id: projectId }, query: { path } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["files", projectId] });
      void qc.invalidateQueries({ queryKey: ["file", projectId] });
    },
  });
}

export function useModels() {
  return useQuery({ queryKey: ak.models, queryFn: () => unwrap(api.GET("/api/models")), staleTime: 30_000 });
}

/** The scripted demo model only knows the demo's lines, so it is never offered as a manual choice. */
export const DEMO_MODEL_ID = "demo:scripted";

export function usePickableModels() {
  return useQuery({
    queryKey: ak.models,
    queryFn: () => unwrap(api.GET("/api/models")),
    staleTime: 30_000,
    select: (models) => models.filter((m) => m.id !== DEMO_MODEL_ID),
  });
}

export const isNotFound = (e: unknown): boolean => e instanceof ApiError && e.status === 404;
