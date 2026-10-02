"""Workflow expressions and templates. No ``eval``: a whitelisted AST walk over plain data.

Expressions read the run's data: ``inputs.topic``, ``nodes.research.output.summary``,
``len(nodes.fetch.output.items) > 3 and inputs.urgent``. Only mappings, lists, strings, numbers,
booleans and None exist here; ``a.b`` is a key lookup on a mapping (there is no attribute access on
Python objects, so ``__class__``-style escapes do not exist). Sizes are capped so an expression
cannot build a huge string or list.

Templates are text with ``{{ expression }}`` holes. For agent prompts, values that come from other
nodes are *not* spliced into the instructions: each becomes a fenced context block, and the prompt
says where to find it (see ``render_prompt``).
"""

from __future__ import annotations

import ast
import json
import operator
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

MAX_NODES = 200
MAX_TEXT = 100_000
MAX_ITEMS = 10_000
_HOLE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.S)


class ExpressionError(ValueError):
    pass


def _check_size(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_TEXT:
        raise ExpressionError("The result is too long.")
    if isinstance(value, (list, dict)) and len(value) > MAX_ITEMS:
        raise ExpressionError("The result has too many items.")
    return value


def _mul(a: Any, b: Any) -> Any:
    if isinstance(a, (str, list)) or isinstance(b, (str, list)):
        n = b if isinstance(a, (str, list)) else a
        seq = a if isinstance(a, (str, list)) else b
        if not isinstance(n, int) or n * len(seq) > MAX_TEXT:
            raise ExpressionError("The result is too long.")
    return a * b


_BIN: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: _mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_CMP: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _text(v: Any) -> str:
    """How a value reads when placed in text: strings as-is, everything else as compact JSON."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(v, ensure_ascii=False, default=str)


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "len": len,
    "str": _text,
    "int": int,
    "float": float,
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "lower": lambda s: str(s).lower(),
    "upper": lambda s: str(s).upper(),
    "trim": lambda s: str(s).strip(),
    "contains": lambda a, b: b in a,
    "startswith": lambda s, p: str(s).startswith(p),
    "endswith": lambda s, p: str(s).endswith(p),
    "join": lambda items, sep=", ": str(sep).join(_text(i) for i in items),
    "split": lambda s, sep=",": [p.strip() for p in str(s).split(sep)],
    "default": lambda v, fallback: fallback if v is None or v == "" else v,
    "keys": lambda m: list(m.keys()) if isinstance(m, Mapping) else [],
    "first": lambda items: items[0] if items else None,
    "last": lambda items: items[-1] if items else None,
}
CONSTANTS: dict[str, Any] = {"true": True, "false": False, "null": None, "none": None}


def parse(expression: str) -> ast.Expression:
    if not isinstance(expression, str) or not expression.strip():
        raise ExpressionError("The expression is empty.")
    if len(expression) > 2000:
        raise ExpressionError("The expression is too long.")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"Not a valid expression: {exc.msg}") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ExpressionError("The expression is too complex.")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ExpressionError("Names starting with '_' are not allowed.")
    return tree


def root_names(expression: str) -> set[str]:
    """The top-level names an expression reads (e.g. {'inputs', 'nodes'})."""
    return {
        n.id
        for n in ast.walk(parse(expression))
        if isinstance(n, ast.Name) and n.id not in FUNCTIONS and n.id not in CONSTANTS
    }


def evaluate(expression: str, variables: Mapping[str, Any]) -> Any:
    tree = parse(expression)
    names = {**CONSTANTS, **variables}

    def lookup(container: Any, key: Any) -> Any:
        if isinstance(container, Mapping):
            if key not in container:
                return None  # a missing key reads as null, so optional fields are easy to test
            return container[key]
        if isinstance(container, (list, str)) and isinstance(key, int):
            return container[key]
        raise ExpressionError(f"Cannot read '{key}' from {type(container).__name__}.")

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, bool, str)) or node.value is None:
                return node.value
            raise ExpressionError("Unsupported literal.")
        if isinstance(node, ast.Name):
            if node.id in names:
                return names[node.id]
            raise ExpressionError(f"Unknown name '{node.id}'. Use inputs.<name> or nodes.<id>.output.")
        if isinstance(node, ast.Attribute):
            return lookup(ev(node.value), node.attr)
        if isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Slice):
                raise ExpressionError("Slices are not supported.")
            return lookup(ev(node.value), ev(node.slice))
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _check_size(_BIN[type(node.op)](ev(node.left), ev(node.right)))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +ev(node.operand)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for v in node.values:
                    result = ev(v)
                    if not result:
                        return result
                return result
            result = False
            for v in node.values:
                result = ev(v)
                if result:
                    return result
            return result
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators, strict=True):
                if type(op) not in _CMP:
                    raise ExpressionError("Unsupported comparison.")
                right = ev(comp)
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return ev(node.body) if ev(node.test) else ev(node.orelse)
        if isinstance(node, (ast.List, ast.Tuple)):
            return _check_size([ev(e) for e in node.elts])
        if isinstance(node, ast.Dict):
            if any(k is None for k in node.keys):
                raise ExpressionError("'**' is not supported.")
            return {ev(k): ev(v) for k, v in zip(node.keys, node.values, strict=True) if k is not None}
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise ExpressionError(f"Only these functions can be called: {', '.join(sorted(FUNCTIONS))}.")
            return _check_size(FUNCTIONS[node.func.id](*[ev(a) for a in node.args]))
        raise ExpressionError(f"'{type(node).__name__}' is not allowed in expressions.")

    try:
        return ev(tree)
    except ExpressionError:
        raise
    except ZeroDivisionError:
        raise ExpressionError("Division by zero.") from None
    except (ValueError, TypeError, OverflowError, KeyError, IndexError, AttributeError) as exc:
        raise ExpressionError(f"Could not evaluate: {exc}") from None


def holes(template: str) -> list[str]:
    return [m.group(1) for m in _HOLE.finditer(template)]


def render(template: str, variables: Mapping[str, Any]) -> str:
    """Fill every {{ expression }} with its value as text."""
    return str(_check_size(_HOLE.sub(lambda m: _text(evaluate(m.group(1), variables)), template)))


def render_value(value: Any, variables: Mapping[str, Any]) -> Any:
    """Tool arguments: a string that is exactly one hole keeps the value's type; other strings are
    rendered as text; lists and mappings are rendered recursively."""
    if isinstance(value, str):
        whole = _HOLE.fullmatch(value.strip())
        if whole:
            return evaluate(whole.group(1), variables)
        return render(value, variables) if "{{" in value else value
    if isinstance(value, list):
        return [render_value(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: render_value(v, variables) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    data: list[tuple[str, str]]  # (label, value) handed to the agent as fenced context


def render_prompt(template: str, variables: Mapping[str, Any]) -> RenderedPrompt:
    """Render an agent prompt. Values from the run's inputs (given by the person or a schedule) are
    written in; values from other nodes (possibly shaped by untrusted content) are passed as data."""
    data: list[tuple[str, str]] = []

    def fill(m: re.Match[str]) -> str:
        expr = m.group(1)
        value = _text(evaluate(expr, variables))
        if root_names(expr) <= {"inputs"}:
            return value
        label = expr.strip()
        data.append((label, value))
        return f"[the value of {label}, provided below as data]"

    return RenderedPrompt(_check_size(_HOLE.sub(fill, template)), data)
