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
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from fastapi_mcp import FastApiMCP
from fastapi.staticfiles import StaticFiles


from .adapters.callsign import lookup_callsign
from .adapters.aprs import (
    get_aprs_locations,
    get_aprs_weather,
    get_aprs_messages,
)
from .adapters.bandplan import get_bandplan_adapter
from .middleware import RequestLogMiddleware


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def create_app() -> FastAPI:
    """Factory function for constructing the FastAPI application.

    The returned application includes CORS middleware, request logging,
    optional API key authentication, and a set of REST endpoints for
    callsign lookups and APRS queries.  The MCP server is automatically
    mounted with the operation identifiers defined on the route
    decorators.
    """
    app = FastAPI(title="Hamops")

    app.mount("/web", StaticFiles(directory="hamops/web"), name="web")
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

    def require_api_key(x_api_key: str = Depends(api_key_header)) -> None:
        """Validate the ``x-api-key`` header against ``OPENAI_API_KEY``."""
        if OPENAI_API_KEY and x_api_key != OPENAI_API_KEY:
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

    @app.get(
        "/api/callsign/{callsign}",
        operation_id="callsign_lookup",
        tags=["HamDB"],
    )
    async def rest_callsign(callsign: str) -> JSONResponse:
        """Look up a callsign via the HamDB service.

        Returns a JSON representation of the normalized callsign record or
        raises a 404 error if the callsign is not found.
        """
        rec = await lookup_callsign(callsign)
        if not rec:
            raise HTTPException(status_code=404, detail="Callsign not found")
        return JSONResponse({"record": rec.model_dump()})

    @app.get(
        "/api/aprs/locations/{callsign}",
        operation_id="aprs_locations",
        tags=["APRS"],
    )
    async def rest_aprs_locations(callsign: str) -> JSONResponse:
        """Fetch all APRS location records for a callsign (base or extended).

        Returns a JSON object with a 'records' field containing a list of
        serialized APRSLocationRecord objects. If no entries are found, returns 404.
        """
        records = await get_aprs_locations(callsign)
        if not records:
            raise HTTPException(status_code=404, detail="APRS station not found")
        return JSONResponse({"records": [rec.model_dump() for rec in records]})

    @app.get(
        "/api/aprs/weather/{callsign}",
        operation_id="aprs_weather",
        tags=["APRS"],
    )
    async def rest_aprs_weather(callsign: str) -> JSONResponse:
        """Retrieve the latest weather report for an APRS weather station.

        Queries the aprs.fi API for weather data associated with the given
        callsign.  If a weather entry exists, returns it under a ``record``
        key; otherwise raises a 404 error.
        """
        record = await get_aprs_weather(callsign)
        if not record:
            raise HTTPException(
                status_code=404, detail="APRS weather station not found"
            )
        return JSONResponse({"record": record.model_dump()})

    @app.get(
        "/api/aprs/messages/{callsign}",
        operation_id="aprs_messages",
        tags=["APRS"],
    )
    async def rest_aprs_messages(callsign: str) -> JSONResponse:
        """Fetch APRS text messages for a callsign (sent to or from).

        Returns a JSON object with a 'records' field containing a list of
        serialized APRSMessageRecord objects. If no entries are found, returns 404.
        """
        records = await get_aprs_messages(callsign)
        if not records:
            raise HTTPException(status_code=404, detail="No APRS messages found")
        return JSONResponse({"records": [rec.model_dump() for rec in records]})

    # -----------------------------------------------------------------------
    # Band Plan Routes
    # -----------------------------------------------------------------------
    @app.get(
        "/api/bands/frequency/{frequency}",
        operation_id="band_at_frequency",
        tags=["Band Plan"],
    )
    async def rest_band_at_frequency(frequency: str) -> JSONResponse:
        """Get band information for a specific frequency.

        The frequency parameter can be in various formats:
        - "14.225 MHz" or "14.225MHz"
        - "14225 kHz" or "14225kHz"
        - "14225000 Hz" or "14225000"
        - "14.225" (assumes MHz if has decimal)

        Returns information about what bands, modes, and privileges
        are available at the specified frequency.
        """
        adapter = get_bandplan_adapter()
        freq_hz = adapter.parse_frequency(frequency)
        
        if freq_hz is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid frequency format: {frequency}"
            )
        
        info = adapter.get_frequency_info(freq_hz)
        return JSONResponse({"record": info.model_dump()})

    @app.get(
        "/api/bands/search",
        operation_id="search_bands",
        tags=["Band Plan"],
    )
    async def rest_search_bands(
        mode: Optional[str] = Query(None, description="Filter by mode (e.g., CW, USB, FM)"),
        band_name: Optional[str] = Query(None, description="Filter by band name (e.g., 20m, 2m, 70cm)"),
        license_class: Optional[str] = Query(None, description="Filter by license class (e.g., General, Extra)"),
        typical_use: Optional[str] = Query(None, description="Filter by typical use (e.g., Phone, Digital, Satellite)"),
        min_frequency: Optional[str] = Query(None, description="Minimum frequency (with units)"),
        max_frequency: Optional[str] = Query(None, description="Maximum frequency (with units)"),
    ) -> JSONResponse:
        """Search for band segments matching specified criteria.

        All parameters are optional. Frequencies can be specified with units
        (e.g., "14 MHz", "144.200 MHz", "146520 kHz").

        Returns a list of band segments matching the search criteria.
        """
        adapter = get_bandplan_adapter()
        
        # Parse frequency bounds if provided
        min_freq_hz = None
        max_freq_hz = None
        
        if min_frequency:
            min_freq_hz = adapter.parse_frequency(min_frequency)
            if min_freq_hz is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid minimum frequency format: {min_frequency}"
                )
        
        if max_frequency:
            max_freq_hz = adapter.parse_frequency(max_frequency)
            if max_freq_hz is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid maximum frequency format: {max_frequency}"
                )
        
        result = adapter.search_bands(
            mode=mode,
            band_name=band_name,
            license_class=license_class,
            typical_use=typical_use,
            min_freq=min_freq_hz,
            max_freq=max_freq_hz,
        )
        
        return JSONResponse({"record": result.model_dump()})

    @app.get(
        "/api/bands/range/{start_frequency}/{end_frequency}",
        operation_id="bands_in_range",
        tags=["Band Plan"],
    )
    async def rest_bands_in_range(
        start_frequency: str,
        end_frequency: str,
    ) -> JSONResponse:
        """Get all band segments within a frequency range.

        Frequencies can be specified with units (e.g., "14 MHz", "14.350 MHz").

        Returns all band segments that overlap with the specified range.
        """
        adapter = get_bandplan_adapter()
        
        start_hz = adapter.parse_frequency(start_frequency)
        if start_hz is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid start frequency format: {start_frequency}"
            )
        
        end_hz = adapter.parse_frequency(end_frequency)
        if end_hz is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid end frequency format: {end_frequency}"
            )
        
        if start_hz > end_hz:
            raise HTTPException(
                status_code=400,
                detail="Start frequency must be less than end frequency"
            )
        
        bands = adapter.get_bands_in_range(start_hz, end_hz)
        return JSONResponse({
            "range": {
                "start": start_hz,
                "end": end_hz,
                "startMHz": start_hz / 1_000_000,
                "endMHz": end_hz / 1_000_000,
            },
            "count": len(bands),
            "bands": [band.model_dump() for band in bands],
        })

    @app.get(
        "/api/bands/summary",
        operation_id="band_plan_summary",
        tags=["Band Plan"],
    )
    async def rest_band_plan_summary() -> JSONResponse:
        """Get summary information about the loaded band plan.

        Returns metadata about the band plan including version, source,
        available bands, modes, and frequency coverage.
        """
        adapter = get_bandplan_adapter()
        summary = adapter.get_summary()
        
        if not summary:
            raise HTTPException(
                status_code=503,
                detail="Band plan data not loaded. Run scripts/gen_bandplan.py"
            )
        
        return JSONResponse({"record": summary.model_dump()})

    # -----------------------------------------------------------------------
    # MCP server mount
    # -----------------------------------------------------------------------
    # Include all operation identifiers so they are exposed over the MCP server
    mcp = FastApiMCP(
        app,
        include_operations=[
            "callsign_lookup",
            "aprs_locations",
            "aprs_weather",
            "aprs_messages",
            "band_at_frequency",
            "search_bands",
            "bands_in_range",
            "band_plan_summary",
        ],
    )
    mcp.mount()

    return app


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = create_app()
