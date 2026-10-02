import type { Provider, ProviderCreate, ProviderKind, ProviderKindInfo, ProviderUpdate } from "@nexus/schemas";
import { Badge, Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, cn } from "@nexus/ui";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { errorMessage, useCreateProvider, useProviderKinds, useProviderModels, useUpdateProvider } from "../../lib/queries";

function KindPicker({ kinds, onPick }: { kinds: ProviderKindInfo[]; onPick: (k: ProviderKindInfo) => void }) {
  return (
    <div role="radiogroup" aria-label="Provider type" className="grid gap-2 sm:grid-cols-2">
      {kinds.map((k) => (
        <button
          key={k.kind}
          type="button"
          role="radio"
          aria-checked={false}
          onClick={() => onPick(k)}
          className="rounded-lg border border-line p-3 text-left transition-colors hover:border-accent hover:bg-raised"
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            {k.label}
            {k.local ? <Badge tone="success">On this machine</Badge> : null}
          </span>
          <span className="mt-1 block text-xs text-fg-muted">{k.help}</span>
        </button>
      ))}
    </div>
  );
}

interface FormProps {
  kind: ProviderKindInfo;
  existing?: Provider | undefined;
  pending: boolean;
  error?: string | undefined;
  onSubmit: (v: { name: string; baseUrl: string; defaultModel: string; apiKey: string; removeKey: boolean }) => void;
  onBack?: (() => void) | undefined;
  onCancel: () => void;
}

