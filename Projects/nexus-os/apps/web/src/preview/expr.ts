/**
 * Workflow expressions and templates for the browser preview: the same small language as the desktop
 * (`services/api/app/workflows/expr.py`), parsed by hand. No `eval`: only plain data, a few
 * operators and the listed functions exist.
 *
 *   inputs.topic · nodes.research.output.summary · len(nodes.fetch.output.items) > 3 and inputs.urgent
 *   "yes" if inputs.n >= 2 else "no" · join(split(inputs.tags), " / ")
 */

export class ExpressionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ExpressionError";
  }
}

const MAX_TEXT = 100_000;
const MAX_ITEMS = 10_000;
const MAX_NODES = 200;
const HOLE = /\{\{\s*([\s\S]+?)\s*\}\}/g;

type Value = unknown;
type Node =
  | { t: "lit"; v: Value }
  | { t: "name"; id: string }
  | { t: "attr"; obj: Node; key: string }
  | { t: "index"; obj: Node; key: Node }
  | { t: "call"; fn: string; args: Node[] }
  | { t: "list"; items: Node[] }
  | { t: "dict"; entries: [Node, Node][] }
  | { t: "unary"; op: string; arg: Node }
  | { t: "bin"; op: string; left: Node; right: Node }
  | { t: "bool"; op: "and" | "or"; left: Node; right: Node }
  | { t: "cmp"; first: Node; rest: [string, Node][] }
  | { t: "if"; test: Node; then: Node; else: Node };

// ---- tokens ------------------------------------------------------------------------------------------

interface Tok {
  k: "num" | "str" | "name" | "op" | "end";
  v: string;
}

function tokenize(src: string): Tok[] {
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i] ?? "";
    if (/\s/.test(c)) {
      i++;
      continue;
    }
    if (/[0-9]/.test(c) || (c === "." && /[0-9]/.test(src[i + 1] ?? ""))) {
      const m = /^(\d+\.?\d*(e[+-]?\d+)?|\.\d+(e[+-]?\d+)?)/i.exec(src.slice(i));
      out.push({ k: "num", v: m?.[0] ?? c });
      i += m?.[0].length ?? 1;
      continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      let s = "";
      while (j < src.length && src[j] !== c) {
        if (src[j] === "\\" && j + 1 < src.length) {
          const e = src[j + 1] ?? "";
          s += e === "n" ? "\n" : e === "t" ? "\t" : e;
          j += 2;
        } else s += src[j++];
      }
      if (j >= src.length) throw new ExpressionError("Not a valid expression: a quoted text is not closed.");
      out.push({ k: "str", v: s });
      i = j + 1;
      continue;
    }
    if (/[A-Za-z_]/.test(c)) {
      const m = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
      const word = m?.[0] ?? c;
      out.push({ k: ["and", "or", "not", "in", "if", "else", "is"].includes(word) ? "op" : "name", v: word });
      i += word.length;
      continue;
    }
    const two = src.slice(i, i + 2);
    if (["==", "!=", "<=", ">=", "//", "**"].includes(two)) {
      if (two === "**") throw new ExpressionError("'**' is not supported.");
      out.push({ k: "op", v: two });
      i += 2;
      continue;
    }
    if ("+-*/%<>()[]{},.:".includes(c)) {
      out.push({ k: "op", v: c });
      i++;
      continue;
    }
    throw new ExpressionError(`Not a valid expression: unexpected '${c}'.`);
  }
  out.push({ k: "end", v: "" });
  return out;
}

// ---- parser (Python precedence) -----------------------------------------------------------------------

