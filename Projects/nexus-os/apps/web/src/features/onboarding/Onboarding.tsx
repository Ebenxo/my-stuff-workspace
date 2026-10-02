import type { PermissionLevel, Provider, UserSettings } from "@nexus/schemas";
import { Button, Card, CardContent, FieldError, Input, Label, cn, toast } from "@nexus/ui";
import { CheckCircle2, FlaskConical, PlugZap, ShieldCheck, Sparkles } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { Logo } from "../../layout/Logo";
import { useStartDemo } from "../../lib/objectiveQueries";
import { errorMessage, useTestProvider, useUpdateSettings } from "../../lib/queries";
import { PERMISSION_COPY } from "../projects/permissions";
import { ProviderDialog } from "../providers/ProviderDialog";

const STEPS = ["Welcome", "Safety", "A model", "Ready"] as const;
const LEVELS: PermissionLevel[] = ["cautious", "balanced", "permissive"];

interface Draft {
  name: string;
  level: PermissionLevel;
  workspace: string;
}

function Stepper({ step }: { step: number }) {
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" aria-label="Setup steps">
      {STEPS.map((s, i) => (
        <li key={s} className={cn("flex items-center gap-1.5", i === step ? "text-fg" : "text-fg-subtle")} aria-current={i === step ? "step" : undefined}>
          <span
            className={cn(
              "flex size-5 items-center justify-center rounded-full border text-[11px]",
              i < step ? "border-success bg-success/15 text-success" : i === step ? "border-accent text-accent-text" : "border-line",
            )}
            aria-hidden="true"
          >
            {i < step ? "✓" : i + 1}
          </span>
          {s}
        </li>
      ))}
    </ol>
  );
}

