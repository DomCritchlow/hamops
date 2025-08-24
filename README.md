# Hamops

> Modern Amateur Radio APIs with Model Context Protocol (MCP) Integration

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-00a393.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Hamops is a comprehensive FastAPI service providing amateur radio utilities through REST APIs and Model Context Protocol. Query callsigns, track APRS data, and explore US band plans with intelligent frequency parsing and rich metadata.

🌐 **Live Demo**: [https://hamops-uiggriujca-uc.a.run.app/](https://hamops-uiggriujca-uc.a.run.app/)

📘 **MCP Query Example**: [Cross-Country APRS Expedition](hamops/web/examples/Query_Example.md) – generated in Claude Desktop using this API with no additional context.

---

## ✨ Features

- **📻 Callsign Lookup** - FCC registration data via HamDB
- **📡 APRS Tracking** - Real-time location, weather, and messaging
- **📊 Band Plan Database** - Complete US frequency allocations with license privileges
- **🤖 MCP Integration** - AI-ready endpoints for natural language queries
- **⚡ High Performance** - Built on FastAPI with async support
- **🎨 Modern Web UI** - Clean, responsive interface for all services

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Internet access for external APIs
- (Optional) API keys for enhanced features

### Local Development

```bash
# Clone the repository
git clone https://github.com/domcritchlow/hamops.git
cd hamops

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env to add your API keys (optional)

# Generate band plan data (first time only)
python scripts/gen_bandplan.py

# Start the server
uvicorn hamops.main:app --reload
```

Visit `http://localhost:8000` for the web interface or `http://localhost:8000/docs` for interactive API documentation.

---

## 📚 API Reference

### Authentication

Optional API key authentication via `x-api-key` header. Set `OPENAI_API_KEY` environment variable to enable.

### Endpoints

#### Callsign Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/callsign/{callsign}` | GET | Look up amateur radio operator information |

#### APRS Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/aprs/locations/{callsign}` | GET | Track position reports with speed, altitude, and path |
| `/api/aprs/weather/{callsign}` | GET | Current weather conditions from APRS stations |
| `/api/aprs/messages/{callsign}` | GET | Text messages sent to/from a callsign |

#### Band Plan Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bands/frequency/{frequency}` | GET | Find band, modes, and privileges at a frequency |
| `/api/bands/search` | GET | Search bands by mode, license, or use |
| `/api/bands/range/{start}/{end}` | GET | Get all bands within a frequency range |
| `/api/bands/summary` | GET | Band plan metadata and statistics |

#### System

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/api` | GET | Service metadata |
| `/health` | GET | Health check |
| `/docs` | GET | Interactive API documentation |
| `/mcp` | * | Model Context Protocol endpoint |

### Frequency Formats

The band plan services accept frequencies in multiple formats:
- `14.225 MHz` or `14.225MHz`
- `146520 kHz` or `146520kHz`
- `144000000 Hz` or `144000000`
- `14.225` (assumes MHz if decimal present)

---

## 🤖 Model Context Protocol (MCP)

All endpoints are exposed through MCP at `/mcp`, enabling AI assistants to query ham radio data using natural language.

### Available Operations

- `callsign_lookup` - Look up amateur radio callsigns
- `aprs_locations` - Get APRS location data
- `aprs_weather` - Get APRS weather reports
- `aprs_messages` - Get APRS messages
- `band_at_frequency` - Find band info at a specific frequency
- `search_bands` - Search for band segments by criteria
- `bands_in_range` - Get bands within a frequency range
- `band_plan_summary` - Get band plan metadata

### Example Queries

AI assistants can handle natural language queries like:
- "What privileges do I have at 14.225 MHz with a General license?"
- "Find CW frequencies available to Technician operators"
- "Show me the weather at KD4PMP's station"
- "What band is 146.52 MHz in?"

---

## 🐳 Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t hamops .

# Generate band plan data (run once)
docker run --rm -v $(pwd)/hamops/data:/app/hamops/data hamops python scripts/gen_bandplan.py

# Run the container
docker run --env-file .env -p 8080:8080 -v $(pwd)/hamops/data:/app/hamops/data hamops
```

### Docker Compose

```yaml
version: '3.8'
services:
  hamops:
    build: .
    ports:
      - "8080:8080"
    env_file: .env
    volumes:
      - ./hamops/data:/app/hamops/data
```

---

## ☁️ Cloud Deployment

### Google Cloud Run

```bash
# Generate band plan data locally first
python scripts/gen_bandplan.py

# Deploy to Cloud Run
gcloud run deploy hamops \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars APRFI_API_KEY=your_key

# Get the deployed URL
gcloud run services describe hamops \
  --region us-central1 \
  --format="value(status.url)"
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Optional: APRS.fi API key for weather and messaging
APRFI_API_KEY=your_aprs_fi_api_key

# Optional: Enable API key authentication
OPENAI_API_KEY=your_api_key
```

### Band Plan Data

The band plan data must be generated before first use:

```bash
# Using the setup script
chmod +x setup.sh
./setup.sh

# Or directly
python scripts/gen_bandplan.py
```

This creates `hamops/data/us_bandplan.json` with over 1000 band segments.

---

## 📊 Data Sources

| Source | Description | Used For |
|--------|-------------|----------|
| [HamDB.org](http://api.hamdb.org) | FCC amateur radio database | Callsign lookups |
| [APRS.fi](https://aprs.fi) | Global APRS network | Location, weather, messages |
| [SDR-Band-Plans](https://github.com/Arrin-KN1E/SDR-Band-Plans) | Frequency allocations | US band plan data |

---

## 🏗️ Project Structure

```
hamops/
├── hamops/
│   ├── main.py              # FastAPI application
│   ├── adapters/            # External API integrations
│   │   ├── aprs.py         # APRS.fi adapter
│   │   ├── bandplan.py     # Band plan query engine
│   │   └── callsign.py     # HamDB adapter
│   ├── models/              # Pydantic data models
│   ├── middleware/          # Logging and request handling
│   ├── web/                # Web interface assets
│   └── data/               # Generated band plan data
├── scripts/
│   └── gen_bandplan.py     # Band plan generator
├── requirements.txt         # Python dependencies
├── Dockerfile              # Container configuration
├── cloudbuild.yaml         # GCP deployment config
└── setup.sh                # Setup automation script
```

---

## 🧪 Development

### Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest tests/
```

### API Testing

Use the interactive documentation at `/docs` for testing endpoints with the Swagger UI.

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- [HamDB.org](http://hamdb.org) for callsign data
- [APRS.fi](https://aprs.fi) for APRS network access
- [Arrin-KN1E](https://github.com/Arrin-KN1E) for SDR band plan data
- The amateur radio community for ongoing support

---

## 📧 Contact

- **GitHub**: [https://github.com/domcritchlow/hamops](https://github.com/domcritchlow/hamops)
- **Issues**: [https://github.com/domcritchlow/hamops/issues](https://github.com/domcritchlow/hamops/issues)

---

<div align="center">
  <b>73</b><br>
</div>