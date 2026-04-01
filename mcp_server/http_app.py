"""
http_app.py
-----------
Render / Cloud Run 等平台可用的 HTTP MCP 部署入口。

預設提供：
  - GET /         → 服務資訊
  - GET /health   → 健康檢查
  - POST /mcp     → Streamable HTTP MCP endpoint

啟動方式：
    python -m mcp_server.http_app
"""

from __future__ import annotations

import os

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .server import mcp

_ROUTES_REGISTERED = False


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Optional lightweight auth for shared test deployments."""

    def __init__(self, app, token: str | None):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next):
        if not self.token:
            return await call_next(request)

        if request.url.path in {"/", "/health"}:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        expected = f"Bearer {self.token}"
        if auth != expected:
            return JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


async def home(_: Request):
    return JSONResponse(
        {
            "service": "CTBC Payment Advisor MCP",
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "health": "/health",
        }
    )


async def health(_: Request):
    return PlainTextResponse("ok")


def _register_public_routes():
    global _ROUTES_REGISTERED
    if _ROUTES_REGISTERED:
        return

    mcp.custom_route("/", methods=["GET"], include_in_schema=False)(home)
    mcp.custom_route("/health", methods=["GET"], include_in_schema=False)(health)
    _ROUTES_REGISTERED = True


def create_app():
    """Create the ASGI app used by Render / Cloud Run deployments."""
    _register_public_routes()
    app = mcp.streamable_http_app()
    app.add_middleware(BearerTokenMiddleware, token=os.getenv("MCP_AUTH_TOKEN"))
    return app


app = create_app()


def main():
    """Run the HTTP deployment app locally."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("mcp_server.http_app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
