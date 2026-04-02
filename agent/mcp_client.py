"""
mcp_client.py
-------------
遠端 HTTP MCP client 封裝。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@dataclass
class MCPTraceEvent:
    tool_name: str
    arguments: dict[str, Any]
    status: str
    summary: str


class MCPHttpClient:
    """Simple synchronous wrapper around Streamable HTTP MCP client."""

    def __init__(
        self,
        server_url: str,
        auth_token: str | None = None,
        trace_logger: Callable[[MCPTraceEvent], None] | None = None,
    ):
        self.server_url = server_url
        self.auth_token = auth_token
        self.trace_logger = trace_logger

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call_tool_async(tool_name, arguments))

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        self._trace(tool_name, arguments, "calling", "request started")

        try:
            async with httpx.AsyncClient(headers=headers, timeout=30.0) as http_client:
                async with streamable_http_client(self.server_url, http_client=http_client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments)
        except Exception as exc:
            self._trace(tool_name, arguments, "error", self._format_exception(exc))
            raise

        payload = self._decode_tool_result(result)
        if payload.get("error"):
            self._trace(tool_name, arguments, "error", str(payload["error"]))
        else:
            self._trace(tool_name, arguments, "success", self._summarize(payload))
        return payload

    def _decode_tool_result(self, result) -> dict[str, Any]:
        if not getattr(result, "content", None):
            return {"error": "工具未回傳內容"}

        first = result.content[0]
        text = getattr(first, "text", "")
        if not text:
            return {"error": "工具回傳內容不可解析"}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}

    def _summarize(self, payload: dict[str, Any]) -> str:
        if "results" in payload and isinstance(payload["results"], list):
            count = len(payload["results"])
            best = payload["results"][0]["card_name"] if count else "none"
            return f"{count} results, best={best}"
        if "recommendations" in payload and isinstance(payload["recommendations"], list):
            return f"{len(payload['recommendations'])} recommendations"
        if "comparison" in payload and isinstance(payload["comparison"], list):
            return f"{len(payload['comparison'])} channel comparisons"
        if "promotions" in payload and isinstance(payload["promotions"], list):
            return f"{len(payload['promotions'])} promotions"
        if "card_name" in payload:
            return f"card={payload['card_name']}"
        if "cards" in payload and isinstance(payload["cards"], list):
            return f"{len(payload['cards'])} cards"
        return "ok"

    def _trace(self, tool_name: str, arguments: dict[str, Any], status: str, summary: str):
        if self.trace_logger:
            self.trace_logger(
                MCPTraceEvent(
                    tool_name=tool_name,
                    arguments=arguments,
                    status=status,
                    summary=summary,
                )
            )

    def _format_exception(self, exc: Exception) -> str:
        if isinstance(exc, BaseExceptionGroup):
            leaves = self._flatten_exception_group(exc)
            if leaves:
                return " | ".join(leaves)
        return f"{type(exc).__name__}: {exc}"

    def _flatten_exception_group(self, exc: BaseExceptionGroup) -> list[str]:
        messages: list[str] = []
        for sub_exc in exc.exceptions:
            if isinstance(sub_exc, BaseExceptionGroup):
                messages.extend(self._flatten_exception_group(sub_exc))
            else:
                messages.append(f"{type(sub_exc).__name__}: {sub_exc}")
        return messages
