import { unwrap } from "@nexus/shared";
import type { MemoryCreate, MemoryUpdate, SearchKind } from "@nexus/schemas";
import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type MemoryStatusFilter = "active" | "pending" | "deleted";

export interface MemoryFilter {
  projectId?: string | undefined;
  scope?: "project" | "global" | undefined;
  status?: MemoryStatusFilter;
  source?: "user" | "agent" | "objective" | "summary" | undefined;
  tag?: string | undefined;
  q?: string | undefined;
}

export const mk = {
  list: (f: MemoryFilter) => ["memory", "list", f] as const,
  stats: (projectId?: string) => ["memory", "stats", projectId ?? null] as const,
  search: (q: string, projectId?: string) => ["memory", "search", q, projectId ?? null] as const,
  item: (id: string) => ["memory", "item", id] as const,
  universal: (q: string, projectId?: string) => ["search", q, projectId ?? null] as const,
};

/** Every memory query starts with "memory", so one invalidation refreshes lists, counts and searches. */
function invalidateMemory(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["memory"] });
  void qc.invalidateQueries({ queryKey: ["search"] });
}

export function useMemories(f: MemoryFilter, enabled = true) {
  return useQuery({
    queryKey: mk.list(f),
    enabled,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/memory", {
          params: {
            query: {
              project_id: f.projectId,
              scope: f.scope,
              status_filter: f.status ?? "active",
              source: f.source,
              tag: f.tag || undefined,
              q: f.q || undefined,
              limit: 200,
            },
          },
        }),
      ),
  });
}

export function useMemoryStats(projectId?: string) {
  return useQuery({
    queryKey: mk.stats(projectId),
    refetchInterval: 30_000,
    queryFn: () => unwrap(api.GET("/api/memory/stats", { params: { query: { project_id: projectId } } })),
  });
}

/** What an agent in this project would recall for ``q`` (with the score breakdown). */
export function useMemorySearch(q: string, projectId?: string) {
  const query = q.trim();
  return useQuery({
    queryKey: mk.search(query, projectId),
    enabled: query.length >= 2,
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/memory/search", { params: { query: { q: query, project_id: projectId, k: 20 } } })),
  });
}

export function useCreateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MemoryCreate) => unwrap(api.POST("/api/memory", { body })),
    onSuccess: () => invalidateMemory(qc),
  });
}

export function useUpdateMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MemoryUpdate }) =>
      unwrap(api.PATCH("/api/memory/{item_id}", { params: { path: { item_id: id } }, body })),
    onSuccess: () => invalidateMemory(qc),
  });
}

export type MemoryAction = "confirm" | "dismiss" | "restore" | "delete" | "purge" | "undo-compression";

export function useMemoryAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, action }: { id: string; action: MemoryAction }) => {
      const path = { params: { path: { item_id: id } } };
      switch (action) {
        case "confirm":
          return unwrap(api.POST("/api/memory/{item_id}/confirm", path));
        case "dismiss":
          return unwrap(api.POST("/api/memory/{item_id}/dismiss", path));
        case "restore":
          return unwrap(api.POST("/api/memory/{item_id}/restore", path));
        case "undo-compression":
          return unwrap(api.POST("/api/memory/{item_id}/undo-compression", path));
        case "delete":
        case "purge":
          await unwrap(
            api.DELETE("/api/memory/{item_id}", { params: { path: { item_id: id }, query: { purge: action === "purge" } } }),
          );
          return null;
      }
    },
    onSettled: () => invalidateMemory(qc),
  });
}

export function useCompressMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => unwrap(api.POST("/api/memory/compress", { body: { project_id: projectId } })),
    onSuccess: () => invalidateMemory(qc),
  });
}

export function useUniversalSearch(q: string, opts: { projectId?: string; kinds?: SearchKind[] } = {}) {
  const query = q.trim();
  return useQuery({
    queryKey: [...mk.universal(query, opts.projectId), opts.kinds ?? []],
    enabled: query.length >= 1,
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/search", {
          params: { query: { q: query, project_id: opts.projectId, kinds: opts.kinds ?? [], limit: 50 } },
        }),
      ),
  });
}
