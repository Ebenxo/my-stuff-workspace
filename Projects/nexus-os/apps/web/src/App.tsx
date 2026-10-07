import { TooltipProvider, Toaster } from "@nexus/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter, createHashRouter } from "react-router";
import { AppShell } from "./layout/AppShell";
import { retryPolicy } from "./lib/queries";
import { IS_PREVIEW } from "./preview/flag";
import { AgentsRoute } from "./routes/Agents";
import { ApprovalsRoute } from "./routes/Approvals";
import { CommandCenterRoute } from "./routes/CommandCenter";
import { IdeasRoute } from "./routes/Ideas";
import { MemoryRoute } from "./routes/Memory";
import { NotFoundRoute } from "./routes/NotFound";
import { ObjectiveRoute } from "./routes/Objective";
import { ProjectDetailRoute } from "./routes/ProjectDetail";
import { ProjectsRoute } from "./routes/Projects";
import { ProvidersRoute } from "./routes/Providers";
import { RunRoute } from "./routes/Run";
import { SearchRoute } from "./routes/Search";
import { TimelineRoute } from "./routes/Timeline";
import { GeneralSettingsRoute, HealthRoute, IntegrationsRoute, SettingsLayout, ToolsRoute } from "./routes/Settings";
import { UsageRoute } from "./routes/Usage";
import { WorkflowEditorRoute } from "./routes/WorkflowEditor";
import { WorkflowRunRoute } from "./routes/WorkflowRun";
import { WorkflowsRoute } from "./routes/Workflows";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: true, retry: retryPolicy },
    mutations: { retry: false },
  },
});

// The browser preview is one hosted page, so its routes live after the "#".
const router = (IS_PREVIEW ? createHashRouter : createBrowserRouter)([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <CommandCenterRoute /> },
      { path: "timeline", element: <TimelineRoute /> },
      { path: "ideas", element: <IdeasRoute /> },
      { path: "projects", element: <ProjectsRoute /> },
      { path: "projects/:projectId", element: <ProjectDetailRoute /> },
      { path: "agents", element: <AgentsRoute /> },
      { path: "objectives/:objectiveId", element: <ObjectiveRoute /> },
      { path: "runs/:runId", element: <RunRoute /> },
      { path: "approvals", element: <ApprovalsRoute /> },
      { path: "memory", element: <MemoryRoute /> },
      { path: "workflows", element: <WorkflowsRoute /> },
      { path: "workflows/:workflowId", element: <WorkflowEditorRoute /> },
      { path: "workflow-runs/:runId", element: <WorkflowRunRoute /> },
      { path: "search", element: <SearchRoute /> },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { index: true, element: <GeneralSettingsRoute /> },
          { path: "providers", element: <ProvidersRoute /> },
          { path: "tools", element: <ToolsRoute /> },
          { path: "integrations", element: <IntegrationsRoute /> },
          { path: "usage", element: <UsageRoute /> },
          { path: "health", element: <HealthRoute /> },
        ],
      },
      { path: "*", element: <NotFoundRoute /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
