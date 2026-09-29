import { unwrap } from "@nexus/shared";
import type { McpServerCreate, McpServerUpdate } from "@nexus/schemas";
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const mk = {
  servers: ["mcp", "servers"] as const,
  server: (id: string) => ["mcp", "server", id] as const,
  log: (id: string) => ["mcp", "log", id] as const,
};

/** Server changes also change the tool list (MCP tools come and go with their servers). */
function invalidateMcp(qc: QueryClient): void {
  void qc.invalidateQueries({ queryKey: ["mcp"] });
  void qc.invalidateQueries({ queryKey: ["tools"] });
}

export function useMcpServers() {
  return useQuery({
    queryKey: mk.servers,
    queryFn: () => unwrap(api.GET("/api/mcp/servers")),
    // While a server is starting (e.g. just after NEXUS starts), look again shortly.
    refetchInterval: (q) => (q.state.data?.some((s) => s.status === "starting") ? 1500 : false),
  });
}

export function useMcpServer(id: string, enabled = true) {
  return useQuery({
    queryKey: mk.server(id),
    enabled: enabled && !!id,
    queryFn: () => unwrap(api.GET("/api/mcp/servers/{server_id}", { params: { path: { server_id: id } } })),
  });
}

export function useMcpLog(id: string, enabled: boolean) {
  return useQuery({
    queryKey: mk.log(id),
    enabled,
    queryFn: () => unwrap(api.GET("/api/mcp/servers/{server_id}/log", { params: { path: { server_id: id } } })),
  });
}

export function useCreateMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: McpServerCreate) => unwrap(api.POST("/api/mcp/servers", { body })),
    onSuccess: () => invalidateMcp(qc),
  });
}

export function useUpdateMcpServer(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: McpServerUpdate) =>
      unwrap(api.PATCH("/api/mcp/servers/{server_id}", { params: { path: { server_id: id } }, body })),
    onSuccess: () => invalidateMcp(qc),
  });
}

export function useDeleteMcpServer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await unwrap(api.DELETE("/api/mcp/servers/{server_id}", { params: { path: { server_id: id } } }));
    },
    onSuccess: () => invalidateMcp(qc),
  });
}

export type McpAction = "start" | "stop" | "check";

export function useMcpAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: McpAction }) => {
      const params = { params: { path: { server_id: id } } };
      if (action === "start") return unwrap(api.POST("/api/mcp/servers/{server_id}/start", params));
      if (action === "stop") return unwrap(api.POST("/api/mcp/servers/{server_id}/stop", params));
      return unwrap(api.POST("/api/mcp/servers/{server_id}/check", params));
    },
    onSuccess: () => invalidateMcp(qc),
  });
}

export function useReadResource(id: string) {
  return useMutation({
    mutationFn: (uri: string) =>
      unwrap(api.POST("/api/mcp/servers/{server_id}/resources/read", { params: { path: { server_id: id } }, body: { uri } })),
  });
}
