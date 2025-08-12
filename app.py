from hamops.mcp_server import mcp 
from hamops.schemas import AprsActiveQuery 

import os, logging, json
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from hamops.adapters.aprs import aprs_active, aprs_track
from hamops.middleware_logging import RequestLogMiddleware


# ... existing imports
from hamops.adapters.callsign import lookup_callsign
# LOG already configured earlier


# --- logging setup (stdout is picked up by Cloud Run) ---
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
LOG = logging.getLogger("hamops")



API_KEY = os.getenv("API_KEY")

app = FastAPI(title="HAM Ops")

app.add_middleware(RequestLogMiddleware)  # <= enable request logging

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)
def require_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    
# --- Handy browser targets ---
@app.get("/")
def root():
    return {"ok": True, "service": "HAM Ops", "docs": "/docs", "health": "/health"}

@app.get("/health")
def health():
    return {"ok": True}

# --- REST endpoints for Custom GPT Actions ---
@app.post("/api/aprs/active")
async def rest_aprs_active(q: AprsActiveQuery, _=Depends(require_api_key)):
    stations = await aprs_active(q)
    LOG.info(json.dumps({
        "event": "aprs_active",
        "params": q.model_dump(),
        "station_count": len(stations)
    }))
    return JSONResponse({"stations": [s.model_dump() for s in stations]})

@app.get("/api/aprs/track/{callsign}")
async def rest_aprs_track(callsign: str, since_minutes: int = 120, _=Depends(require_api_key)):
    track = await aprs_track(callsign, since_minutes)
    LOG.info(json.dumps({
        "event": "aprs_track",
        "callsign": callsign,
        "points": len(track.points)
    }))
    return JSONResponse({"track": track.model_dump()})




@app.get("/api/callsign/{callsign}")
async def rest_callsign(callsign: str, _=Depends(require_api_key)):
    rec = await lookup_callsign(callsign)
    if not rec:
        raise HTTPException(status_code=404, detail="Callsign not found")
    # Avoid PII-heavy address fields by design
    return JSONResponse({"record": rec.model_dump()})

# Optional: browser-friendly alias with query param
@app.get("/api/callsign")
async def rest_callsign_q(callsign: str, _=Depends(require_api_key)):
    rec = await lookup_callsign(callsign)
    if not rec:
        raise HTTPException(status_code=404, detail="Callsign not found")
    return JSONResponse({"record": rec.model_dump()})




# --- Mount MCP (Streamable HTTP) under /mcp ---
# FastMCP exposes an ASGI app we can mount.
app.mount("/mcp", mcp.streamable_http_app())
