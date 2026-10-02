import type { McpServer, RiskLevel } from "@nexus/schemas";
import { Button, Dialog, DialogContent, DialogFooter, FieldError, Input, Label, Select, Switch, Textarea, cn, toast } from "@nexus/ui";
import { Globe, Terminal } from "lucide-react";
import { useState, type FormEvent } from "react";
import { errorMessage } from "../../lib/queries";
import { useCreateMcpServer, useUpdateMcpServer } from "../../lib/mcpQueries";
import { RISK } from "../agents/format";
import { PairsEditor } from "./PairsEditor";
import { EMPTY_FORM, MCP_RISKS, toCreate, toForm, toUpdate, validateForm, type Pair, type SecretRow, type ServerForm } from "./model";

const RISK_HELP: Record<string, string> = {
  MODERATE: "Runs without asking in balanced projects. Only for servers you trust completely.",
  HIGH: "Recommended. Asks you first in balanced projects, and scheduled runs always wait for you.",
  VERY_HIGH: "Always asks you, in every project.",
};

const blankPair = (): Pair => ({ key: "", value: "" });
const blankSecret = (): SecretRow => ({ key: "", value: "", saved: false });

function TransportPicker({ value, onChange }: { value: ServerForm["transport"]; onChange: (t: ServerForm["transport"]) => void }) {
  const options = [
    { t: "stdio" as const, icon: Terminal, title: "A program on this computer", hint: "Started by NEXUS, e.g. npx or uvx (stdio)." },
    { t: "http" as const, icon: Globe, title: "A web address", hint: "A server that is already running (streamable HTTP)." },
  ];
  return (
    <div role="radiogroup" aria-label="How NEXUS reaches the server" className="grid gap-2 sm:grid-cols-2">
      {options.map(({ t, icon: Icon, title, hint }) => (
        <button
          key={t}
          type="button"
          role="radio"
          aria-checked={value === t}
          onClick={() => onChange(t)}
          className={cn(
            "rounded-lg border p-3 text-left transition-colors",
            value === t ? "border-accent bg-accent/10" : "border-line hover:border-accent/60 hover:bg-raised",
          )}
        >
          <span className="flex items-center gap-2 text-sm font-medium">
            <Icon className="size-4" aria-hidden="true" /> {title}
          </span>
          <span className="mt-1 block text-xs text-fg-muted">{hint}</span>
        </button>
      ))}
    </div>
  );
}

