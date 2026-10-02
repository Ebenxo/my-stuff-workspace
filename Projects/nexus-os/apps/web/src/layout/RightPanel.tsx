import { Badge, EmptyState, Tabs, TabsContent, TabsList, TabsTrigger } from "@nexus/ui";
import { Activity } from "lucide-react";
import { useMemo } from "react";
import { ApprovalsPanel } from "../features/approvals/ApprovalsPanel";
import { ActivityList } from "../features/events/ActivityList";
import { isActivityEvent } from "../features/events/describe";
import { usePendingApprovalCount } from "../lib/agentQueries";
import { useEvents } from "../stores/events";
import { useUi, type RightTab } from "../stores/ui";

function ActivityFeed() {
  const events = useEvents((s) => s.events);
  const newestFirst = useMemo(() => events.filter(isActivityEvent).reverse().slice(0, 100), [events]);
  return newestFirst.length === 0 ? (
    <EmptyState icon={<Activity />} title="Nothing has happened yet" description="Everything NEXUS does is recorded here as it happens." />
  ) : (
    <ActivityList events={newestFirst} />
  );
}

export function RightPanel() {
  const tab = useUi((s) => s.rightTab);
  const setRight = useUi((s) => s.setRight);
  const pending = usePendingApprovalCount();
  // Tabs for features that do not exist yet are not offered; a stored choice falls back to Activity.
  const active: RightTab = tab === "approvals" ? "approvals" : "activity";
  return (
    <aside aria-label="Side panel" className="hidden w-80 shrink-0 flex-col border-l border-line bg-surface lg:flex">
      <Tabs value={active} onValueChange={(v) => setRight(true, v as RightTab)} className="flex min-h-0 flex-1 flex-col">
        <TabsList className="shrink-0">
          <TabsTrigger value="activity">Activity</TabsTrigger>
          <TabsTrigger value="approvals">
            Approvals
            {pending > 0 ? (
              <Badge tone="warning" className="ml-1.5" aria-label={`${pending} waiting`}>
                {pending}
              </Badge>
            ) : null}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="activity" className="min-h-0 flex-1 overflow-y-auto">
          <ActivityFeed />
        </TabsContent>
        <TabsContent value="approvals" className="min-h-0 flex-1 overflow-y-auto">
          <ApprovalsPanel showHistory={false} />
        </TabsContent>
      </Tabs>
    </aside>
  );
}