/** First run: who you are, how careful agents should be, a model, and a way to see it work. */
export function Onboarding({ settings }: { settings: UserSettings }) {
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>({
    name: settings.display_name,
    level: settings.default_permission_level,
    workspace: settings.workspace_root,
  });
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState<{ provider: Provider; ok: boolean; detail: string } | undefined>();
  const update = useUpdateSettings();
  const test = useTestProvider();
  const demo = useStartDemo();
  const navigate = useNavigate();

  function finish(then: "home" | "demo" | "skip") {
    const body =
      then === "skip"
        ? { onboarding_completed: true }
        : {
            display_name: draft.name.trim(),
            default_permission_level: draft.level,
            ...(draft.workspace.trim() && draft.workspace.trim() !== settings.workspace_root ? { workspace_root: draft.workspace.trim() } : {}),
            onboarding_completed: true,
          };
    update.mutate(body, {
      onSuccess: () => {
        if (then !== "demo") return void navigate("/");
        demo.mutate(undefined, {
          onSuccess: (o) => void navigate(`/objectives/${o.id}`),
          onError: (e) => toast.error(errorMessage(e)),
        });
      },
      onError: (e) => toast.error(errorMessage(e)),
    });
  }

  function next(e: FormEvent) {
    e.preventDefault();
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  }

  const back = step > 0 && step < 3 ? (
    <Button type="button" variant="ghost" onClick={() => setStep(step - 1)}>
      Back
    </Button>
  ) : null;

  return (
    <div className="flex min-h-full items-start justify-center overflow-y-auto bg-canvas px-4 py-10 sm:items-center">
      <main id="main" className="w-full max-w-xl">
        <div className="mb-6 flex items-center justify-between gap-3">
          <Logo />
          <Button variant="ghost" size="sm" onClick={() => finish("skip")} loading={update.isPending && step < 3}>
            Skip setup
          </Button>
        </div>
        <Stepper step={step} />
        <Card>
          <CardContent className="pt-5">
            {step === 0 ? (
              <form onSubmit={next} className="space-y-5">
                <div>
                  <h1 className="text-xl font-semibold tracking-tight">Welcome to NEXUS</h1>
                  <p className="mt-2 text-[14px] text-fg-muted">
                    Describe what you want done. A Planner turns it into tasks, specialist agents do the work with tools, a Critic and a Verifier check it, and
                    you see every step. Anything risky waits for your approval, and everything stays on this computer unless you connect something that
                    doesn't.
                  </p>
                </div>
                <div>
                  <Label htmlFor="ob-name">What should NEXUS call you? (optional)</Label>
                  <Input id="ob-name" value={draft.name} maxLength={120} onChange={(e) => setDraft({ ...draft, name: e.target.value })} autoFocus />
                </div>
                <div className="flex justify-end">
                  <Button type="submit" variant="primary">
                    Get started
                  </Button>
                </div>
              </form>
            ) : step === 1 ? (
              <form onSubmit={next} className="space-y-5">
                <div>
                  <h1 className="flex items-center gap-2 text-lg font-semibold">
                    <ShieldCheck className="size-5 text-accent-text" aria-hidden="true" /> How careful should agents be?
                  </h1>
                  <p className="mt-1 text-[13px] text-fg-muted">The default for new projects. Each project can change it, and deleting files, running commands and sending data out always ask.</p>
                </div>
                <div role="radiogroup" aria-label="Permission level" className="space-y-2">
                  {LEVELS.map((level) => (
                    <button
                      key={level}
                      type="button"
                      role="radio"
                      aria-checked={draft.level === level}
                      onClick={() => setDraft({ ...draft, level })}
                      className={cn(
                        "w-full rounded-lg border p-3 text-left transition-colors",
                        draft.level === level ? "border-accent bg-accent/10" : "border-line hover:border-accent/60 hover:bg-raised",
                      )}
                    >
                      <span className="text-sm font-medium">
                        {PERMISSION_COPY[level].label}
                        {level === "balanced" ? <span className="ml-2 text-xs font-normal text-fg-subtle">recommended</span> : null}
                      </span>
                      <span className="mt-0.5 block text-xs text-fg-muted">{PERMISSION_COPY[level].help}</span>
                    </button>
                  ))}
                </div>
                <div>
                  <Label htmlFor="ob-workspace">Where project files live</Label>
                  <Input id="ob-workspace" value={draft.workspace} onChange={(e) => setDraft({ ...draft, workspace: e.target.value })} className="font-mono text-xs" spellCheck={false} />
                  {!draft.workspace.trim() ? <FieldError>Enter a folder.</FieldError> : <p className="mt-1 text-xs text-fg-subtle">Agents can only reach files inside a project's own folder here.</p>}
                </div>
                <div className="flex justify-between">
                  {back}
                  <Button type="submit" variant="primary" disabled={!draft.workspace.trim()}>
                    Continue
                  </Button>
                </div>
              </form>
            ) : step === 2 ? (
              <form onSubmit={next} className="space-y-5">
                <div>
                  <h1 className="flex items-center gap-2 text-lg font-semibold">
                    <PlugZap className="size-5 text-accent-text" aria-hidden="true" /> Connect a model
                  </h1>
                  <p className="mt-1 text-[13px] text-fg-muted">
                    NEXUS works with Anthropic, OpenAI, Gemini, or a model on this computer through Ollama or LM Studio (nothing leaves your machine). Keys
                    are kept in your system's secret store and never shown again. You can also do this later, and try the demo without one.
                  </p>
                </div>
                {connected ? (
                  <div role="status" className={cn("rounded-md border px-3 py-2 text-[13px]", connected.ok ? "border-success/40 bg-success/10" : "border-warning/40 bg-warning/10")}>
                    <p className="flex items-center gap-1.5 font-medium">
                      <CheckCircle2 className={cn("size-4", connected.ok ? "text-success" : "text-warning")} aria-hidden="true" />
                      {connected.provider.name}: {connected.ok ? "connected" : "saved, but the test failed"}
                    </p>
                    <p className="mt-0.5 text-xs text-fg-muted">{connected.detail}</p>
                  </div>
                ) : null}
                <div className="flex flex-wrap justify-between gap-2">
                  {back}
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" onClick={() => setConnecting(true)} loading={test.isPending}>
                      <PlugZap /> {connected ? "Connect another" : "Connect a provider"}
                    </Button>
                    <Button type="submit" variant={connected ? "primary" : "ghost"}>
                      {connected ? "Continue" : "Skip for now"}
                    </Button>
                  </div>
                </div>
              </form>
            ) : (
              <div className="space-y-5">
                <div>
                  <h1 className="flex items-center gap-2 text-lg font-semibold">
                    <Sparkles className="size-5 text-accent-text" aria-hidden="true" /> You're set{draft.name.trim() ? `, ${draft.name.trim()}` : ""}
                  </h1>
                  <p className="mt-1 text-[13px] text-fg-muted">
                    Press <kbd className="rounded border border-line-strong px-1 font-mono text-[11px]">Ctrl K</kbd> (⌘K on a Mac) anywhere to jump to a page or
                    do something, and <kbd className="rounded border border-line-strong px-1 font-mono text-[11px]">?</kbd> for all shortcuts.
                  </p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => finish("demo")}
                    disabled={update.isPending || demo.isPending}
                    className="rounded-lg border border-accent bg-accent/10 p-3 text-left transition-colors hover:bg-accent/15 disabled:opacity-60"
                  >
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <FlaskConical className="size-4" aria-hidden="true" /> {demo.isPending ? "Setting up the demo…" : "Try the demo"}
                    </span>
                    <span className="mt-1 block text-xs text-fg-muted">Watch the team compare three (fictional) coding assistants. Scripted, so no model is needed.</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => finish("home")}
                    disabled={update.isPending || demo.isPending}
                    className="rounded-lg border border-line p-3 text-left transition-colors hover:border-accent/60 hover:bg-raised disabled:opacity-60"
                  >
                    <span className="text-sm font-medium">Go to the Command Center</span>
                    <span className="mt-1 block text-xs text-fg-muted">Create a project and give NEXUS your first objective.</span>
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
        {/* Outside the step's form: events from a portal still bubble through the React tree. */}
        <ProviderDialog
          open={connecting}
          onOpenChange={setConnecting}
          onCreated={(provider) =>
            test.mutate(provider.id, {
              onSuccess: (r) => setConnected({ provider, ok: r.ok, detail: r.detail }),
              onError: (e) => setConnected({ provider, ok: false, detail: errorMessage(e) }),
            })
          }
        />
      </main>
    </div>
  );
}