function ServerFormBody({ server, onDone }: { server?: McpServer | undefined; onDone: () => void }) {
  const [form, setForm] = useState<ServerForm>(() => (server ? toForm(server) : EMPTY_FORM));
  const [touched, setTouched] = useState(false);
  const create = useCreateMcpServer();
  const update = useUpdateMcpServer(server?.id ?? "");
  const set = <K extends keyof ServerForm>(k: K, v: ServerForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const errors = touched ? validateForm(form, !server) : {};
  const pending = create.isPending || update.isPending;
  const failure = create.error ?? update.error;

  function done(s: McpServer, verb: string) {
    if (s.status === "error") toast.error(`${verb} ${s.name}, but it did not start: ${s.error ?? "unknown problem"}`);
    else if (s.status === "running") toast.success(`${verb} ${s.name}: ${s.tools ?? 0} tools available`);
    else toast.success(`${verb} ${s.name}`);
    onDone();
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (Object.keys(validateForm(form, !server)).length) return;
    if (!server) return create.mutate(toCreate(form), { onSuccess: (s) => done(s, "Added") });
    const patch = toUpdate(server, form);
    if (Object.keys(patch).length === 0) return onDone();
    update.mutate(patch, { onSuccess: (s) => done(s, "Saved") });
  }

  return (
    <form onSubmit={submit} className="max-h-[70vh] space-y-5 overflow-y-auto pr-1" noValidate>
      {!server ? (
        <>
          <TransportPicker value={form.transport} onChange={(t) => set("transport", t)} />
          <div>
            <Label htmlFor="mcp-name">Name</Label>
            <Input id="mcp-name" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="github" aria-invalid={!!errors.name} />
            {errors.name ? <FieldError>{errors.name}</FieldError> : (
              <p className="mt-1 text-xs text-fg-subtle">
                Its tools will be named <code className="font-mono">mcp__{form.name || "name"}__…</code>. It cannot be changed later.
              </p>
            )}
          </div>
        </>
      ) : null}
      <div>
        <Label htmlFor="mcp-description">What it is for (optional)</Label>
        <Input id="mcp-description" value={form.description} onChange={(e) => set("description", e.target.value)} maxLength={500} />
      </div>

      {form.transport === "stdio" ? (
        <>
          <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
            <div>
              <Label htmlFor="mcp-command">Command</Label>
              <Input id="mcp-command" value={form.command} onChange={(e) => set("command", e.target.value)} placeholder="npx" className="font-mono text-xs" aria-invalid={!!errors.command} spellCheck={false} />
              <FieldError>{errors.command}</FieldError>
            </div>
            <div>
              <Label htmlFor="mcp-args">Arguments (one per line)</Label>
              <Textarea id="mcp-args" rows={3} value={form.args} onChange={(e) => set("args", e.target.value)} placeholder={"-y\n@modelcontextprotocol/server-filesystem\n/path/to/folder"} className="font-mono text-xs" spellCheck={false} />
            </div>
          </div>
          <div>
            <Label htmlFor="mcp-cwd">Working folder (optional)</Label>
            <Input id="mcp-cwd" value={form.cwd} onChange={(e) => set("cwd", e.target.value)} placeholder="A private folder in NEXUS's data" className="font-mono text-xs" spellCheck={false} />
          </div>
          <fieldset>
            <legend className="mb-1.5 text-[13px] font-medium">Environment variables</legend>
            <p className="mb-2 text-xs text-fg-subtle">
              The program gets only what you list here (plus basics like PATH), none of NEXUS's own settings or keys. Put tokens under secret values: they are
              kept in the secret store and never shown again.
            </p>
            <PairsEditor label="Variable" rows={form.env} onChange={(rows) => set("env", rows)} blank={blankPair} keyPlaceholder="LOG_LEVEL" />
            <div className="mt-3">
              <p className="mb-1.5 text-xs font-medium text-fg-muted">Secret values</p>
              <PairsEditor label="Secret variable" secret rows={form.secretEnv} onChange={(rows) => set("secretEnv", rows)} blank={blankSecret} keyPlaceholder="API_TOKEN" />
            </div>
            <FieldError>{errors.env}</FieldError>
          </fieldset>
        </>
      ) : (
        <>
          <div>
            <Label htmlFor="mcp-url">Address</Label>
            <Input id="mcp-url" value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://mcp.example.com/mcp" className="font-mono text-xs" aria-invalid={!!errors.url} spellCheck={false} />
            <FieldError>{errors.url}</FieldError>
          </div>
          <fieldset>
            <legend className="mb-1.5 text-[13px] font-medium">Headers</legend>
            <p className="mb-2 text-xs text-fg-subtle">Put credentials (such as Authorization) under secret headers. They are only sent over https, except to this computer.</p>
            <PairsEditor label="Header" rows={form.headers} onChange={(rows) => set("headers", rows)} blank={blankPair} keyPlaceholder="X-Workspace" />
            <div className="mt-3">
              <p className="mb-1.5 text-xs font-medium text-fg-muted">Secret values</p>
              <PairsEditor label="Secret header" secret rows={form.secretHeaders} onChange={(rows) => set("secretHeaders", rows)} blank={blankSecret} keyPlaceholder="Authorization" />
            </div>
            <FieldError>{errors.headers}</FieldError>
          </fieldset>
        </>
      )}

      <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <Label htmlFor="mcp-risk">Risk level of its tools</Label>
          <Select id="mcp-risk" value={form.riskLevel} onChange={(e) => set("riskLevel", e.target.value as RiskLevel)}>
            {MCP_RISKS.map((r) => (
              <option key={r} value={r}>
                {RISK[r].label}
              </option>
            ))}
          </Select>
          <p className="mt-1 text-xs text-fg-subtle">{RISK_HELP[form.riskLevel]}</p>
        </div>
        <div>
          <Label htmlFor="mcp-timeout">Time limit per call (s)</Label>
          <Input id="mcp-timeout" inputMode="numeric" value={form.timeout} onChange={(e) => set("timeout", e.target.value)} aria-invalid={!!errors.timeout} />
          <FieldError>{errors.timeout}</FieldError>
        </div>
      </div>
      {!server ? (
        <label className="flex items-center gap-2 text-[13px]">
          <Switch checked={form.enabled} onCheckedChange={(v) => set("enabled", v)} aria-label="Start it now" /> Start it now, and whenever NEXUS starts
        </label>
      ) : null}

      <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-fg-muted">
        A server runs with your own permissions and sees whatever its tools are given. Only add servers you trust. Its tools reach agents only if you add
        them to an agent, and every call goes through approvals like any other risky action.
      </p>
      {failure ? (
        <p role="alert" className="text-[13px] text-danger">
          {errorMessage(failure)}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={pending}>
          {server ? "Save" : "Add server"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function McpServerDialog({ open, onOpenChange, server }: { open: boolean; onOpenChange: (o: boolean) => void; server?: McpServer | undefined }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={server ? `Edit ${server.name}` : "Add an MCP server"}
        description={server ? undefined : "Connect the tools of another program through the Model Context Protocol."}
        className="max-w-2xl"
      >
        {open ? <ServerFormBody key={server?.id ?? "new"} server={server} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
