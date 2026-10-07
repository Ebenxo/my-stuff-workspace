import { Card } from "@nexus/ui";
import { ApprovalsPanel } from "../features/approvals/ApprovalsPanel";
import { Page, PageHeader } from "./Page";

export function ApprovalsRoute() {
  return (
    <Page>
      <PageHeader
        title="Approvals"
        description="Actions an agent wants to take that need your say-so. Nothing here has happened yet: an agent waits until you decide."
      />
      <Card>
        <ApprovalsPanel />
      </Card>
    </Page>
  );
}