export function parse(expression: string): Node {
  if (typeof expression !== "string" || !expression.trim()) throw new ExpressionError("The expression is empty.");
  if (expression.length > 2000) throw new ExpressionError("The expression is too long.");
  const toks = tokenize(expression);
  let p = 0;
  let count = 0;
  const peek = () => toks[p] ?? { k: "end", v: "" };
  const isOp = (v: string) => peek().k === "op" && peek().v === v;
  const take = () => toks[p++] ?? { k: "end", v: "" };
  const expect = (v: string) => {
    if (!isOp(v)) throw new ExpressionError(`Not a valid expression: expected '${v}'.`);
    take();
  };
  const node = <T extends Node>(n: T): T => {
    if (++count > MAX_NODES) throw new ExpressionError("The expression is too complex.");
    return n;
  };

  const ternary = (): Node => {
    const body = or();
    if (isOp("if")) {
      take();
      const test = or();
      expect("else");
      return node({ t: "if", test, then: body, else: ternary() });
    }
    return body;
  };
  const or = (): Node => {
    let left = and();
    while (isOp("or")) {
      take();
      left = node({ t: "bool", op: "or", left, right: and() });
    }
    return left;
  };
  const and = (): Node => {
    let left = not();
    while (isOp("and")) {
      take();
      left = node({ t: "bool", op: "and", left, right: not() });
    }
    return left;
  };
  const not = (): Node => {
    if (isOp("not")) {
      take();
      return node({ t: "unary", op: "not", arg: not() });
    }
    return compare();
  };
  const compare = (): Node => {
    const first = sum();
    const rest: [string, Node][] = [];
    for (;;) {
      const t = peek();
      if (t.k !== "op") break;
      if (["==", "!=", "<", "<=", ">", ">="].includes(t.v)) {
        take();
        rest.push([t.v, sum()]);
      } else if (t.v === "in") {
        take();
        rest.push(["in", sum()]);
      } else if (t.v === "not" && toks[p + 1]?.v === "in") {
        p += 2;
        rest.push(["not in", sum()]);
      } else if (t.v === "is") {
        throw new ExpressionError("Use == and != instead of 'is'.");
      } else break;
    }
    return rest.length ? node({ t: "cmp", first, rest }) : first;
  };
  const sum = (): Node => {
    let left = product();
    while (isOp("+") || isOp("-")) {
      const op = take().v;
      left = node({ t: "bin", op, left, right: product() });
    }
    return left;
  };
  const product = (): Node => {
    let left = unary();
    while (isOp("*") || isOp("/") || isOp("//") || isOp("%")) {
      const op = take().v;
      left = node({ t: "bin", op, left, right: unary() });
    }
    return left;
  };
  const unary = (): Node => {
    if (isOp("-") || isOp("+")) {
      const op = take().v;
      return node({ t: "unary", op, arg: unary() });
    }
    return postfix();
  };
  const postfix = (): Node => {
    let n = atom();
    for (;;) {
      if (isOp(".")) {
        take();
        const t = take();
        if (t.k !== "name") throw new ExpressionError("Not a valid expression: expected a name after '.'.");
        if (t.v.startsWith("_")) throw new ExpressionError("Names starting with '_' are not allowed.");
        n = node({ t: "attr", obj: n, key: t.v });
      } else if (isOp("[")) {
        take();
        if (isOp(":")) throw new ExpressionError("Slices are not supported.");
        const key = ternary();
        if (isOp(":")) throw new ExpressionError("Slices are not supported.");
        expect("]");
        n = node({ t: "index", obj: n, key });
      } else if (isOp("(")) {
        if (n.t !== "name") throw new ExpressionError(`Only these functions can be called: ${Object.keys(FUNCTIONS).sort().join(", ")}.`);
        take();
        const args: Node[] = [];
        while (!isOp(")")) {
          if (peek().k === "name" && toks[p + 1]?.v === "=") throw new ExpressionError("Named arguments are not supported.");
          args.push(ternary());
          if (!isOp(")")) expect(",");
        }
        take();
        n = node({ t: "call", fn: n.id, args });
      } else return n;
    }
  };
  const atom = (): Node => {
    const t = take();
    if (t.k === "num") return node({ t: "lit", v: Number(t.v) });
    if (t.k === "str") {
      let v = t.v;
      while (peek().k === "str") v += take().v; // "a" "b" joins, as in Python
      return node({ t: "lit", v });
    }
    if (t.k === "name") {
      if (t.v === "True") return node({ t: "lit", v: true });
      if (t.v === "False") return node({ t: "lit", v: false });
      if (t.v === "None") return node({ t: "lit", v: null });
      return node({ t: "name", id: t.v });
    }
    if (t.k === "op" && t.v === "(") {
      if (isOp(")")) {
        take();
        return node({ t: "list", items: [] });
      }
      const first = ternary();
      if (isOp(",")) {
        const items = [first];
        while (isOp(",")) {
          take();
          if (isOp(")")) break;
          items.push(ternary());
        }
        expect(")");
        return node({ t: "list", items });
      }
      expect(")");
      return first;
    }
    if (t.k === "op" && t.v === "[") {
      const items: Node[] = [];
      while (!isOp("]")) {
        items.push(ternary());
        if (!isOp("]")) expect(",");
      }
      take();
      return node({ t: "list", items });
    }
    if (t.k === "op" && t.v === "{") {
      const entries: [Node, Node][] = [];
      while (!isOp("}")) {
        const k = ternary();
        expect(":");
        entries.push([k, ternary()]);
        if (!isOp("}")) expect(",");
      }
      take();
      return node({ t: "dict", entries });
    }
    throw new ExpressionError(`Not a valid expression${t.k === "end" ? ": it ends too soon" : `: unexpected '${t.v}'`}.`);
  };

  const tree = ternary();
  if (peek().k !== "end") throw new ExpressionError(`Not a valid expression: unexpected '${peek().v}'.`);
  return tree;
}

