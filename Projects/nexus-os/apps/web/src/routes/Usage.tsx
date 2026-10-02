import type { Budgets } from "@nexus/schemas";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, ErrorState, FieldError, Input, Label, Select, Skeleton, Switch, toast } from "@nexus/ui";
import { useState, type FormEvent } from "react";
import { errorMessage, useBudgets, useUpdateBudgets, useUsageSummary } from "../lib/queries";

type Group = "model" | "provider" | "agent" | "project" | "day" | "purpose";

const fmtUsd = (n: number) => (n === 0 ? "$0.00" : n < 0.01 ? "<$0.01" : `$${n.toFixed(2)}`);
const fmtNum = (n: number) => n.toLocaleString();

export function UsageRoute() {
  const [days, setDays] = useState(30);
  const [group, setGroup] = useState<Group>("model");
  const usage = useUsageSummary(days, group);
  const budgets = useBudgets();

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold">Usage &amp; budgets</h3>
        <p className="mt-0.5 max-w-xl text-[13px] text-fg-muted">
          Every model call is counted. Cost is shown only where a price is known; set prices per model under Edit on a provider. Calls without a price are counted separately, never as free.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <div>
          <Label htmlFor="usage-days">Period</Label>
          <Select id="usage-days" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-40">
            <option value={1}>Last 24 hours</option>
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </Select>
        </div>
        <div>
          <Label htmlFor="usage-group">Group by</Label>
          <Select id="usage-group" value={group} onChange={(e) => setGroup(e.target.value as Group)} className="w-40">
            {(["model", "provider", "agent", "project", "day", "purpose"] as Group[]).map((g) => (
              <option key={g} value={g}>
                {g[0]?.toUpperCase()}
                {g.slice(1)}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {usage.isPending ? (
        <Skeleton className="h-40" />
      ) : usage.isError ? (
        <ErrorState message={errorMessage(usage.error)} onRetry={() => void usage.refetch()} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Calls</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{fmtNum(usage.data.total_calls)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Tokens</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{fmtNum(usage.data.total_tokens)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Known cost</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{fmtUsd(usage.data.total_cost_usd)}</p>
                {usage.data.unknown_cost_calls > 0 ? (
                  <p className="mt-1 text-xs text-warning">{usage.data.unknown_cost_calls} call(s) have no price set, so they are not included.</p>
                ) : null}
              </CardContent>
            </Card>
          </div>

          <Card>
            {usage.data.groups.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-fg-muted">No model calls in this period yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <caption className="sr-only">Usage grouped by {group}</caption>
                  <thead className="text-xs text-fg-subtle">
                    <tr className="border-b border-line">
                      <th scope="col" className="px-4 py-2 font-medium capitalize">{group}</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Calls</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Input</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Output</th>
                      <th scope="col" className="px-4 py-2 text-right font-medium">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usage.data.groups.map((g) => (
                      <tr key={g.key} className="border-b border-line last:border-0">
                        <th scope="row" className="max-w-[16rem] truncate px-4 py-2 font-mono text-xs font-normal">{g.key}</th>
                        <td className="px-4 py-2 text-right tabular-nums">{fmtNum(g.calls)}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{fmtNum(g.input_tokens)}</td>
                        <td className="px-4 py-2 text-right tabular-nums">{fmtNum(g.output_tokens)}</td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          {fmtUsd(g.cost_usd)}
                          {g.unknown_cost_calls > 0 ? <Badge tone="warning" className="ml-2">+{g.unknown_cost_calls} unpriced</Badge> : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {budgets.isPending ? <Skeleton className="h-64" /> : budgets.isError ? <ErrorState message={errorMessage(budgets.error)} onRetry={() => void budgets.refetch()} /> : <BudgetForm initial={budgets.data} />}
    </div>
  );
}

function num(v: string): number | null {
  return v.trim() === "" ? null : Number(v);
}

function BudgetForm({ initial }: { initial: Budgets }) {
  const update = useUpdateBudgets();
  const [daily, setDaily] = useState(initial.daily_usd?.toString() ?? "");
  const [monthly, setMonthly] = useState(initial.monthly_usd?.toString() ?? "");
  const [dailyTok, setDailyTok] = useState(initial.daily_tokens?.toString() ?? "");
  const [monthlyTok, setMonthlyTok] = useState(initial.monthly_tokens?.toString() ?? "");
  const [expensive, setExpensive] = useState(initial.expensive_call_usd?.toString() ?? "");
  const [warn, setWarn] = useState(String(Math.round((initial.warn_at_fraction ?? 0.8) * 100)));
  const [hard, setHard] = useState(initial.hard_stop ?? true);

  const fields = [daily, monthly, dailyTok, monthlyTok, expensive].map(num);
  const invalid = fields.some((v) => v !== null && (!Number.isFinite(v) || v < 0)) || !(Number(warn) > 0 && Number(warn) <= 100);

  function save(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    update.mutate(
      {
        ...initial,
        daily_usd: num(daily),
        monthly_usd: num(monthly),
        daily_tokens: num(dailyTok) === null ? null : Math.round(num(dailyTok)!),
        monthly_tokens: num(monthlyTok) === null ? null : Math.round(num(monthlyTok)!),
        expensive_call_usd: num(expensive),
        warn_at_fraction: Number(warn) / 100,
        hard_stop: hard,
      },
      { onSuccess: () => toast.success("Budgets saved"), onError: (err) => toast.error(errorMessage(err)) },
    );
  }

  const field = (id: string, label: string, value: string, set: (v: string) => void, unit: string, step = "any") => (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-2">
        <Input id={id} inputMode="decimal" type="number" min={0} step={step} value={value} onChange={(e) => set(e.target.value)} placeholder="No limit" />
        <span className="text-xs text-fg-subtle">{unit}</span>
      </div>
    </div>
  );

  return (
    <form onSubmit={save}>
      <Card>
        <CardHeader>
          <CardTitle>Budgets</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-[13px] text-fg-muted">
            NEXUS checks the projected total before each call. Dollar limits only count calls whose price is known; token limits count everything. Per-project limits are set on each project.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            {field("b-daily", "Daily limit", daily, setDaily, "USD")}
            {field("b-monthly", "Monthly limit", monthly, setMonthly, "USD")}
            {field("b-dtok", "Daily token limit", dailyTok, setDailyTok, "tokens", "1")}
            {field("b-mtok", "Monthly token limit", monthlyTok, setMonthlyTok, "tokens", "1")}
            {field("b-exp", "Warn before a single call costing more than", expensive, setExpensive, "USD")}
            {field("b-warn", "Warn when a limit is this full", warn, setWarn, "%", "1")}
          </div>
          <label className="flex items-center gap-3 text-sm">
            <Switch checked={hard} onCheckedChange={setHard} aria-label="Stop calls when a limit is reached" />
            <span>
              Stop calls when a limit would be exceeded
              <span className="block text-xs text-fg-muted">Off means NEXUS only warns and records it.</span>
            </span>
          </label>
          {invalid ? <FieldError>Limits must be zero or more, and the warning threshold between 1 and 100.</FieldError> : null}
          <FieldError>{update.isError ? errorMessage(update.error) : undefined}</FieldError>
          <Button type="submit" variant="primary" loading={update.isPending} disabled={invalid}>
            Save budgets
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
