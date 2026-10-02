import { Button, Input } from "@nexus/ui";
import { Plus, X } from "lucide-react";
import type { Pair, SecretRow } from "./model";

interface Props<T extends Pair> {
  label: string; // "Variable", "Header"
  rows: T[];
  onChange: (rows: T[]) => void;
  blank: () => T;
  keyPlaceholder: string;
  secret?: boolean;
}

/** Name/value rows. Secret rows take a value that is sent once and never shown again. */
export function PairsEditor<T extends Pair>({ label, rows, onChange, blank, keyPlaceholder, secret = false }: Props<T>) {
  const set = (i: number, patch: Partial<Pair>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-2">
      {rows.map((r, i) => {
        const saved = secret && (r as unknown as SecretRow).saved;
        const n = i + 1;
        return (
          <div key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_auto] items-center gap-2">
            <Input
              aria-label={`${label} ${n} name`}
              value={r.key}
              readOnly={saved}
              placeholder={keyPlaceholder}
              onChange={(e) => set(i, { key: e.target.value })}
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Input
              aria-label={`${label} ${n} value`}
              type={secret ? "password" : "text"}
              autoComplete={secret ? "new-password" : "off"}
              value={r.value}
              placeholder={saved ? "Saved · type to replace" : secret ? "Secret value" : "Value"}
              onChange={(e) => set(i, { value: e.target.value })}
              className="font-mono text-xs"
              spellCheck={false}
            />
            <Button
              type="button"
              size="icon-sm"
              variant="ghost"
              aria-label={`Remove ${r.key || `${label.toLowerCase()} ${n}`}`}
              onClick={() => onChange(rows.filter((_, j) => j !== i))}
            >
              <X />
            </Button>
          </div>
        );
      })}
      <Button type="button" size="sm" variant="ghost" onClick={() => onChange([...rows, blank()])}>
        <Plus /> Add {label.toLowerCase()}
      </Button>
    </div>
  );
}
