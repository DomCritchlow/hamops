

"""Pydantic models for APRS data.

This module defines data structures used by the APRS adapters.  Each
class mirrors the shape of the objects returned from the aprs.fi API
when querying location and weather information.  Optional fields are
used liberally to accommodate missing data.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional


class APRSLocationRecord(BaseModel):
    """Normalized APRS location data returned from the aprs.fi service.

    All numeric fields (lat/lng/course/speed/altitude) are converted to
    Python floats when possible.  Times are returned as Unix epoch
    seconds (int) if present.  Additional APRS metadata is surfaced
    directly as strings.
    """

    name: str
    time: Optional[int] = None
    lasttime: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    course: Optional[float] = None
    speed: Optional[float] = None
    altitude: Optional[float] = None
    symbol: Optional[str] = None
    srccall: Optional[str] = None
    dstcall: Optional[str] = None
    comment: Optional[str] = None
    path: Optional[str] = None
    phg: Optional[str] = None
    status: Optional[str] = None
    status_lasttime: Optional[int] = None


class APRSWeatherRecord(BaseModel):
    """Normalized APRS weather data, including location (lat/lng)."""

    name: str
    time: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    temp: Optional[float] = None
    pressure: Optional[float] = None
    humidity: Optional[float] = None
    wind_direction: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_gust: Optional[float] = None
    rain_1h: Optional[float] = None
    rain_24h: Optional[float] = None
    rain_mn: Optional[float] = None
    luminosity: Optional[float] = None


class APRSMessageRecord(BaseModel):
    """Normalized APRS message data."""
    time: Optional[int] = None
    fromcall: Optional[str] = None
    tocall: Optional[str] = None
    message: Optional[str] = None
    path: Optional[str] = None
    type: Optional[str] = None