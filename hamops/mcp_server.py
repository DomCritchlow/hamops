from typing import Any, Dict
from mcp.server.fastmcp import FastMCP

from hamops.adapters.callsign import lookup_callsign

mcp = FastMCP("HAM Ops", stateless_http=True)

# Baseline tools so ChatGPT’s connector validator is satisfied
@mcp.tool()
def search(query: str) -> dict:
    return {"results": []}

@mcp.tool()
def fetch(id: str) -> dict:
    return {"item": None}


@mcp.tool()
async def callsign_lookup(callsign: str) -> dict:
    """Look up a ham callsign. Returns coarse info (no full address)."""
    rec = await lookup_callsign(callsign)
    return {"record": rec.model_dump() if rec else None}
