import os, json
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from hamops.middleware_logging import RequestLogMiddleware
#from hamops.mcp_server import mcp 
from hamops.adapters.callsign import lookup_callsign

from fastapi_mcp import FastApiMCP

API_KEY = os.getenv("API_KEY")

# CRITICAL: Create the MCP HTTP app first


# CRITICAL: Use MCP's lifespan when creating FastAPI app
app = FastAPI(title="Hamops")



# Add CORS middleware for Claude
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLogMiddleware)

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def require_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    
# --- Handy browser targets ---
@app.get("/")
def root():
    return {
        "ok": True, 
        "service": "HAM Ops", 
        "docs": "/docs", 
        "health": "/health",
        "mcp": "/mcp"  # Let users know about MCP endpoint
    }

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/callsign/{callsign}", operation_id="callsign_lookup")
async def rest_callsign(callsign: str, _=Depends(require_api_key)):
    rec = await lookup_callsign(callsign)
    if not rec:
        raise HTTPException(status_code=404, detail="Callsign not found")
    return JSONResponse({"record": rec.model_dump()})

# Mount MCP app
mcp = FastApiMCP(app, include_operations=['callsign_lookup'])
mcp.mount()