"""Main application module for Hamops.

This module defines the FastAPI application, registers middleware,
defines REST endpoints, and mounts an MCP server for Model Context
Protocol operations.  At startup, it constructs the FastAPI app via
``create_app`` and exposes it as a module-level variable named ``app``
so that ASGI servers like Uvicorn can discover it automatically.
"""

from __future__ import annotations

import os
from importlib import resources
from typing import List

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP

from .adapters.callsign import lookup_callsign
from .adapters.aprs import (
    get_aprs_location,
    get_aprs_weather,
)
from .middleware import RequestLogMiddleware


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("API_KEY")


def create_app() -> FastAPI:
    """Factory function for constructing the FastAPI application.

    The returned application includes CORS middleware, request logging,
    optional API key authentication, and a set of REST endpoints for
    callsign lookups and APRS queries.  The MCP server is automatically
    mounted with the operation identifiers defined on the route
    decorators.
    """
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
        """Serve the simple single–page web interface.

        The HTML file is loaded from the ``hamops/web`` package data using
        ``importlib.resources``.
        """
        index = resources.files("hamops").joinpath("web/index.html").read_text()
        return HTMLResponse(index)

    @app.get("/api")
    def api_root():
        """Return a simple service descriptor for programmatic clients."""
        return {
            "ok": True,
            "service": "HAM Ops",
            "docs": "/docs",
            "health": "/health",
            "mcp": "/mcp",
        }

    @app.get("/health")
    def health():
        """Health check endpoint."""
        return {"ok": True}

    @app.get("/api/callsign/{callsign}", operation_id="callsign_lookup")
    async def rest_callsign(callsign: str):
        """Look up a callsign via the HamDB service.

        Returns a JSON representation of the normalized callsign record or
        raises a 404 error if the callsign is not found.
        """
        rec = await lookup_callsign(callsign)
        if not rec:
            raise HTTPException(status_code=404, detail="Callsign not found")
        return JSONResponse({"record": rec.model_dump()})

    @app.get("/api/aprs/location/{callsign}", operation_id="aprs_location")
    async def rest_aprs_location(callsign: str):
        """Fetch the most recent APRS location for a callsign.

        This endpoint queries the aprs.fi API (if configured) for the latest
        position report associated with ``callsign``.  When successful it
        returns a JSON object with a ``record`` field containing a
        serialized :class:`~hamops.models.aprs.APRSLocationRecord`.
        If no entry is found, a 404 error is returned.
        """
        record = await get_aprs_location(callsign)
        if not record:
            raise HTTPException(status_code=404, detail="APRS station not found")
        return JSONResponse({"record": record.model_dump()})

    @app.get("/api/aprs/weather/{callsign}", operation_id="aprs_weather")
    async def rest_aprs_weather(callsign: str):
        """Retrieve the latest weather report for an APRS weather station.

        Queries the aprs.fi API for weather data associated with the given
        callsign.  If a weather entry exists, returns it under a ``record``
        key; otherwise raises a 404 error.
        """
        record = await get_aprs_weather(callsign)
        if not record:
            raise HTTPException(status_code=404, detail="APRS weather station not found")
        return JSONResponse({"record": record.model_dump()})

    # -----------------------------------------------------------------------
    # MCP server mount
    # -----------------------------------------------------------------------
    # Include all operation identifiers so they are exposed over the MCP server
    mcp = FastApiMCP(
        app,
        include_operations=["callsign_lookup", "aprs_location", "aprs_track", "aprs_weather"],
    )
    mcp.mount()

    return app


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = create_app()
