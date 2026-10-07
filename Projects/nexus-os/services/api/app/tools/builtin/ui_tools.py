"""Tools that act on the user's screen, always via a user gesture."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.risk import RiskLevel
from app.tools.base import Capability, ToolContext, ToolDefinition


class ClipboardWriteArgs(BaseModel):
    text: str = Field(min_length=1, max_length=20_000, description="Text to offer for copying.")
    label: str = Field(default="Copy result", max_length=60)


async def clipboard_write(ctx: ToolContext, a: ClipboardWriteArgs) -> dict[str, Any]:
    await ctx.emit("CLIPBOARD_REQUEST", {"text": a.text, "label": a.label})
    return {
        "offered": True,
        "note": "The user is shown a Copy button. Nothing is copied until they click it.",
    }


TOOLS = [
    ToolDefinition(
        "clipboard_write",
        "Offer the user a 'Copy' button for some text. Nothing is copied without their click. "
        "There is deliberately no way to read the clipboard.",
        ClipboardWriteArgs,
        RiskLevel.MODERATE,
        clipboard_write,
        permissions=frozenset({Capability.UI_CLIPBOARD}),
    ),
]
