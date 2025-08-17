
"""
APRS.fi adapter for location and weather queries.

This module provides simple async functions to fetch APRS location and weather data using the APRS.fi API.
Set the environment variable APRFI_API_KEY to your API key. Optionally, override the base URL with APRS_API_BASE_URL.
"""

from __future__ import annotations

import os
import httpx
from hamops.middleware.logging import log_info, log_warning, log_error

from typing import Optional, Any, Dict

from hamops.models.aprs import APRSLocationRecord, APRSWeatherRecord

# --- Helpers ---
def _to_float(val: Any) -> Optional[float]:
    """Convert value to float, return None if not possible or blank/placeholder."""
    try:
        s = str(val).strip()
        if not s or s in {"-", "--", "---", "nan", "None"}:
            return None
        return float(s)
    except Exception:
        return None

def _to_int(val: Any) -> Optional[int]:
    """Convert value to int, return None if not possible or blank/placeholder."""
    try:
        s = str(val).strip()
        if not s or s in {"-", "--", "---", "nan", "None"}:
            return None
        return int(float(s))
    except Exception:
        return None


async def _fetch_aprs(params: Dict[str, str | int | float]) -> Optional[dict]:
    """Query the APRS.fi API and return the JSON response dict, or None on error."""
    api_key = os.getenv("APRFI_API_KEY")
    if not api_key:
        log_warning("aprs_api_key_missing", message="APRFI_API_KEY not set.", params=params)
        return None
    base_url = os.getenv("APRS_API_BASE_URL", "https://api.aprs.fi/api/get")
    query = {**params, "apikey": api_key, "format": "json"}
    try:
        log_info("aprs_api_request", base_url=base_url, params=params)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(base_url, params=query)
        if resp.status_code != 200:
            log_warning("aprs_api_response_status", status_code=resp.status_code, text=resp.text)
            return None
        return resp.json()
    except Exception as e:
        log_error("aprs_api_request_error", error=str(e), params=params)
        return None



async def get_aprs_location(callsign: str) -> Optional[APRSLocationRecord]:
    """Get the latest APRS location for a callsign, or None if not found."""
    data = await _fetch_aprs({"what": "loc", "name": callsign})
    if not data or not isinstance(data, dict):
        return None
    entries = data.get("entries") or []
    if not entries:
        return None
    entry = entries[0]
    return APRSLocationRecord(
        name=entry.get("name", callsign),
        time=_to_int(entry.get("time")),
        lasttime=_to_int(entry.get("lasttime")),
        lat=_to_float(entry.get("lat")),
        lng=_to_float(entry.get("lng")),
        course=_to_float(entry.get("course")),
        speed=_to_float(entry.get("speed")),
        altitude=_to_float(entry.get("altitude")),
        symbol=entry.get("symbol"),
        srccall=entry.get("srccall"),
        dstcall=entry.get("dstcall"),
        comment=entry.get("comment"),
        path=entry.get("path"),
        phg=entry.get("phg"),
        status=entry.get("status"),
        status_lasttime=_to_int(entry.get("status_lasttime")),
    )




async def get_aprs_weather(callsign: str) -> Optional[APRSWeatherRecord]:
    """Get the latest weather report for an APRS weather station callsign, or None if not found."""
    data = await _fetch_aprs({"what": "wx", "name": callsign})
    if not data or not isinstance(data, dict):
        return None
    entries = data.get("entries") or []
    if not entries:
        return None
    entry = entries[0]
    return APRSWeatherRecord(
        name=entry.get("name", callsign),
        time=_to_int(entry.get("time")),
        temp=_to_float(entry.get("temp")),
        pressure=_to_float(entry.get("pressure")),
        humidity=_to_float(entry.get("humidity")),
        wind_direction=_to_float(entry.get("wind_direction")),
        wind_speed=_to_float(entry.get("wind_speed")),
        wind_gust=_to_float(entry.get("wind_gust")),
        rain_1h=_to_float(entry.get("rain_1h")),
        rain_24h=_to_float(entry.get("rain_24h")),
        rain_mn=_to_float(entry.get("rain_mn")),
        luminosity=_to_float(entry.get("luminosity")),
    )