// ---- values -------------------------------------------------------------------------------------------

const isMap = (v: Value): v is Record<string, Value> => typeof v === "object" && v !== null && !Array.isArray(v);

/** How a value reads in text: strings as-is, everything else as compact JSON. */
export function text(v: Value): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  return JSON.stringify(v);
}

export function truthy(v: Value): boolean {
  if (Array.isArray(v)) return v.length > 0;
  if (isMap(v)) return Object.keys(v).length > 0;
  return Boolean(v);
}

const equal = (a: Value, b: Value): boolean =>
  typeof a === "object" || typeof b === "object" ? JSON.stringify(a) === JSON.stringify(b) : a === b;

function size(v: Value): Value {
  if (typeof v === "string" && v.length > MAX_TEXT) throw new ExpressionError("The result is too long.");
  if (Array.isArray(v) && v.length > MAX_ITEMS) throw new ExpressionError("The result has too many items.");
  if (isMap(v) && Object.keys(v).length > MAX_ITEMS) throw new ExpressionError("The result has too many items.");
  return v;
}

const num = (v: Value, what: string): number => {
  if (typeof v === "number") return v;
  if (typeof v === "boolean") return Number(v);
  throw new ExpressionError(`Could not evaluate: ${what} needs numbers, not ${v === null ? "null" : typeof v}.`);
};

function contains(container: Value, item: Value): boolean {
  if (typeof container === "string") {
    if (typeof item !== "string") throw new ExpressionError("Could not evaluate: 'in' on text needs text on the left.");
    return container.includes(item);
  }
  if (Array.isArray(container)) return container.some((x) => equal(x, item));
  if (isMap(container)) return typeof item === "string" && item in container;
  throw new ExpressionError("Could not evaluate: 'in' needs text, a list or a mapping on the right.");
}

function asList(v: Value, fn: string): Value[] {
  if (Array.isArray(v)) return v;
  if (typeof v === "string") return [...v];
  if (isMap(v)) return Object.keys(v);
  throw new ExpressionError(`Could not evaluate: ${fn}() needs a list.`);
}

