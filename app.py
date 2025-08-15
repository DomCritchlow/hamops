import os, json
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from hamops.middleware_logging import RequestLogMiddleware
from hamops.mcp_server import mcp 
from hamops.adapters.callsign import lookup_callsign

API_KEY = os.getenv("API_KEY")


app = FastAPI(title="HAM Ops")

app.add_middleware(RequestLogMiddleware)

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




@app.get("/api/callsign/{callsign}")
async def rest_callsign(callsign: str, _=Depends(require_api_key)):
    rec = await lookup_callsign(callsign)
    if not rec:
        raise HTTPException(status_code=404, detail="Callsign not found")
    # Avoid PII-heavy address fields by design
    return JSONResponse({"record": rec.model_dump()})





# --- Mount MCP (Streamable HTTP) under /mcp ---
# FastMCP exposes an ASGI app we can mount.
app.mount("/mcp", mcp.streamable_http_app())