"""A tiny, safe expression evaluator (no eval). Arithmetic, comparisons, boolean logic, a fixed
function whitelist, and named variables that the caller supplies. Used by the calculator tool and,
later, workflow conditions."""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping
from typing import Any

MAX_NODES = 300
MAX_DIGITS = 4000


class ExpressionError(ValueError):
    pass


def _pow(base: Any, exp: Any) -> Any:
    if (
        isinstance(exp, int)
        and isinstance(base, int)
        and (abs(exp) > 2000 or (abs(base) > 1 and abs(exp) * math.log2(abs(base)) > MAX_DIGITS * 3.33))
    ):
        raise ExpressionError("That exponent is too large to compute safely.")
    return base**exp


_BIN: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: _pow,
}
_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
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
FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "int": int,
    "float": float,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": lambda n: math.factorial(n) if 0 <= n <= 500 else _too_big(),
    "gcd": math.gcd,
    "radians": math.radians,
    "degrees": math.degrees,
    "pow": _pow,
}
CONSTANTS: dict[str, Any] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
    "true": True,
    "false": False,
    "null": None,
}


def _too_big() -> Any:
    raise ExpressionError("That value is too large to compute safely.")


def evaluate(expression: str, variables: Mapping[str, Any] | None = None) -> Any:
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
    names = {**CONSTANTS, **(variables or {})}

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
            raise ExpressionError(f"Unknown name '{node.id}'.")
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            result = _BIN[type(node.op)](ev(node.left), ev(node.right))
            if isinstance(result, int) and len(str(result)) > MAX_DIGITS:
                raise ExpressionError("The result is too large.")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.BoolOp):
            values = (ev(v) for v in node.values)
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators, strict=True):
                right = ev(comp)
                if type(op) not in _CMP or not _CMP[type(op)](left, right):
                    if type(op) not in _CMP:
                        raise ExpressionError("Unsupported comparison.")
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return ev(node.body) if ev(node.test) else ev(node.orelse)
        if isinstance(node, (ast.List, ast.Tuple)):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise ExpressionError("Only the built-in math functions can be called.")
            return FUNCTIONS[node.func.id](*[ev(a) for a in node.args])
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            return ev(node.value)[node.slice.value]
        raise ExpressionError(f"'{type(node).__name__}' is not allowed in expressions.")

    try:
        return ev(tree)
    except ExpressionError:
        raise
    except ZeroDivisionError:
        raise ExpressionError("Division by zero.") from None
    except (ValueError, TypeError, OverflowError, KeyError, IndexError) as exc:
        raise ExpressionError(f"Could not compute that: {exc}") from None
