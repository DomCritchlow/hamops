from hamops.schemas import (
    AprsActiveQuery, AprsStation, AprsTrack, AprsTrackPoint,
    CenterLatLon, CenterPlace, CenterMaidenhead
)


import os, math
import httpx
from typing import List
from pydantic import BaseModel

APRFI_KEY = os.getenv("APRFI_API_KEY")   # get a key from aprs.fi (respect their ToS)
APRFI_BASE = "https://api.aprs.fi/api/get"

class Geo(BaseModel):
    lat: float
    lon: float

async def _geocode_center(center) -> Geo:
    # Minimal demo: handle lat/lon; TODO: add Nominatim for place + a Maidenhead->lat/lon helper
    if isinstance(center, CenterLatLon):
        return Geo(lat=center.lat, lon=center.lon)
    if isinstance(center, CenterPlace):
        # TODO: real geocoding; placeholder raises for now
        raise NotImplementedError("place geocoding not yet implemented")
    if isinstance(center, CenterMaidenhead):
        # TODO: convert Maidenhead to lat/lon
        raise NotImplementedError("maidenhead geocoding not yet implemented")
    raise ValueError("unknown center type")

async def aprs_active(q: AprsActiveQuery) -> List[AprsStation]:
    """
    Uses aprs.fi 'box' query as a simple MVP (bbox around center+radius).
    For APRS-IS live filtering, swap in a socket client later.
    """
    if not APRFI_KEY:
        return []

    center = await _geocode_center(q.center)
    # Build a rough bbox from radius (km) ~ lat/lon degrees
    dlat = q.radius_km / 111.0
    dlon = q.radius_km / (111.0 * math.cos(math.radians(center.lat)))
    bbox = (center.lat - dlat, center.lon - dlon, center.lat + dlat, center.lon + dlon)

    params = {
        "what": "loc",
        "bbox": f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}",
        "format": "json",
        "apikey": APRFI_KEY,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(APRFI_BASE, params=params)
        r.raise_for_status()
        data = r.json()

    stations: List[AprsStation] = []
    for item in data.get("entries", []):
        # Filter by recency (since_minutes)
        # aprs.fi returns 'lasttime' as epoch
        try:
            import datetime as dt
            last = dt.datetime.utcfromtimestamp(int(item.get("lasttime", 0))).isoformat() + "Z"
        except Exception:
            last = None

        stations.append(AprsStation(
            callsign=item.get("name",""),
            last_heard_utc=last or "",
            lat=float(item.get("lat", 0)),
            lon=float(item.get("lng", 0)),
            symbol=item.get("symbol"),
            heard_via=None,
            comment=item.get("comment"),
            source="aprs.fi",
        ))
    return stations

async def aprs_track(callsign: str, since_minutes: int) -> AprsTrack:
    if not APRFI_KEY:
        return AprsTrack(callsign=callsign, points=[], source="aprs.fi")
    params = {
        "what": "loc",
        "name": callsign,
        "format": "json",
        "apikey": APRFI_KEY,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(APRFI_BASE, params=params)
        r.raise_for_status()
        data = r.json()
        
    pts: list[AprsTrackPoint] = []
    import datetime as dt
    cutoff = dt.datetime.utcnow() - dt.timedelta(minutes=since_minutes)
    for e in data.get("entries", []):
        t = dt.datetime.utcfromtimestamp(int(e.get("lasttime",0)))
        if t < cutoff: 
            continue
        pts.append(AprsTrackPoint(
            t=t.isoformat()+"Z",
            lat=float(e.get("lat",0)),
            lon=float(e.get("lng",0)),
        ))
    return AprsTrack(callsign=callsign, points=pts, source="aprs.fi")
