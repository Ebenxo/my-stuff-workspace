import type { ConnectionTest, Provider } from "@nexus/schemas";
import { formatRelativeTime } from "@nexus/shared";
import { Badge, Button, Card, Switch, toast } from "@nexus/ui";
import { CheckCircle2, Pencil, PlugZap, Trash2, XCircle } from "lucide-react";
import { errorMessage, useTestProvider, useUpdateProvider } from "../../lib/queries";

const KIND_LABEL: Record<string, string> = {
  anthropic: "Anthropic",
  openai: "OpenAI",
  gemini: "Google Gemini",
  ollama: "Ollama",
  lmstudio: "LM Studio",
  openai_compatible: "Custom endpoint",
  demo: "Demo (scripted)",
};

export function ProviderCard({
  provider,
  fresh,
  onTested,
  onEdit,
  onDelete,
}: {
  provider: Provider;
  fresh?: ConnectionTest | undefined;
  onTested: (id: string, r: ConnectionTest) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const test = useTestProvider();
  const toggle = useUpdateProvider(provider.id);

  const result: { ok: boolean; text: string } | null = fresh
    ? { ok: fresh.ok, text: fresh.ok ? `${fresh.detail} (${fresh.latency_ms} ms)` : fresh.detail }
    : provider.last_test_ok === true
      ? { ok: true, text: `Connected ${provider.last_test_at ? formatRelativeTime(provider.last_test_at) : ""}`.trim() }
      : provider.last_test_ok === false
        ? { ok: false, text: provider.last_test_error ?? "The last connection test failed." }
        : null;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-sm font-medium text-fg">{provider.name}</h3>
            <Badge>{KIND_LABEL[provider.kind] ?? provider.kind}</Badge>
            {provider.is_local ? <Badge tone="success">On this machine</Badge> : <Badge tone="info">Cloud</Badge>}
            {!provider.enabled ? <Badge tone="warning">Disabled</Badge> : null}
          </div>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
            <dt className="text-fg-subtle">Default model</dt>
            <dd className="font-mono text-fg-muted">{provider.default_model ?? "chosen automatically"}</dd>
            <dt className="text-fg-subtle">API key</dt>
            <dd className="font-mono text-fg-muted">{provider.has_key ? provider.key_hint : provider.is_local ? "not needed" : "none"}</dd>
            {provider.base_url ? (
              <>
                <dt className="text-fg-subtle">Endpoint</dt>
                <dd className="break-all font-mono text-fg-muted">{provider.base_url}</dd>
              </>
            ) : null}
          </dl>
        </div>
        <label className="flex items-center gap-2 text-xs text-fg-muted">
          <span>{provider.enabled ? "Enabled" : "Disabled"}</span>
          <Switch
            checked={provider.enabled}
            disabled={toggle.isPending}
            aria-label={`${provider.enabled ? "Disable" : "Enable"} ${provider.name}`}
            onCheckedChange={(enabled) =>
              toggle.mutate({ enabled }, { onError: (e) => toast.error(errorMessage(e)) })
            }
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          loading={test.isPending}
          onClick={() =>
            test.mutate(provider.id, {
              onSuccess: (r) => onTested(provider.id, r),
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          <PlugZap /> Test connection
        </Button>
        <Button size="sm" variant="ghost" onClick={onEdit}>
          <Pencil /> Edit
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete} aria-label={`Remove ${provider.name}`}>
          <Trash2 /> Remove
        </Button>
      </div>

      {result ? (
        <p
          role="status"
          className={`mt-3 flex items-start gap-1.5 text-[13px] ${result.ok ? "text-success" : "text-danger"}`}
        >
          {result.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> : <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />}
          <span>{result.text}</span>
        </p>
      ) : (
        <p className="mt-3 text-xs text-fg-subtle">Not tested yet.</p>
      )}
    </Card>
  );
}
