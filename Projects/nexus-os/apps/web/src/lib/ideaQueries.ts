import { unwrap } from "@nexus/shared";
import { parseEventRecord, type EventRecord, type IdeaCreate, type IdeaKind, type IdeaToObjective, type IdeaUpdate } from "@nexus/schemas";
import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api } from "./api";

export type IdeaStatusFilter = "open" | "done" | "all";

export interface IdeaFilter {
  status?: IdeaStatusFilter;
  kind?: IdeaKind | undefined;
  projectId?: string | undefined;
  q?: string | undefined;
}

export const ik = {
  list: (f: IdeaFilter) => ["ideas", "list", f] as const,
  dueCount: ["ideas", "due-count"] as const,
  timeline: (projectId?: string) => ["timeline", projectId ?? null] as const,
  history: (projectId: string | undefined, detailed: boolean) => ["history", projectId ?? null, detailed] as const,
};

/** Ideas also show up on the timeline and in search, so a change refreshes all three. */
function invalidateIdeas(qc: QueryClient): void {
  for (const key of [["ideas"], ["timeline"], ["search"]]) void qc.invalidateQueries({ queryKey: key });
}

export function useIdeas(f: IdeaFilter) {
  return useQuery({
    queryKey: ik.list(f),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(
        api.GET("/api/ideas", {
          params: {
            query: {
              status_filter: f.status ?? "open",
              kind: f.kind,
              project_id: f.projectId,
              q: f.q?.trim() || undefined,
              limit: 300,
            },
          },
        }),
      ),
  });
}

/** Open items whose due time has come (shown next to "Ideas" in the sidebar). */
export function useIdeasDueCount(): number {
  return (
    useQuery({
      queryKey: ik.dueCount,
      refetchInterval: 60_000,
      queryFn: () => unwrap(api.GET("/api/ideas/due-count")),
    }).data?.count ?? 0
  );
}

export function useCreateIdea() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: IdeaCreate) => unwrap(api.POST("/api/ideas", { body })),
    onSuccess: () => invalidateIdeas(qc),
  });
}

export function useUpdateIdea() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: IdeaUpdate }) =>
      unwrap(api.PATCH("/api/ideas/{idea_id}", { params: { path: { idea_id: id } }, body })),
    onSuccess: () => invalidateIdeas(qc),
  });
}

export function useDeleteIdea() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await unwrap(api.DELETE("/api/ideas/{idea_id}", { params: { path: { idea_id: id } } }));
    },
    onSuccess: () => invalidateIdeas(qc),
  });
}

export function useStartIdeaObjective() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: IdeaToObjective }) =>
      unwrap(api.POST("/api/ideas/{idea_id}/objective", { params: { path: { idea_id: id } }, body })),
    onSuccess: () => {
      invalidateIdeas(qc);
      void qc.invalidateQueries({ queryKey: ["objectives"] });
    },
  });
}

export function useTimeline(projectId?: string) {
  return useQuery({
    queryKey: ik.timeline(projectId),
    refetchInterval: 30_000, // schedules come due and relative times move on even when nothing happens
    placeholderData: keepPreviousData,
    queryFn: () => unwrap(api.GET("/api/timeline", { params: { query: { project_id: projectId } } })),
  });
}

/** Never in the history: they repeat something already shown, or are bookkeeping for every model call. */
const ALWAYS_LEFT_OUT = ["NOTIFICATION_CREATED", "USAGE_RECORDED"];
/** Fine-grained steps, shown only when the person asks for every detail. */
export const DETAIL_TYPES = [
  "AGENT_STEP",
  "TOOL_CALLED",
  "TOOL_COMPLETED",
  "TASK_STATUS_CHANGED",
  "WORKFLOW_NODE_STARTED",
  "WORKFLOW_NODE_COMPLETED",
];
export const HISTORY_PAGE = 60;

export function historyExcludes(detailed: boolean): string[] {
  return detailed ? ALWAYS_LEFT_OUT : [...ALWAYS_LEFT_OUT, ...DETAIL_TYPES];
}

/** The event log, newest first, a page at a time ("Load older" asks for the page before the last one). */
export function useHistory(projectId: string | undefined, detailed: boolean) {
  return useInfiniteQuery({
    queryKey: ik.history(projectId, detailed),
    initialPageParam: 0,
    getNextPageParam: (last: EventRecord[]) => (last.length < HISTORY_PAGE ? undefined : last[last.length - 1]?.seq),
    queryFn: async ({ pageParam }): Promise<EventRecord[]> => {
      const page = await unwrap(
        api.GET("/api/events", {
          params: {
            query: {
              newest_first: true,
              limit: HISTORY_PAGE,
              before_seq: pageParam,
              project_id: projectId,
              exclude_types: historyExcludes(detailed).join(","),
            },
          },
        }),
      );
      // The wire is untrusted input to the UI, like the live stream.
      return page.map((raw) => parseEventRecord(raw)).filter((e): e is EventRecord => e !== null);
    },
  });
}
