"""Main application module for Hamops.

This module defines the FastAPI application, registers middleware,
defines REST endpoints, and mounts an MCP server for Model Context
Protocol operations.  At startup, it constructs the FastAPI app via
``create_app`` and exposes it as a module-level variable named ``app``
so that ASGI servers like Uvicorn can discover it automatically.
"""

import os
from contextlib import asynccontextmanager
from importlib import resources
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .adapters.callsign import lookup_callsign
from .adapters.aprs import (
    get_aprs_locations,
    get_aprs_weather,
    get_aprs_messages,
)
from .adapters.bandplan import get_bandplan_adapter
from .middleware import RequestLogMiddleware
from .models import (
    APRSLocationRecord,
    APRSMessageRecord,
    APRSWeatherRecord,
    BandPlanSummary,
    BandSearchResult,
    BandSegment,
    CallsignRecord,
    FrequencyInfo,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# Placeholder instructions describing the MCP server. Fill in version, contact
# information, and any other global details relevant to clients.
MCP_SERVER_INSTRUCTIONS = (
    "TODO: add server version, contact information, capability flags, and other "
    "high-level guidance for MCP clients."
)


# ---------------------------------------------------------------------------
# MCP tool I/O models
# ---------------------------------------------------------------------------


class CallsignLookupOutput(BaseModel):
    """Structured result for callsign lookups."""

    record: CallsignRecord = Field(..., description="Normalized callsign data")


class APRSLocationsOutput(BaseModel):
    """Structured result for APRS location history."""

    records: list[APRSLocationRecord] = Field(
        ..., description="APRS location packets for the callsign"
    )


class APRSWeatherOutput(BaseModel):
    """Structured result for APRS weather queries."""

    record: APRSWeatherRecord = Field(
        ..., description="Latest weather report for the station"
    )


class APRSMessagesOutput(BaseModel):
    """Structured result for APRS message queries."""

    records: list[APRSMessageRecord] = Field(
        ..., description="APRS text messages to or from the callsign"
    )


class BandAtFrequencyOutput(BaseModel):
    """Band information at a specific frequency."""

    record: FrequencyInfo


class SearchBandsOutput(BaseModel):
    """Result of searching band segments."""

    record: BandSearchResult


class FrequencyRange(BaseModel):
    """Frequency range used for band lookups."""

    start: int
    end: int
    startMHz: float
    endMHz: float


class BandsInRangeOutput(BaseModel):
    """Band segments within a frequency span."""

    range: FrequencyRange
    count: int
    bands: list[BandSegment]


class BandPlanSummaryOutput(BaseModel):
    """Summary information about the loaded band plan."""

    record: BandPlanSummary


def create_app() -> FastAPI:
    """Factory function for constructing the FastAPI application.

    The returned application includes CORS middleware, request logging,
    optional API key authentication, and a set of REST endpoints for
    callsign lookups and APRS queries.  The MCP server is automatically
    mounted with the operation identifiers defined on the route
    decorators.
    """
    mcp = FastMCP(
        name="Hamops",
        instructions=MCP_SERVER_INSTRUCTIONS,
        streamable_http_path="/",
    )
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Hamops", lifespan=lifespan)

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

    async def callsign_lookup_tool(
        callsign: str,
        ctx: Context = None,
    ) -> CallsignLookupOutput:
        """Look up a callsign via the HamDB service.

        TODO: document rate limits, input examples, and expected error codes.
        """
        rec = await lookup_callsign(callsign)
        if not rec:
            raise ValueError("Callsign not found")
        return CallsignLookupOutput(record=rec)

    @app.get(
        "/api/callsign/{callsign}",
        operation_id="callsign_lookup",
        tags=["HamDB"],
    )
    async def rest_callsign(callsign: str) -> JSONResponse:
        try:
            return JSONResponse((await callsign_lookup_tool(callsign)).model_dump())
        except ValueError:
            raise HTTPException(status_code=404, detail="Callsign not found")

    mcp.add_tool(
        callsign_lookup_tool,
        name="callsign_lookup",
        title="Callsign Lookup",
        description=(
            "Retrieve normalized callsign details. TODO: add sample payloads and "
            "rate-limit information."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )

    async def aprs_locations_tool(
        callsign: str,
        ctx: Context = None,
    ) -> APRSLocationsOutput:
        """Fetch all APRS location records for a callsign (base or extended).

        TODO: document units, data retention, and sample payloads.
        """
        records = await get_aprs_locations(callsign)
        if not records:
            raise ValueError("APRS station not found")
        return APRSLocationsOutput(records=records)

    @app.get(
        "/api/aprs/locations/{callsign}",
        operation_id="aprs_locations",
        tags=["APRS"],
    )
    async def rest_aprs_locations(callsign: str) -> JSONResponse:
        try:
            return JSONResponse((await aprs_locations_tool(callsign)).model_dump())
        except ValueError:
            raise HTTPException(status_code=404, detail="APRS station not found")

    mcp.add_tool(
        aprs_locations_tool,
        name="aprs_locations",
        title="APRS Location History",
        description=(
            "Fetch recent APRS position packets for a callsign. TODO: document "
            "units and retention period."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )

    async def aprs_weather_tool(
        callsign: str,
        ctx: Context = None,
    ) -> APRSWeatherOutput:
        """Retrieve the latest weather report for an APRS weather station.

        TODO: include units of measure, rate limits, and example payloads.
        """
        record = await get_aprs_weather(callsign)
        if not record:
            raise ValueError("APRS weather station not found")
        return APRSWeatherOutput(record=record)

    @app.get(
        "/api/aprs/weather/{callsign}",
        operation_id="aprs_weather",
        tags=["APRS"],
    )
    async def rest_aprs_weather(callsign: str) -> JSONResponse:
        try:
            return JSONResponse((await aprs_weather_tool(callsign)).model_dump())
        except ValueError:
            raise HTTPException(
                status_code=404, detail="APRS weather station not found"
            )

    mcp.add_tool(
        aprs_weather_tool,
        name="aprs_weather",
        title="APRS Weather",
        description=(
            "Get the latest APRS weather report for a station. TODO: document "
            "units of measure and expected update frequency."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )

    async def aprs_messages_tool(
        callsign: str,
        ctx: Context = None,
    ) -> APRSMessagesOutput:
        """Fetch APRS text messages for a callsign (sent to or from).

        TODO: specify retention policies and sample message formats.
        """
        records = await get_aprs_messages(callsign)
        if not records:
            raise ValueError("No APRS messages found")
        return APRSMessagesOutput(records=records)

    @app.get(
        "/api/aprs/messages/{callsign}",
        operation_id="aprs_messages",
        tags=["APRS"],
    )
    async def rest_aprs_messages(callsign: str) -> JSONResponse:
        try:
            return JSONResponse((await aprs_messages_tool(callsign)).model_dump())
        except ValueError:
            raise HTTPException(status_code=404, detail="No APRS messages found")

    mcp.add_tool(
        aprs_messages_tool,
        name="aprs_messages",
        title="APRS Messages",
        description=(
            "Fetch APRS text messages to or from a callsign. TODO: include "
            "retention limits and example outputs."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )

    # -----------------------------------------------------------------------
    # Band Plan Routes
    # -----------------------------------------------------------------------
    async def band_at_frequency_tool(
        frequency: str,
        ctx: Context = None,
    ) -> BandAtFrequencyOutput:
        """Get band information for a specific frequency.

        TODO: specify accepted units and provide example usage.
        """
        adapter = get_bandplan_adapter()
        freq_hz = adapter.parse_frequency(frequency)
        if freq_hz is None:
            raise ValueError(f"Invalid frequency format: {frequency}")
        info = adapter.get_frequency_info(freq_hz)
        return BandAtFrequencyOutput(record=info)

    @app.get(
        "/api/bands/frequency/{frequency}",
        operation_id="band_at_frequency",
        tags=["Band Plan"],
    )
    async def rest_band_at_frequency(frequency: str) -> JSONResponse:
        try:
            return JSONResponse((await band_at_frequency_tool(frequency)).model_dump())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    mcp.add_tool(
        band_at_frequency_tool,
        name="band_at_frequency",
        title="Band at Frequency",
        description=(
            "Provide band information for a specific frequency. TODO: include "
            "units and example requests."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )

    async def search_bands_tool(
        mode: Optional[str] = None,
        band_name: Optional[str] = None,
        license_class: Optional[str] = None,
        typical_use: Optional[str] = None,
        min_frequency: Optional[str] = None,
        max_frequency: Optional[str] = None,
        ctx: Context = None,
    ) -> SearchBandsOutput:
        """Search for band segments matching specified criteria.

        TODO: document allowable filters, units, and sample queries.
        """
        adapter = get_bandplan_adapter()
        min_freq_hz = None
        max_freq_hz = None
        if min_frequency:
            min_freq_hz = adapter.parse_frequency(min_frequency)
            if min_freq_hz is None:
                raise ValueError(f"Invalid minimum frequency format: {min_frequency}")
        if max_frequency:
            max_freq_hz = adapter.parse_frequency(max_frequency)
            if max_freq_hz is None:
                raise ValueError(f"Invalid maximum frequency format: {max_frequency}")
        result = adapter.search_bands(
            mode=mode,
            band_name=band_name,
            license_class=license_class,
            typical_use=typical_use,
            min_freq=min_freq_hz,
            max_freq=max_freq_hz,
        )
        return SearchBandsOutput(record=result)

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
        try:
            return JSONResponse(
                (
                    await search_bands_tool(
                        mode=mode,
                        band_name=band_name,
                        license_class=license_class,
                        typical_use=typical_use,
                        min_frequency=min_frequency,
                        max_frequency=max_frequency,
                    )
                ).model_dump()
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    mcp.add_tool(
        search_bands_tool,
        name="search_bands",
        title="Search Bands",
        description=(
            "Search band segments matching provided filters. TODO: detail "
            "available criteria and example requests."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )

    async def bands_in_range_tool(
        start_frequency: str,
        end_frequency: str,
        ctx: Context = None,
    ) -> BandsInRangeOutput:
        """Get all band segments within a frequency range.

        TODO: specify units and provide example requests.
        """
        adapter = get_bandplan_adapter()
        start_hz = adapter.parse_frequency(start_frequency)
        if start_hz is None:
            raise ValueError(f"Invalid start frequency format: {start_frequency}")
        end_hz = adapter.parse_frequency(end_frequency)
        if end_hz is None:
            raise ValueError(f"Invalid end frequency format: {end_frequency}")
        if start_hz > end_hz:
            raise ValueError("Start frequency must be less than end frequency")
        bands = adapter.get_bands_in_range(start_hz, end_hz)
        return BandsInRangeOutput(
            range=FrequencyRange(
                start=start_hz,
                end=end_hz,
                startMHz=start_hz / 1_000_000,
                endMHz=end_hz / 1_000_000,
            ),
            count=len(bands),
            bands=bands,
        )

    @app.get(
        "/api/bands/range/{start_frequency}/{end_frequency}",
        operation_id="bands_in_range",
        tags=["Band Plan"],
    )
    async def rest_bands_in_range(
        start_frequency: str,
        end_frequency: str,
    ) -> JSONResponse:
        try:
            return JSONResponse(
                (
                    await bands_in_range_tool(start_frequency, end_frequency)
                ).model_dump()
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    mcp.add_tool(
        bands_in_range_tool,
        name="bands_in_range",
        title="Bands in Range",
        description=(
            "List band segments within a frequency span. TODO: clarify units "
            "and provide sample outputs."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )

    async def band_plan_summary_tool(
        ctx: Context = None,
    ) -> BandPlanSummaryOutput:
        """Get summary information about the loaded band plan.

        TODO: include data source, version, and refresh cadence.
        """
        adapter = get_bandplan_adapter()
        summary = adapter.get_summary()
        if not summary:
            raise ValueError("Band plan data not loaded. Run scripts/gen_bandplan.py")
        return BandPlanSummaryOutput(record=summary)

    @app.get(
        "/api/bands/summary",
        operation_id="band_plan_summary",
        tags=["Band Plan"],
    )
    async def rest_band_plan_summary() -> JSONResponse:
        try:
            return JSONResponse((await band_plan_summary_tool()).model_dump())
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))

    mcp.add_tool(
        band_plan_summary_tool,
        name="band_plan_summary",
        title="Band Plan Summary",
        description=(
            "Summarize metadata for the loaded band plan. TODO: note data "
            "provenance and version information."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False),
    )

    # -----------------------------------------------------------------------
    # MCP server mount
    # -----------------------------------------------------------------------
    app.mount("/mcp", mcp_app)

    return app


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = create_app()
