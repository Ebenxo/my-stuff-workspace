"""Web search backends. None is bundled: the user configures SearXNG (self-hosted) or Brave."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote, urlsplit

from app.tools.netguard import NetError, SafeHttpClient

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class SearchNotConfigured(Exception):
    pass


class SearchService:
    def __init__(
        self,
        http: SafeHttpClient,
        get_config: Callable[[], Awaitable[dict[str, Any]]],
        get_secret: Callable[[str], Awaitable[str | None]],
    ) -> None:
        self._http = http
        self._config = get_config
        self._secret = get_secret

    async def backend_name(self) -> str | None:
        cfg = await self._config()
        return {"searxng": "SearXNG", "brave": "Brave Search"}.get(cfg.get("kind", ""))

    async def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        import json

        cfg = await self._config()
        kind = cfg.get("kind")
        if kind == "searxng":
            base = str(cfg.get("base_url") or "").rstrip("/")
            if not base:
                raise SearchNotConfigured("SearXNG needs a base URL.")
            parts = urlsplit(base)
            exempt = [f"{parts.hostname}:{parts.port or (443 if parts.scheme == 'https' else 80)}"]
            res = await self._http.request(
                "GET",
                f"{base}/search?q={quote(query)}&format=json",
                allow_private=exempt,
                max_bytes=500_000,
                as_text=False,
            )
            items = json.loads(res.text).get("results", [])
            return [
                {
                    "title": str(i.get("title", ""))[:200],
                    "url": str(i.get("url", "")),
                    "snippet": str(i.get("content", ""))[:400],
                }
                for i in items[:limit]
            ]
        if kind == "brave":
            key = await self._secret(str(cfg.get("secret_ref") or "search:brave"))
            if not key:
                raise SearchNotConfigured("Brave Search needs an API key.")
            res = await self._http.request(
                "GET",
                f"{BRAVE_URL}?q={quote(query)}&count={limit}",
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
                max_bytes=500_000,
                as_text=False,
            )
            items = json.loads(res.text).get("web", {}).get("results", [])
            return [
                {
                    "title": str(i.get("title", ""))[:200],
                    "url": str(i.get("url", "")),
                    "snippet": str(i.get("description", ""))[:400],
                }
                for i in items[:limit]
            ]
        raise SearchNotConfigured("No web search backend is configured.")


__all__ = ["NetError", "SearchNotConfigured", "SearchService"]
