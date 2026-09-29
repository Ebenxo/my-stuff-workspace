"""Arguments for MCP tools: a small JSON Schema checker, and the pydantic model that carries it.

MCP servers describe their tools' arguments with JSON Schema. The ToolExecutor validates arguments with
a pydantic model before policy runs, so each MCP tool gets a model whose JSON schema is the server's own
(cleaned) schema and whose validation is this checker. It covers the keywords tools use in practice
(type, properties, required, additionalProperties, items, enum, const, lengths, bounds, anyOf/oneOf/
allOf). Unknown keywords are ignored (the server validates again), and ``pattern`` is deliberately not
evaluated: a regular expression written by a server could be made to run for a very long time.

Error messages name the argument and the rule, never the value.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator
from pydantic_core import PydanticCustomError

MAX_DEPTH = 24
MAX_PROBLEMS = 12
MAX_SCHEMA_CHARS = 40_000
MAX_DESCRIPTION = 600
MAX_FIELD_DESCRIPTION = 240

# Control characters (except tab and newline), zero-width and bidirectional-override characters: they
# hide text from a person reading a description while a model still reads it.
_INVISIBLE = re.compile("[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁠-⁤﻿]")


def clean_text(value: Any, limit: int) -> str:
    """Server-provided text made safe to show and to put in a prompt: visible characters only, spaces
    collapsed, length capped."""
    if not isinstance(value, str):
        return ""
    text = " ".join(_INVISIBLE.sub("", value).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def clean_schema(schema: Any) -> dict[str, Any]:
    """The schema NEXUS keeps for a tool: an object schema with cleaned descriptions and titles.
    Raises ValueError when it is not usable (too large to show a model)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    if len(json.dumps(schema, default=str)) > MAX_SCHEMA_CHARS:
        raise ValueError("its argument schema is too large")
    out = copy.deepcopy(schema)

    def walk(node: Any, depth: int) -> None:
        if depth > MAX_DEPTH:
            return
        if isinstance(node, dict):
            for key in ("description", "title"):
                if key in node and isinstance(node[key], str):
                    node[key] = clean_text(node[key], MAX_FIELD_DESCRIPTION)
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(out, 0)
    out.setdefault("type", "object")
    if out.get("type") != "object":
        raise ValueError("its arguments are not an object")
    out.setdefault("properties", {})
    return out


def _is(value: Any, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer()
        )
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "null":
        return value is None
    return True  # an unknown type name is the server's business


def _within(key: str, value: float, bound: float) -> bool:
    if key == "minimum":
        return value >= bound
    if key == "maximum":
        return value <= bound
    if key == "exclusiveMinimum":
        return value > bound
    return value < bound


def _at(path: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{path or 'arguments'}[{key}]"
    return f"{path}.{key}" if path else key


def check(schema: Any, value: Any, path: str = "", depth: int = 0) -> list[str]:
    """Problems with ``value`` against ``schema`` (empty when it is acceptable)."""
    if schema is False:
        return [f"{path or 'arguments'}: not accepted"]
    if not isinstance(schema, dict) or depth > MAX_DEPTH:
        return []
    where = path or "arguments"
    kind = schema.get("type")
    if kind is not None:
        kinds = [k for k in (kind if isinstance(kind, list) else [kind]) if isinstance(k, str)]
        if kinds and not any(_is(value, k) for k in kinds):
            return [f"{where}: must be {' or '.join(kinds)}"]
    problems: list[str] = []
    if "const" in schema and value != schema["const"]:
        problems.append(f"{where}: must be {json.dumps(schema['const'], default=str)[:60]}")
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        shown = ", ".join(json.dumps(v, default=str)[:40] for v in enum[:12])
        problems.append(f"{where}: must be one of {shown}")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            problems.append(f"{where}: must be at least {schema['minLength']} characters")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            problems.append(f"{where}: must be at most {schema['maxLength']} characters")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        for key, text in (
            ("minimum", "at least"),
            ("maximum", "at most"),
            ("exclusiveMinimum", "more than"),
            ("exclusiveMaximum", "less than"),
        ):
            bound = schema.get(key)
            if (
                isinstance(bound, (int, float))
                and not isinstance(bound, bool)
                and not _within(key, value, bound)
            ):
                problems.append(f"{where}: must be {text} {bound}")
    if isinstance(value, dict):
        raw_props, raw_required = schema.get("properties"), schema.get("required")
        props: dict[str, Any] = raw_props if isinstance(raw_props, dict) else {}
        required: list[Any] = raw_required if isinstance(raw_required, list) else []
        for name in required:
            if isinstance(name, str) and name not in value:
                problems.append(f"{_at(path, name)}: required")
        extra = schema.get("additionalProperties", True)
        for name, item in value.items():
            if name in props:
                problems += check(props[name], item, _at(path, name), depth + 1)
            elif extra is False:
                problems.append(f"{_at(path, name)}: not an accepted argument")
            elif isinstance(extra, dict):
                problems += check(extra, item, _at(path, name), depth + 1)
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(value[:500]):
                problems += check(items, item, _at(path, i), depth + 1)
                if len(problems) >= MAX_PROBLEMS:
                    break
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            problems.append(f"{where}: needs at least {schema['minItems']} items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            problems.append(f"{where}: takes at most {schema['maxItems']} items")
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if isinstance(options, list) and options and all(check(o, value, path, depth + 1) for o in options):
            problems.append(f"{where}: does not match any accepted form")
    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for option in all_of:
            problems += check(option, value, path, depth + 1)
    return problems[:MAX_PROBLEMS]


class MCPArguments(BaseModel):
    """Base for MCP tool arguments. Subclasses carry their server's schema in ``source_schema``."""

    model_config = ConfigDict(extra="allow")
    source_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    @model_validator(mode="before")
    @classmethod
    def _check(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            raise PydanticCustomError("mcp_arguments", "arguments must be an object")
        problems = check(cls.source_schema, data)
        if problems:
            raise PydanticCustomError("mcp_arguments", "; ".join(problems))
        return data

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return copy.deepcopy(cls.source_schema)

    def arguments(self) -> dict[str, Any]:
        """The arguments exactly as given (every key is an 'extra' field on this model)."""
        return dict(self.model_extra or {})


def args_model(tool_name: str, schema: dict[str, Any]) -> type[MCPArguments]:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", tool_name)[:80] or "tool"
    model: type[MCPArguments] = type(f"MCPArgs_{safe}", (MCPArguments,), {"__module__": __name__})
    model.source_schema = schema
    return model
