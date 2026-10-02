import { Button, EmptyState } from "@nexus/ui";
import { Link } from "react-router";
import { Page } from "./Page";

export function NotFoundRoute() {
  return (
    <Page>
      <EmptyState
        title="Page not found"
        description="That address doesn't lead anywhere in NEXUS."
        action={
          <Button asChild variant="primary">
            <Link to="/">Go to Command Center</Link>
          </Button>
        }
      />
    </Page>
  );
}
