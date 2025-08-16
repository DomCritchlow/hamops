from fastmcp import FastMCP
from hamops.adapters.callsign import lookup_callsign

# Create FastMCP instance (no stateless_http parameter needed)
mcp = FastMCP("HAM Ops")

@mcp.tool
async def callsign_lookup(callsign: str) -> str:
    """Look up a ham radio callsign. Returns operator information."""
    rec = await lookup_callsign(callsign)
    if rec:
        parts = []
        if rec.name:
            parts.append(f"Name: {rec.name}")
        if rec.callsign:
            parts.append(f"Call: {rec.callsign}")
        if rec.license_class:
            parts.append(f"Class: {rec.license_class}")
        if rec.status:
            parts.append(f"Status: {rec.status}")
        if rec.grid:
            parts.append(f"Grid: {rec.grid}")
        if rec.country:
            parts.append(f"Country: {rec.country}")
        if rec.expires:
            parts.append(f"Expires: {rec.expires}")
        if rec.lat and rec.lon:
            parts.append(f"Coords: {rec.lat}, {rec.lon}")
        
        return " | ".join(parts) if parts else "Callsign found but no details available"
    return f"Callsign {callsign} not found in database"

# Remove the generic search/fetch tools if not using them