const FUNCTIONS: Record<string, (...a: Value[]) => Value> = {
  len: (v) =>
    typeof v === "string" || Array.isArray(v)
      ? v.length
      : isMap(v)
        ? Object.keys(v).length
        : (() => {
            throw new ExpressionError("Could not evaluate: len() needs text, a list or a mapping.");
          })(),
  str: (v) => text(v),
  int: (v) => {
    if (typeof v === "string") {
      if (!/^\s*[+-]?\d+\s*$/.test(v)) throw new ExpressionError(`Could not evaluate: '${v.slice(0, 40)}' is not a whole number.`);
      return Number.parseInt(v, 10);
    }
    return Math.trunc(num(v, "int()"));
  },
  float: (v) => {
    const n = typeof v === "string" ? Number(v.trim()) : num(v, "float()");
    if (Number.isNaN(n)) throw new ExpressionError(`Could not evaluate: '${text(v).slice(0, 40)}' is not a number.`);
    return n;
  },
  round: (v, digits) => {
    const d = digits === undefined ? 0 : num(digits, "round()");
    const f = 10 ** d;
    return Math.round(num(v, "round()") * f) / f;
  },
  abs: (v) => Math.abs(num(v, "abs()")),
  min: (...a) => pick(a, "min", (x, y) => x < y),
  max: (...a) => pick(a, "max", (x, y) => x > y),
  sum: (v) => asList(v, "sum").reduce<number>((s, x) => s + num(x, "sum()"), 0),
  lower: (v) => text(v).toLowerCase(),
  upper: (v) => text(v).toUpperCase(),
  trim: (v) => text(v).trim(),
  contains: (a, b) => contains(a, b),
  startswith: (s, p) => text(s).startsWith(text(p)),
  endswith: (s, p) => text(s).endsWith(text(p)),
  join: (items, sep = ", ") => asList(items, "join").map(text).join(text(sep)),
  split: (s, sep = ",") =>
    text(s)
      .split(text(sep))
      .map((x) => x.trim()),
  default: (v, fallback) => (v === null || v === undefined || v === "" ? fallback : v),
  keys: (m) => (isMap(m) ? Object.keys(m) : []),
  first: (items) => (Array.isArray(items) && items.length ? items[0] : null),
  last: (items) => (Array.isArray(items) && items.length ? items[items.length - 1] : null),
};

function pick(args: Value[], fn: string, better: (a: never, b: never) => boolean): Value {
  const list = args.length === 1 ? asList(args[0], fn) : args;
  if (!list.length) throw new ExpressionError(`Could not evaluate: ${fn}() of an empty list.`);
  return list.reduce((best, x) => (better(x as never, best as never) ? x : best));
}

const CONSTANTS: Record<string, Value> = { true: true, false: false, null: null, none: null };

function binary(op: string, a: Value, b: Value): Value {
  switch (op) {
    case "+":
      if (typeof a === "string" && typeof b === "string") return a + b;
      if (Array.isArray(a) && Array.isArray(b)) return [...a, ...b];
      if (typeof a === "string" || typeof b === "string")
        throw new ExpressionError("Could not evaluate: text can only be added to text (use str() first).");
      return num(a, "+") + num(b, "+");
    case "-":
      return num(a, "-") - num(b, "-");
    case "*": {
      const seq = typeof a === "string" || Array.isArray(a) ? a : typeof b === "string" || Array.isArray(b) ? b : null;
      if (seq !== null) {
        const n = seq === a ? b : a;
        if (typeof n !== "number" || !Number.isInteger(n) || n * seq.length > MAX_TEXT)
          throw new ExpressionError("The result is too long.");
        return typeof seq === "string" ? seq.repeat(Math.max(n, 0)) : Array.from({ length: Math.max(n, 0) }, () => seq).flat();
      }
      return num(a, "*") * num(b, "*");
    }
    case "/":
    case "//":
    case "%": {
      const x = num(a, op);
      const y = num(b, op);
      if (y === 0) throw new ExpressionError("Division by zero.");
      if (op === "/") return x / y;
      if (op === "//") return Math.floor(x / y);
      return ((x % y) + y) % y;
    }
  }
  throw new ExpressionError(`'${op}' is not allowed in expressions.`);
}

function compareOp(op: string, a: Value, b: Value): boolean {
  switch (op) {
    case "==":
      return equal(a, b);
    case "!=":
      return !equal(a, b);
    case "in":
      return contains(b, a);
    case "not in":
      return !contains(b, a);
  }
  const bothNum = typeof a === "number" && typeof b === "number";
  const bothStr = typeof a === "string" && typeof b === "string";
  if (!bothNum && !bothStr)
    throw new ExpressionError(
      `Could not evaluate: cannot compare ${a === null ? "null" : typeof a} with ${b === null ? "null" : typeof b} using '${op}'.`,
    );
  const x = a as number | string;
  const y = b as number | string;
  return op === "<" ? x < y : op === "<=" ? x <= y : op === ">" ? x > y : x >= y;
}

export type Variables = Record<string, Value>;

