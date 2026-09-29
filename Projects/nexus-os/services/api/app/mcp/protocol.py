"""MCP protocol constants, errors and result rendering (JSON-RPC 2.0 messages, protocol 2025-06-18).

Everything a server sends is untrusted: text is cleaned and capped before anyone sees it, and binary
content is described rather than passed on.
"""

from __future__ import annotations

import json
from typing import Any

from app.mcp.jsonschema import clean_text

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_RESULT_CHARS = 200_000

# JSON-RPC error codes
METHOD_NOT_FOUND = -32601


class MCPError(Exception):
    """A failure talking to an MCP server. ``message`` is safe to show a person and an agent."""

    def __init__(
        self, message: str, *, code: str = "mcp_error", rpc_code: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.rpc_code = rpc_code
        self.retryable = retryable


def rpc_error_message(error: Any) -> tuple[str, int | None]:
    if not isinstance(error, dict):
        return "The server returned an error.", None
    code = error.get("code") if isinstance(error.get("code"), int) else None
    text = clean_text(error.get("message"), 500) or "The server returned an error."
    return text, code


def _size_note(item: dict[str, Any]) -> str:
    data = item.get("data") or item.get("blob")
    if isinstance(data, str):
        return f", about {max(1, len(data) * 3 // 4 // 1024)} KB"
    return ""


def render_content(items: Any) -> str:
    """Tool or prompt content as text. Images, audio and binary resources are described, not included."""
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "text" and isinstance(item.get("text"), str):
            parts.append(item["text"])
        elif kind in ("image", "audio"):
            mime = clean_text(item.get("mimeType"), 80) or "unknown type"
            parts.append(f"[{kind}: {mime}{_size_note(item)}; not shown]")
        elif kind == "resource" and isinstance(item.get("resource"), dict):
            res = item["resource"]
            uri = clean_text(res.get("uri"), 300)
            if isinstance(res.get("text"), str):
                parts.append(f"[resource {uri}]\n{res['text']}")
            else:
                parts.append(f"[binary resource {uri}{_size_note(res)}; not shown]")
        elif kind == "resource_link":
            name = clean_text(item.get("name"), 120)
            parts.append(f"[link: {name} {clean_text(item.get('uri'), 300)}]".replace("  ", " "))
        else:
            parts.append("[content of a type NEXUS does not show]")
    text = "\n\n".join(p for p in parts if p)
    return text[:MAX_RESULT_CHARS]


def render_tool_result(result: dict[str, Any]) -> tuple[str, bool]:
    """(text for the agent, whether the tool reported an error)."""
    text = render_content(result.get("content"))
    structured = result.get("structuredContent")
    if not text and structured is not None:
        text = json.dumps(structured, ensure_ascii=False, default=str)[:MAX_RESULT_CHARS]
    return text, bool(result.get("isError"))


def render_resource(result: dict[str, Any], *, limit: int = 100_000) -> list[dict[str, Any]]:
    """``resources/read`` contents for the UI: text (capped) or a note about binary data."""
    out: list[dict[str, Any]] = []
    contents = result.get("contents")
    for item in contents if isinstance(contents, list) else []:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "uri": clean_text(item.get("uri"), 500),
            "mime_type": clean_text(item.get("mimeType"), 120) or None,
        }
        if isinstance(item.get("text"), str):
            text = item["text"]
            entry["text"] = text[:limit]
            entry["truncated"] = len(text) > limit
        else:
            entry["text"] = None
            entry["note"] = f"Binary content{_size_note(item)}; not shown."
        out.append(entry)
    return out


def render_prompt(result: dict[str, Any]) -> list[dict[str, str]]:
    """``prompts/get`` messages for the UI (role and text)."""
    out: list[dict[str, str]] = []
    messages = result.get("messages")
    for m in messages if isinstance(messages, list) else []:
        if not isinstance(m, dict):
            continue
        role = m.get("role") if m.get("role") in ("user", "assistant") else "user"
        content = m.get("content")
        text = render_content([content] if isinstance(content, dict) else content)
        out.append({"role": str(role), "text": text[:20_000]})
    return out
