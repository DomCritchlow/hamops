# Hamops

Hamops is a small FastAPI service with an MCP (Model Context Protocol) server. It
is meant to grow into a library of amateur‑radio utilities exposed over HTTP.

## Available Services

### Callsign Lookup
- **REST:** `GET /api/callsign/{callsign}`
- **MCP:** operation id `callsign_lookup`
- **Web UI:** visit the root URL and use the form to query a callsign

## Web Interface

The root endpoint (`/`) serves a minimal single‑page app that works on desktop
and mobile browsers. It provides a form for callsign lookups and displays the
JSON response from the service.

## API Usage

For programmatic access, use the `/api` prefix:

- `GET /api` – service metadata
- `GET /api/callsign/{callsign}` – perform a lookup
- `GET /health` – basic health check

## Development

### Requirements
- Python 3.11+
- [HamDB](http://api.hamdb.org) network access for callsign lookups

### Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in any needed values
uvicorn hamops.main:app --reload
```

Visit `http://localhost:8000` for the web UI or `http://localhost:8000/docs`
for the interactive API documentation.

### Docker

```bash
docker build -t hamops .
# Run with environment variables from .env
docker run --env-file .env -p 8080:8080 hamops
```

### Google Cloud Run

```bash
gcloud run deploy hamops \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

Retrieve the deployed URL:

```bash
gcloud run services describe hamops \
  --region us-central1 \
  --format="value(status.url)"
```

## MCP

The MCP server is automatically mounted at `/mcp` and exposes the
`callsign_lookup` operation. Any MCP client that supports HTTP transport can
interact with it at that endpoint.
