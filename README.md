# Hamops

Hamops is a small FastAPI service with an MCP (Model Context Protocol) server. It
is meant to grow into a library of amateur‑radio utilities exposed over HTTP.

[Hamops deployed](https://hamops-uiggriujca-uc.a.run.app/)

## Available Services

### Callsign Lookup
- **REST:** `GET /api/callsign/{callsign}`
- **MCP:** operation id `callsign_lookup`
- **Web UI:** visit the root URL and use the form to query a callsign

### APRS Location
- **REST:** `GET /api/aprs/locations/{callsign}`
- **MCP:** operation id `aprs_locations`

### APRS Weather
- **REST:** `GET /api/aprs/weather/{callsign}`
- **MCP:** operation id `aprs_weather`

### APRS Messages
- **REST:** `GET /api/aprs/messages/{callsign}`
- **MCP:** operation id `aprs_messages`

### Band Plan Services

#### Band at Frequency
- **REST:** `GET /api/bands/frequency/{frequency}`
- **MCP:** operation id `band_at_frequency`
- **Description:** Find what band, modes, and license privileges are available at a specific frequency
- **Frequency formats:** "14.225 MHz", "146520 kHz", "144000000 Hz", or "14.225" (assumes MHz)

#### Search Bands
- **REST:** `GET /api/bands/search`
- **MCP:** operation id `search_bands`
- **Query parameters:**
  - `mode`: Filter by mode (CW, USB, LSB, FM, AM, etc.)
  - `band_name`: Filter by band name (160m, 80m, 40m, 20m, 2m, 70cm, etc.)
  - `license_class`: Filter by license (Technician, General, Advanced, Extra)
  - `typical_use`: Filter by use (Phone, Digital, Satellite, Emergency, etc.)
  - `min_frequency`: Minimum frequency with units
  - `max_frequency`: Maximum frequency with units

#### Bands in Range
- **REST:** `GET /api/bands/range/{start_frequency}/{end_frequency}`
- **MCP:** operation id `bands_in_range`
- **Description:** Get all band segments within a frequency range

#### Band Plan Summary
- **REST:** `GET /api/bands/summary`
- **MCP:** operation id `band_plan_summary`
- **Description:** Get metadata about the loaded band plan

## Web Interface

The root endpoint (`/`) serves a simple single‑column interface that works on
desktop and mobile browsers. Each tool accepts a callsign query and shows the
JSON response inline with a loading indicator. The band plan tools allow
searching by frequency, mode, band name, and license class.

## API Usage

For programmatic access, use the `/api` prefix. If the `OPENAI_API_KEY`
environment variable is set, include an `x-api-key` header with each
request:

- `GET /api` – service metadata
- `GET /api/callsign/{callsign}` – perform a lookup
- `GET /api/aprs/locations/{callsign}` – APRS location history
- `GET /api/aprs/weather/{callsign}` – latest APRS weather report
- `GET /api/aprs/messages/{callsign}` – APRS messages to/from a callsign
- `GET /api/bands/frequency/{freq}` – band info at a frequency
- `GET /api/bands/search` – search band segments
- `GET /api/bands/range/{start}/{end}` – bands in a range
- `GET /api/bands/summary` – band plan metadata
- `GET /health` – basic health check

## Development

### Requirements
- Python 3.11+
- [HamDB](http://api.hamdb.org) network access for callsign lookups
- Internet access to fetch band plan data

### Local Development

```bash
# Set up virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env  # fill in any needed values

# Generate band plan data (first time only)
python scripts/gen_bandplan.py

# Start the server
uvicorn hamops.main:app --reload
```

Visit `http://localhost:8000` for the web UI or `http://localhost:8000/docs`
for the interactive API documentation.

### Setup Script

For convenience, you can use the setup script to generate the band plan data:

```bash
chmod +x setup.sh
./setup.sh
```

### Docker

```bash
# Build the image
docker build -t hamops .

# Generate band plan data (run once)
docker run --rm -v $(pwd)/hamops/data:/app/hamops/data hamops python scripts/gen_bandplan.py

# Run with environment variables from .env
docker run --env-file .env -p 8080:8080 -v $(pwd)/hamops/data:/app/hamops/data hamops
```

### Google Cloud Run

```bash
# Generate band plan data locally first
python scripts/gen_bandplan.py

# Deploy to Cloud Run
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

The MCP server is automatically mounted at `/mcp` and exposes all the 
operations listed above. Any MCP client that supports HTTP transport can
interact with it at that endpoint.

### MCP Operations Available:
- `callsign_lookup` - Look up amateur radio callsigns
- `aprs_locations` - Get APRS location data
- `aprs_weather` - Get APRS weather reports
- `aprs_messages` - Get APRS messages
- `band_at_frequency` - Find band info at a specific frequency
- `search_bands` - Search for band segments by criteria
- `bands_in_range` - Get bands within a frequency range
- `band_plan_summary` - Get band plan metadata

## Data Sources

- **Callsign data:** [HamDB.org](http://api.hamdb.org)
- **APRS data:** [aprs.fi](https://aprs.fi) (requires API key in `.env`)
- **Band plan data:** [SDR-Band-Plans](https://github.com/Arrin-KN1E/SDR-Band-Plans)

## Band Plan Features

The band plan service provides comprehensive information about US amateur radio
frequency allocations. It can answer questions like:

- What privileges do I have at 14.225 MHz?
- Where can I operate CW with a General license?
- What bands are available for satellite communication?
- What modes are allowed in the 20m band?
- Which frequencies can Technician licensees use for phone?

The frequency parser intelligently handles multiple unit formats, making it
easy to query using whatever format is most convenient.