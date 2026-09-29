import { TooltipProvider, Toaster } from "@nexus/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createBrowserRouter } from "react-router";
import { AppShell } from "./layout/AppShell";
import { retryPolicy } from "./lib/queries";
import { CommandCenterRoute } from "./routes/CommandCenter";
import { NotFoundRoute } from "./routes/NotFound";
import { ProjectDetailRoute } from "./routes/ProjectDetail";
import { ProjectsRoute } from "./routes/Projects";
import { GeneralSettingsRoute, HealthRoute, SettingsLayout } from "./routes/Settings";

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
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { index: true, element: <GeneralSettingsRoute /> },
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
