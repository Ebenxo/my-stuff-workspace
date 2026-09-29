import { TooltipProvider, Toaster } from "@nexus/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router";
import { AppShell } from "./layout/AppShell";
import { retryPolicy } from "./lib/queries";
import { AgentsRoute } from "./routes/Agents";
import { ApprovalsRoute } from "./routes/Approvals";
import { CommandCenterRoute } from "./routes/CommandCenter";
import { MemoryRoute } from "./routes/Memory";
import { NotFoundRoute } from "./routes/NotFound";
import { ObjectiveRoute } from "./routes/Objective";
import { ProjectDetailRoute } from "./routes/ProjectDetail";
import { ProjectsRoute } from "./routes/Projects";
import { ProvidersRoute } from "./routes/Providers";
import { RunRoute } from "./routes/Run";
import { SearchRoute } from "./routes/Search";
import { GeneralSettingsRoute, HealthRoute, SettingsLayout, ToolsRoute } from "./routes/Settings";
import { UsageRoute } from "./routes/Usage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: true, retry: retryPolicy },
    mutations: { retry: false },
  },
});

const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <CommandCenterRoute /> },
      { path: "projects", element: <ProjectsRoute /> },
      { path: "projects/:projectId", element: <ProjectDetailRoute /> },
      { path: "agents", element: <AgentsRoute /> },
      { path: "objectives/:objectiveId", element: <ObjectiveRoute /> },
      { path: "runs/:runId", element: <RunRoute /> },
      { path: "approvals", element: <ApprovalsRoute /> },
      { path: "memory", element: <MemoryRoute /> },
      { path: "search", element: <SearchRoute /> },
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { index: true, element: <GeneralSettingsRoute /> },
          { path: "providers", element: <ProvidersRoute /> },
          { path: "tools", element: <ToolsRoute /> },
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
