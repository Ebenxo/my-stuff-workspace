"""Built-in tool set."""

from __future__ import annotations

from app.tools.base import ToolDefinition
from app.tools.builtin import code_tools, data_tools, docs_tools, fs_tools, git_tools, net_tools, ui_tools


def builtin_tools() -> list[ToolDefinition]:
    return [
        *fs_tools.TOOLS,
        *docs_tools.TOOLS,
        *data_tools.TOOLS,
        *code_tools.TOOLS,
        *git_tools.TOOLS,
        *net_tools.TOOLS,
        *ui_tools.TOOLS,
    ]
