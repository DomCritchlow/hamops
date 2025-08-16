import os
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware

from hamops.middleware_logging import RequestLogMiddleware
from hamops.mcp_server import mcp 
from hamops.adapters.callsign import lookup_callsign

API_KEY = os.getenv("API_KEY")

# Create the MCP HTTP app first
mcp_app = mcp.http_app(path="/mcp")

# Create FastAPI app with MCP's lifespan
app = FastAPI(
    title="HAM Ops",
    lifespan=mcp_app.lifespan  # Important: Use MCP's lifespan
)

# Add CORS middleware for Claude web interface
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, be more specific
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLogMiddleware)

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

def require_api_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    
# --- Browser endpoints ---
@app.get("/")
def root():
    return {
        "ok": True, 
        "service": "HAM Ops", 
        "docs": "/docs", 
        "health": "/health",
        "mcp": "/mcp"  # Add MCP endpoint to discovery
    }

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/callsign/{callsign}")
async def rest_callsign(callsign: str, _=Depends(require_api_key)):
    rec = await lookup_callsign(callsign)
    if not rec:
        raise HTTPException(status_code=404, detail="Callsign not found")
    return JSONResponse({"record": rec.model_dump()})

# --- Mount MCP server ---
# Mount the MCP HTTP app
app.mount("/mcp", mcp_app)