export function evaluate(expression: string, variables: Variables): Value {
  const tree = parse(expression);
  const names: Variables = { ...CONSTANTS, ...variables };
  const lookup = (container: Value, key: Value): Value => {
    if (isMap(container)) return typeof key === "string" && Object.hasOwn(container, key) ? container[key] : null;
    if ((Array.isArray(container) || typeof container === "string") && typeof key === "number" && Number.isInteger(key)) {
      const i = key < 0 ? container.length + key : key;
      if (i < 0 || i >= container.length) throw new ExpressionError("Could not evaluate: index out of range.");
      return container[i];
    }
    throw new ExpressionError(
      `Cannot read '${text(key)}' from ${container === null ? "null" : Array.isArray(container) ? "a list" : typeof container}.`,
    );
  };
  const ev = (n: Node): Value => {
    switch (n.t) {
      case "lit":
        return n.v;
      case "name":
        if (Object.hasOwn(names, n.id)) return names[n.id];
        throw new ExpressionError(`Unknown name '${n.id}'. Use inputs.<name> or nodes.<id>.output.`);
      case "attr":
        return lookup(ev(n.obj), n.key);
      case "index":
        return lookup(ev(n.obj), ev(n.key));
      case "call": {
        const fn = FUNCTIONS[n.fn];
        if (!fn) throw new ExpressionError(`Only these functions can be called: ${Object.keys(FUNCTIONS).sort().join(", ")}.`);
        return size(fn(...n.args.map(ev)));
      }
      case "list":
        return size(n.items.map(ev));
      case "dict":
        return Object.fromEntries(n.entries.map(([k, v]) => [text(ev(k)), ev(v)]));
      case "unary": {
        const v = ev(n.arg);
        if (n.op === "not") return !truthy(v);
        return n.op === "-" ? -num(v, "-") : num(v, "+");
      }
      case "bin":
        return size(binary(n.op, ev(n.left), ev(n.right)));
      case "bool": {
        const left = ev(n.left);
        if (n.op === "and") return truthy(left) ? ev(n.right) : left;
        return truthy(left) ? left : ev(n.right);
      }
      case "cmp": {
        let left = ev(n.first);
        for (const [op, comp] of n.rest) {
          const right = ev(comp);
          if (!compareOp(op, left, right)) return false;
          left = right;
        }
        return true;
      }
      case "if":
        return truthy(ev(n.test)) ? ev(n.then) : ev(n.else);
    }
  };
  return ev(tree);
}

/** The top-level names an expression reads (e.g. inputs, nodes). */
export function rootNames(expression: string): Set<string> {
  const found = new Set<string>();
  const walk = (n: Node): void => {
    switch (n.t) {
      case "name":
        if (!(n.id in CONSTANTS)) found.add(n.id);
        return;
      case "attr":
        return walk(n.obj);
      case "index":
        walk(n.obj);
        return walk(n.key);
      case "call":
        return n.args.forEach(walk);
      case "list":
        return n.items.forEach(walk);
      case "dict":
        return n.entries.forEach(([k, v]) => (walk(k), walk(v)));
      case "unary":
        return walk(n.arg);
      case "bin":
      case "bool":
        walk(n.left);
        return walk(n.right);
      case "cmp":
        walk(n.first);
        return n.rest.forEach(([, c]) => walk(c));
      case "if":
        walk(n.test);
        walk(n.then);
        return walk(n.else);
    }
  };
  walk(parse(expression));
  return found;
}

export function holes(template: string): string[] {
  return [...template.matchAll(HOLE)].map((m) => m[1] ?? "");
}

/** Fill every {{ expression }} with its value as text. */
export function render(template: string, variables: Variables): string {
  return size(template.replace(HOLE, (_, e: string) => text(evaluate(e, variables)))) as string;
}

/**
 * An agent step's prompt: values from the run's inputs are written in; values from other steps
 * (which may carry outside text) are handed over as data, with a note in the prompt saying where.
 */
export function renderPrompt(template: string, variables: Variables): { text: string; data: [string, string][] } {
  const data: [string, string][] = [];
  const out = template.replace(HOLE, (_, e: string) => {
    const value = text(evaluate(e, variables));
    if ([...rootNames(e)].every((n) => n === "inputs")) return value;
    const label = e.trim();
    data.push([label, value]);
    return `[the value of ${label}, provided below as data]`;
  });
  return { text: size(out) as string, data };
}
