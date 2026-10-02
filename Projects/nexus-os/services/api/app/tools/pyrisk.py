"""Static risk classification of Python code before it runs.

This decides whether a human must approve, it is NOT what contains the code. Code that only uses
a small allow-list of pure standard-library modules and touches no files outside its scratch
directory is MODERATE. Anything else is HIGH and asks. The scan is deliberately conservative and is
one layer among several (approval, sandbox limits, taint tracking).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

SAFE_MODULES = frozenset(
    {
        "math",
        "cmath",
        "statistics",
        "random",
        "json",
        "csv",
        "re",
        "datetime",
        "time",
        "calendar",
        "itertools",
        "functools",
        "collections",
        "heapq",
        "bisect",
        "string",
        "textwrap",
        "decimal",
        "fractions",
        "dataclasses",
        "typing",
        "enum",
        "operator",
        "copy",
        "hashlib",
        "base64",
        "html",
        "difflib",
        "unicodedata",
        "pprint",
        "numbers",
        "array",
        "abc",
        "contextlib",
        "zoneinfo",
        "uuid",
        "urllib.parse",
        "__future__",
    }
)
BANNED_CALLS = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "input",
        "breakpoint",
        "globals",
        "locals",
        "vars",
        "memoryview",
    }
)
DUNDER_ATTRS = frozenset(
    {
        "__class__",
        "__bases__",
        "__mro__",
        "__subclasses__",
        "__globals__",
        "__builtins__",
        "__dict__",
        "__code__",
        "__closure__",
        "__import__",
        "__loader__",
        "__spec__",
        "__reduce__",
        "__reduce_ex__",
        "__getattribute__",
    }
)


@dataclass(frozen=True)
class PythonRisk:
    risky: bool
    findings: tuple[str, ...]


def _unsafe_open_path(call: ast.Call) -> bool:
    """open() is fine only for a literal, relative, non-escaping path (the scratch directory)."""
    if not call.args or not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str):
        return True
    path = call.args[0].value.replace("\\", "/")
    if path.startswith(("/", "~")) or ".." in path.split("/") or (len(path) > 1 and path[1] == ":"):
        return True
    return any(kw.arg in ("opener", "closefd") for kw in call.keywords)


_RISKY_METHODS = frozenset({"open", "system", "popen", "spawn", "fork", "exec", "load", "loads"})


def _risky_method(fn: ast.Attribute) -> bool:
    """Methods that open files or start processes. ``json.load(s)`` is the harmless exception."""
    if fn.attr not in _RISKY_METHODS:
        return False
    return not (fn.attr in ("load", "loads") and isinstance(fn.value, ast.Name) and fn.value.id == "json")


def classify_python(code: str) -> PythonRisk:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return PythonRisk(False, ())  # will fail harmlessly when run
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in SAFE_MODULES and alias.name.split(".")[0] not in {
                    m.split(".")[0] for m in SAFE_MODULES if "." not in m
                }:
                    findings.append(f"imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or (
                mod not in SAFE_MODULES and mod.split(".")[0] not in {m for m in SAFE_MODULES if "." not in m}
            ):
                findings.append(f"imports from {'.' * node.level}{mod}")
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                if fn.id in BANNED_CALLS:
                    findings.append(f"calls {fn.id}()")
                elif fn.id == "open" and _unsafe_open_path(node):
                    findings.append("opens a file outside its scratch directory")
                elif fn.id in ("getattr", "setattr", "delattr"):
                    attr = node.args[1] if len(node.args) > 1 else None
                    if not (
                        isinstance(attr, ast.Constant)
                        and isinstance(attr.value, str)
                        and not attr.value.startswith("_")
                    ):
                        findings.append(f"calls {fn.id}() with a computed or private name")
            elif isinstance(fn, ast.Attribute) and _risky_method(fn):
                findings.append(f"calls .{fn.attr}()")
        elif isinstance(node, ast.Attribute) and node.attr in DUNDER_ATTRS:
            findings.append(f"touches {node.attr}")
        elif isinstance(node, ast.Name) and node.id in DUNDER_ATTRS:
            findings.append(f"uses {node.id}")
    unique = tuple(dict.fromkeys(findings))[:8]
    return PythonRisk(bool(unique), unique)
