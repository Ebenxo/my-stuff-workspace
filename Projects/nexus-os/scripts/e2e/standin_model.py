"""A stand-in for an OpenAI-compatible model server, used only by the end-to-end test.

It plays a scripted "model" (like the demo, but through the ordinary provider path, so onboarding can
connect to it and an agent can run against it). The scenario is chosen by a tag in the task text and
the step by how many assistant turns the conversation has. Nothing in the app uses this file.

    python scripts/e2e/standin_model.py PORT
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODEL = "e2e-standin"


def step(summary: str, action: dict[str, Any]) -> str:
    return json.dumps({"summary": summary, "action": action})


def call(tool: str, args: dict[str, Any], summary: str) -> str:
    return step(summary, {"type": "tool_call", "tool": tool, "arguments": args})


def finish(summary: str, status: str = "completed") -> str:
    return step("Finishing up", {"type": "finish", "result": {"status": status, "summary": summary}})


SCENARIOS = {
    "tidy": [
        call("list_directory", {"path": "files"}, "Looking at what is in files/"),
        call("delete_file", {"path": "files/old-notes.txt"}, "Removing the outdated notes file"),
        finish("Removed files/old-notes.txt (it is in the project trash)."),
    ],
}


def pick(messages: list[dict[str, Any]]) -> str:
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    for tag, script in SCENARIOS.items():
        if f"[{tag}]" in str(first):
            assistants = sum(1 for m in messages if m.get("role") == "assistant")
            return script[min(assistants, len(script) - 1)]
    return finish("The stand-in model has no script for this task.", "failed")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        return None

    def _json(self, status: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        if not self.path.endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        text = pick(request.get("messages", []))
        self._json(
            200,
            {
                "id": "cmpl-e2e",
                "object": "chat.completion",
                "model": request.get("model", MODEL),
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 400, "completion_tokens": 60, "total_tokens": 460},
            },
        )


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
