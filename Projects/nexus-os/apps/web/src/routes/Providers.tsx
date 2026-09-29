import type { ConnectionTest, Provider, ProviderKind } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, EmptyState, ErrorState, Skeleton, toast } from "@nexus/ui";
import { Plus, Server } from "lucide-react";
import { useState } from "react";
import { ProviderCard } from "../features/providers/ProviderCard";
import { ProviderDialog } from "../features/providers/ProviderDialog";
import { errorMessage, useDeleteProvider, useProviders, useTestProvider } from "../lib/queries";

export function ProvidersRoute() {
  const providers = useProviders();
  const remove = useDeleteProvider();
  const test = useTestProvider();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Provider | undefined>();
  const [deleting, setDeleting] = useState<Provider | undefined>();
  const [fresh, setFresh] = useState<Record<string, ConnectionTest>>({});
  const remember = (id: string, r: ConnectionTest) => setFresh((f) => ({ ...f, [id]: r }));

  const addButton = (
    <Button variant="primary" onClick={() => setAdding(true)}>
      <Plus /> Add provider
    </Button>
  );

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">AI providers</h3>
          <p className="mt-0.5 max-w-xl text-[13px] text-fg-muted">
            Where NEXUS gets its models. Each agent can use a different one. Keys never leave your device except to reach the provider you gave them to.
          </p>
        </div>
        {providers.data && providers.data.length > 0 ? addButton : null}
      </div>

      {providers.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-36" />
          <Skeleton className="h-36" />
        </div>
      ) : providers.isError ? (
        <ErrorState message={errorMessage(providers.error)} onRetry={() => void providers.refetch()} />
      ) : providers.data.length === 0 ? (
        <EmptyState
          icon={<Server />}
          title="Connect an AI provider"
          description="NEXUS needs at least one model to plan and work. Use a cloud provider with your own key, or a local model that never leaves this machine."
          action={addButton}
        />
      ) : (
        <ul className="space-y-3">
          {providers.data.map((p) => (
            <li key={p.id}>
              <ProviderCard
                provider={p}
                fresh={fresh[p.id]}
                onTested={remember}
                onEdit={() => setEditing(p)}
                onDelete={() => setDeleting(p)}
              />
            </li>
          ))}
        </ul>
      )}

      <ProviderDialog
        open={adding}
        onOpenChange={setAdding}
        onCreated={(p) =>
          // Verify the connection straight away so problems show up while the user is still here.
          test.mutate(p.id, {
            onSuccess: (r) => {
              remember(p.id, r);
              if (r.ok) toast.success(`${p.name} connected`);
              else toast.error(`${p.name} was saved but could not connect: ${r.detail}`);
            },
          })
        }
      />
      {editing ? (
        <ProviderDialog key={editing.id} open onOpenChange={(o) => !o && setEditing(undefined)} existing={editing} initialKind={editing.kind as ProviderKind} />
      ) : null}

      <Dialog open={!!deleting} onOpenChange={(o) => !o && setDeleting(undefined)}>
        <DialogContent title={`Remove ${deleting?.name ?? "provider"}?`} description="Its stored API key is deleted too. Agents that prefer this provider will fall back to another one.">
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(undefined)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() =>
                deleting &&
                remove.mutate(deleting.id, {
                  onSuccess: () => {
                    toast.success(`Removed ${deleting.name}`);
                    setDeleting(undefined);
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              Remove provider
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
