"""Main application module for Hamops.

This module defines the FastAPI application, registers middleware,
defines REST endpoints, and mounts an MCP server for Model Context
Protocol operations.  At startup, it constructs the FastAPI app via
``create_app`` and exposes it as a module-level variable named ``app``
so that ASGI servers like Uvicorn can discover it automatically.
"""

from __future__ import annotations

import os
from datetime import datetime
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
from .adapters.propagation import get_propagation_adapter
from .middleware import RequestLogMiddleware


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def create_app() -> FastAPI:
    """Factory function for constructing the FastAPI application.

    The returned application includes CORS middleware, request logging,
    optional API key authentication, and a set of REST endpoints for
    callsign lookups, APRS queries, band plan, and propagation services.
    The MCP server is automatically mounted with the operation identifiers
    defined on the route decorators.
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
    # Propagation Routes
    # -----------------------------------------------------------------------
    @app.get(
        "/api/propagation/conditions",
        operation_id="propagation_conditions",
        tags=["Propagation"],
    )
    async def rest_propagation_conditions(
        location: Optional[str] = Query(None, description="Location for MUF data (optional)")
    ) -> JSONResponse:
        """Get current solar-terrestrial conditions and band propagation status.

        Returns the latest solar flux, sunspot number, K-index, A-index,
        solar wind speed, geomagnetic field status, and qualitative band
        conditions (Good/Fair/Poor) for different bands during day/night.

        If a location is provided, also includes MUF (Maximum Usable Frequency)
        data for that location.
        """
        adapter = get_propagation_adapter()
        conditions = await adapter.fetch_current_conditions(location)
        
        if not conditions:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch current propagation conditions"
            )
        
        return JSONResponse({"record": conditions.model_dump()})

    @app.get(
        "/api/propagation/forecast",
        operation_id="propagation_forecast",
        tags=["Propagation"],
    )
    async def rest_propagation_forecast(
        days: int = Query(27, ge=1, le=27, description="Number of days to forecast (1-27)"),
        date: Optional[str] = Query(None, description="Specific date to get forecast for (ISO format)")
    ) -> JSONResponse:
        """Get short-term propagation forecast from NOAA.

        Returns predicted solar flux, A-index, and K-index for the next N days
        (up to 27 days). Each day includes a qualitative assessment of expected
        propagation conditions.

        If a specific date is provided, returns only the forecast for that date.
        """
        adapter = get_propagation_adapter()
        forecasts = await adapter.fetch_forecast(days)
        
        if not forecasts:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch propagation forecast"
            )
        
        # Filter by specific date if requested
        if date:
            date_forecast = [f for f in forecasts if f.date == date]
            if not date_forecast:
                raise HTTPException(
                    status_code=404,
                    detail=f"No forecast available for date: {date}"
                )
            return JSONResponse({"record": date_forecast[0].model_dump()})
        
        return JSONResponse({
            "count": len(forecasts),
            "forecasts": [f.model_dump() for f in forecasts]
        })

    @app.get(
        "/api/propagation/analysis",
        operation_id="propagation_analysis",
        tags=["Propagation"],
    )
    async def rest_propagation_analysis(
        season: Optional[str] = Query(None, description="Season: 'summer' or 'winter'"),
        band: Optional[str] = Query(None, description="Amateur band (e.g., '20m', '40m', '80m')"),
        solar_cycle: Optional[str] = Query(None, description="Solar cycle phase: 'minimum', 'rising', 'maximum', 'declining'"),
        year: Optional[int] = Query(None, ge=2000, le=2050, description="Specific year for analysis"),
    ) -> JSONResponse:
        """Analyze propagation characteristics for specific conditions.

        Provides detailed propagation analysis based on season, band, solar cycle
        phase, and/or year. Returns expected daytime and nighttime propagation
        characteristics, maximum distances, and operating recommendations.

        All parameters are optional. The more specific the query, the more
        detailed the analysis.
        """
        adapter = get_propagation_adapter()
        
        # Validate inputs
        if season and season not in ["summer", "winter"]:
            raise HTTPException(
                status_code=400,
                detail="Season must be 'summer' or 'winter'"
            )
        
        if solar_cycle and solar_cycle not in ["minimum", "rising", "maximum", "declining"]:
            raise HTTPException(
                status_code=400,
                detail="Solar cycle must be one of: minimum, rising, maximum, declining"
            )
        
        analysis = adapter.analyze_propagation(
            season=season,
            band=band,
            solar_cycle=solar_cycle,
            year=year,
        )
        
        return JSONResponse({"record": analysis.model_dump()})

    @app.get(
        "/api/propagation/muf",
        operation_id="propagation_muf",
        tags=["Propagation"],
    )
    async def rest_propagation_muf(
        location: str = Query(..., description="Location or station code for MUF data"),
        lat: Optional[float] = Query(None, ge=-90, le=90, description="Latitude"),
        lon: Optional[float] = Query(None, ge=-180, le=180, description="Longitude"),
    ) -> JSONResponse:
        """Get Maximum Usable Frequency (MUF) data for a location.

        Returns the current MUF for 3000km path and critical frequency (foF2)
        for the specified location. Data is obtained from the nearest ionosonde
        station.

        Provide either a location string or lat/lon coordinates.
        """
        adapter = get_propagation_adapter()
        
        # Format location string if coordinates provided
        if lat is not None and lon is not None:
            location = f"{lat},{lon}"
        
        muf_data = await adapter.fetch_muf(location)
        
        if not muf_data:
            raise HTTPException(
                status_code=404,
                detail=f"No MUF data available for location: {location}"
            )
        
        return JSONResponse({"record": muf_data.model_dump()})

    @app.get(
        "/api/propagation/solar-cycle/{year}",
        operation_id="solar_cycle_data",
        tags=["Propagation"],
    )
    async def rest_solar_cycle_data(
        year: int
    ) -> JSONResponse:
        """Get solar cycle information for a specific year.

        Returns predicted or observed solar flux and sunspot numbers for the
        specified year, along with the solar cycle phase and expected propagation
        characteristics.
        
        Args:
            year: Year to analyze (2000-2050)
        """
        # Validate year range
        if year < 2000 or year > 2050:
            raise HTTPException(
                status_code=400,
                detail="Year must be between 2000 and 2050"
            )
        
        adapter = get_propagation_adapter()
        cycle_data = await adapter.get_solar_cycle_data(year)
        
        return JSONResponse({"record": cycle_data.model_dump()})

    @app.get(
        "/api/propagation/aurora",
        operation_id="aurora_conditions",
        tags=["Propagation"],
    )
    async def rest_aurora_conditions() -> JSONResponse:
        """Get current aurora visibility predictions.

        Returns OVATION aurora model data showing where auroras may be visible,
        including view line latitude and best viewing locations.
        """
        adapter = get_propagation_adapter()
        aurora_data = await adapter.fetch_aurora_data()
        
        if not aurora_data:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch aurora data"
            )
        
        return JSONResponse({"record": aurora_data.model_dump()})

    @app.get(
        "/api/propagation/solar-regions",
        operation_id="solar_regions",
        tags=["Propagation"],
    )
    async def rest_solar_regions() -> JSONResponse:
        """Get active solar regions and sunspot groups.

        Returns information about numbered active regions on the Sun,
        including their location, size, magnetic configuration, and
        flare probabilities.
        """
        adapter = get_propagation_adapter()
        regions = await adapter.fetch_solar_regions()
        
        return JSONResponse({
            "count": len(regions),
            "regions": [r.model_dump() for r in regions]
        })

    @app.get(
        "/api/propagation/solar-events",
        operation_id="solar_events",
        tags=["Propagation"],
    )
    async def rest_solar_events(
        days: int = Query(3, ge=1, le=30, description="Number of days of events to retrieve")
    ) -> JSONResponse:
        """Get recent solar events (flares, CMEs, etc.).

        Returns a list of recent solar events including flares, coronal mass
        ejections (CMEs), and proton events. Events are sorted by time with
        the most recent first.
        """
        adapter = get_propagation_adapter()
        events = await adapter.fetch_solar_events(days)
        
        return JSONResponse({
            "count": len(events),
            "events": [e.model_dump() for e in events]
        })

    @app.get(
        "/api/propagation/space-weather",
        operation_id="space_weather_summary",
        tags=["Propagation"],
    )
    async def rest_space_weather_summary() -> JSONResponse:
        """Get comprehensive space weather summary.

        Combines data from multiple sources to provide a complete picture of
        current space weather conditions, including:
        - Solar activity level
        - Geomagnetic storm status (G-scale)
        - Radio blackout status (R-scale)
        - Solar radiation storm status (S-scale)
        - Particle flux measurements
        - Active region count
        - Recent flare activity
        - Aurora visibility
        """
        adapter = get_propagation_adapter()
        summary = await adapter.fetch_space_weather_summary()
        
        if not summary:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch space weather data"
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
            "propagation_conditions",
            "propagation_forecast",
            "propagation_analysis",
            "propagation_muf",
            "solar_cycle_data",
            "aurora_conditions",
            "solar_regions",
            "solar_events",
            "space_weather_summary",
        ],
    )
    mcp.mount()

    return app


# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------
app = create_app()