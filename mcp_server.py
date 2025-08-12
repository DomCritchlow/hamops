

from hamops.adapters.aprs import aprs_active, aprs_track
from hamops.schemas import AprsActiveQuery

from mcp.server.fastmcp import FastMCP
from typing import Any, Dict

from hamops.adapters.callsign import lookup_callsign


mcp = FastMCP("HAM Ops", stateless_http=True)  # streamable HTTP friendly

# Baseline tools so ChatGPT’s connector validator is satisfied
@mcp.tool()
def search(query: str) -> dict:
    """Lightweight query router. Use: aprs:active center='lat,lon' radius_km=20 since=120"""
    return {"results": []}

@mcp.tool()
def fetch(id: str) -> dict:
    """Expand an item returned by search."""
    return {"item": None}

# Domain tools
@mcp.tool()
async def aprs_active_tool(center: dict, radius_km: float, since_minutes: int) -> dict:
    """List APRS stations active within an area since N minutes."""
    q = AprsActiveQuery(center=center, radius_km=radius_km, since_minutes=since_minutes)
    stations = await aprs_active(q)
    return {"stations": [s.model_dump() for s in stations]}

@mcp.tool()
async def aprs_track_tool(callsign: str, since_minutes: int = 120) -> dict:
    """Track a station over the last N minutes."""
    track = await aprs_track(callsign, since_minutes)
    return {"track": track.model_dump()}


@mcp.tool()
async def callsign_lookup(callsign: str) -> dict:
    """Look up a ham callsign. Returns coarse info (no full address)."""
    rec = await lookup_callsign(callsign)
    return {"record": rec.model_dump() if rec else None}
