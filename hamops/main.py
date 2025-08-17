# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import os
from importlib import resources

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP

from .adapters.callsign import lookup_callsign
from .middleware import RequestLogMiddleware

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY")


# ---------------------------------------------------------------------------
# Application Factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title="Hamops")

    # -----------------------------------------------------------------------
    # Middleware
    # -----------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLogMiddleware)

    # -----------------------------------------------------------------------
    # API key dependency
    # -----------------------------------------------------------------------
    api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

    def require_api_key(x_api_key: str | None = Header(default=None)):
        if API_KEY and x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Missing or invalid API key")

    # -----------------------------------------------------------------------
    # Routes
    # -----------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def web_root():
        index = resources.files("hamops").joinpath("web/index.html").read_text()
        return HTMLResponse(index)

    @app.get("/api")
    def api_root():
        return {
            "ok": True,
            "service": "HAM Ops",
            "docs": "/docs",
            "health": "/health",
            "mcp": "/mcp",
        }

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/callsign/{callsign}", operation_id="callsign_lookup")
    async def rest_callsign(callsign: str):
        rec = await lookup_callsign(callsign)
        if not rec:
            raise HTTPException(status_code=404, detail="Callsign not found")
        return JSONResponse({"record": rec.model_dump()})

    # -----------------------------------------------------------------------
    # MCP server mount
    # -----------------------------------------------------------------------
    mcp = FastApiMCP(app, include_operations=["callsign_lookup"])
    mcp.mount()

    return app


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = create_app()
