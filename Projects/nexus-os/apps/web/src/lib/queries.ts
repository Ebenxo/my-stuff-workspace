import { ApiError, unwrap } from "@nexus/shared";
import type {
  ProjectCreate,
  ProjectUpdate,
  UserSettingsUpdate,
} from "@nexus/schemas";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const qk = {
  projects: (status?: string) => ["projects", status ?? "all"] as const,
  project: (id: string) => ["project", id] as const,
  health: ["health"] as const,
  settings: ["settings"] as const,
  notifications: ["notifications"] as const,
  unread: ["notifications", "unread"] as const,
  events: (scope: string) => ["events", scope] as const,
  verify: ["events", "verify"] as const,
};

export function retryPolicy(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
  return failureCount < 2;
}

export function useProjects(status?: "active" | "archived") {
  return useQuery({
    queryKey: qk.projects(status),
    queryFn: () =>
      unwrap(api.GET("/api/projects", { params: { query: status ? { status_filter: status } : {} } })),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: qk.project(id),
    queryFn: () => unwrap(api.GET("/api/projects/{project_id}", { params: { path: { project_id: id } } })),
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => unwrap(api.POST("/api/projects", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectUpdate) =>
      unwrap(api.PATCH("/api/projects/{project_id}", { params: { path: { project_id: id } }, body })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects"] });
      void qc.invalidateQueries({ queryKey: qk.project(id) });
    },
  });
}

export function useSetProjectArchived() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      unwrap(
        archived
          ? api.POST("/api/projects/{project_id}/archive", { params: { path: { project_id: id } } })
          : api.POST("/api/projects/{project_id}/unarchive", { params: { path: { project_id: id } } }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });
}

export function useHealth(refetchMs = 15_000) {
  return useQuery({
    queryKey: qk.health,
    queryFn: () => unwrap(api.GET("/api/health")),
    refetchInterval: refetchMs,
  });
}

export function useSettings() {
  return useQuery({ queryKey: qk.settings, queryFn: () => unwrap(api.GET("/api/settings")) });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UserSettingsUpdate) => unwrap(api.PATCH("/api/settings", { body })),
    onSuccess: (data) => qc.setQueryData(qk.settings, data),
  });
}

export function useNotifications() {
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => unwrap(api.GET("/api/notifications", { params: { query: { limit: 50 } } })),
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: qk.unread,
    queryFn: () => unwrap(api.GET("/api/notifications/unread-count")),
  });
}

export function useMarkNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string | "all"): Promise<void> => {
      if (id === "all") await unwrap(api.POST("/api/notifications/read-all"));
      else await unwrap(api.POST("/api/notifications/{notification_id}/read", { params: { path: { notification_id: id } } }));
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

export function useVerifyEvents() {
  return useMutation({ mutationFn: () => unwrap(api.GET("/api/events/verify", { params: { query: {} } })) });
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