function ProviderForm({ kind, existing, pending, error, onSubmit, onBack, onCancel }: FormProps) {
  const [name, setName] = useState(existing?.name ?? kind.label.replace(" (local)", ""));
  const [baseUrl, setBaseUrl] = useState(existing?.base_url ?? "");
  const [defaultModel, setDefaultModel] = useState(existing?.default_model ?? "");
  const [apiKey, setApiKey] = useState("");
  const [removeKey, setRemoveKey] = useState(false);
  const [touched, setTouched] = useState(false);
  const models = useProviderModels(existing?.id);

  const needsKey = kind.needs_key && !existing;
  const errors = {
    name: name.trim() === "" ? "Give this provider a name." : undefined,
    key: needsKey && apiKey.trim() === "" ? `${kind.label} needs an API key.` : undefined,
    url: kind.kind === "openai_compatible" && baseUrl.trim() === "" ? "Enter the endpoint's base URL." : undefined,
  };
  const invalid = Object.values(errors).some(Boolean);

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    onSubmit({ name: name.trim(), baseUrl: baseUrl.trim(), defaultModel: defaultModel.trim(), apiKey: apiKey.trim(), removeKey });
  }

  return (
    <form onSubmit={submit} noValidate autoComplete="off">
      <div className="space-y-4">
        <div>
          <Label htmlFor="prov-name">Name</Label>
          <Input id="prov-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} aria-invalid={touched && !!errors.name} />
          {touched ? <FieldError>{errors.name}</FieldError> : null}
        </div>

        {kind.kind !== "demo" ? (
          <div>
            <Label htmlFor="prov-key">API key{kind.needs_key ? "" : " (optional)"}</Label>
            {existing?.has_key && !removeKey ? (
              <p className="mb-2 flex items-center gap-1.5 text-xs text-fg-muted">
                <KeyRound className="size-3.5" aria-hidden="true" />
                A key is stored ({existing.key_hint}). Enter a new one to replace it.
              </p>
            ) : null}
            <Input
              id="prov-key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
              placeholder={existing?.has_key ? "Leave blank to keep the current key" : "Paste your key"}
              aria-invalid={touched && !!errors.key}
              disabled={removeKey}
              className="font-mono"
            />
            {touched ? <FieldError>{errors.key}</FieldError> : null}
            <p className="mt-1.5 flex items-start gap-1.5 text-xs text-fg-muted">
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              Stored in your operating system's keychain (or a private file if none is available). It is never shown again or sent anywhere except this provider.
            </p>
            {existing?.has_key ? (
              <label className="mt-2 flex items-center gap-2 text-xs text-fg-muted">
                <input type="checkbox" checked={removeKey} onChange={(e) => setRemoveKey(e.target.checked)} className="accent-[var(--nx-accent)]" />
                Remove the stored key
              </label>
            ) : null}
          </div>
        ) : null}

        {kind.kind !== "demo" ? (
          <div>
            <Label htmlFor="prov-url">Base URL{kind.kind === "openai_compatible" ? "" : " (optional)"}</Label>
            <Input
              id="prov-url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder={kind.default_base_url ?? "https://your-endpoint.example.com/v1"}
              spellCheck={false}
              aria-invalid={touched && !!errors.url}
              className="font-mono text-[13px]"
            />
            {touched ? <FieldError>{errors.url}</FieldError> : null}
          </div>
        ) : null}

        <div>
          <Label htmlFor="prov-model">Default model (optional)</Label>
          <Input
            id="prov-model"
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            list="prov-models"
            spellCheck={false}
            placeholder={existing ? "Pick or type a model id" : "You can pick from the list after connecting"}
            className="font-mono text-[13px]"
          />
          <datalist id="prov-models">
            {(models.data ?? []).map((m) => (
              <option key={m.id} value={m.id} />
            ))}
          </datalist>
        </div>
        <FieldError>{error}</FieldError>
      </div>
      <DialogFooter>
        {onBack ? (
          <Button type="button" variant="ghost" onClick={onBack} className="mr-auto">
            Back
          </Button>
        ) : null}
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={pending}>
          {existing ? "Save changes" : "Connect"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ProviderDialog({
  open,
  onOpenChange,
  existing,
  initialKind,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing?: Provider | undefined;
  initialKind?: ProviderKind | undefined;
  onCreated?: ((p: Provider) => void) | undefined;
}) {
  const kinds = useProviderKinds();
  const create = useCreateProvider();
  const update = useUpdateProvider(existing?.id ?? "");
  const [picked, setPicked] = useState<ProviderKind | undefined>(initialKind);

  const kindInfo = kinds.data?.find((k) => k.kind === (existing?.kind ?? picked));
  const pending = create.isPending || update.isPending;
  const error = create.isError ? errorMessage(create.error) : update.isError ? errorMessage(update.error) : undefined;

  function close(o: boolean) {
    if (!o) {
      create.reset();
      update.reset();
      setPicked(initialKind);
    }
    onOpenChange(o);
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent
        title={existing ? `Edit ${existing.name}` : kindInfo ? `Connect ${kindInfo.label}` : "Add an AI provider"}
        description={existing ? undefined : kindInfo ? kindInfo.help : "Choose where NEXUS gets its models. You can add several and route work between them."}
        className={cn("max-w-lg", !existing && !kindInfo && "max-w-xl")}
      >
        {!existing && !kindInfo ? (
          // The scripted demo provider is registered by the demo project itself, not chosen by hand.
          <KindPicker kinds={(kinds.data ?? []).filter((k) => k.kind !== "demo")} onPick={(k) => setPicked(k.kind)} />
        ) : kindInfo ? (
          <ProviderForm
            kind={kindInfo}
            existing={existing}
            pending={pending}
            error={error}
            onBack={existing ? undefined : () => setPicked(undefined)}
            onCancel={() => close(false)}
            onSubmit={(v) => {
              if (existing) {
                const body: ProviderUpdate = {
                  name: v.name,
                  base_url: v.baseUrl,
                  default_model: v.defaultModel,
                  ...(v.removeKey ? { api_key: "" } : v.apiKey ? { api_key: v.apiKey } : {}),
                };
                update.mutate(body, { onSuccess: () => close(false) });
              } else {
                const body: ProviderCreate = {
                  kind: kindInfo.kind,
                  name: v.name,
                  ...(v.baseUrl ? { base_url: v.baseUrl } : {}),
                  ...(v.defaultModel ? { default_model: v.defaultModel } : {}),
                  ...(v.apiKey ? { api_key: v.apiKey } : {}),
                };
                create.mutate(body, {
                  onSuccess: (p) => {
                    onCreated?.(p);
                    close(false);
                  },
                });
              }
            }}
          />
        ) : (
          <p className="text-sm text-fg-muted">Loading provider types…</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
