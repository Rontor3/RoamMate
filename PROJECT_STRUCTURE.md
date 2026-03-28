# RoamMate — Project Structure

## Root Directory

| Path | Description |
|------|-------------|
| `main.py` | Entry point — starts the MCP servers (Tavily search, Hotel/Flight tools) |
| `requirements.txt` | Python package dependencies |
| `.env` | API keys and environment configuration |
| `world-airports.csv` | Airport dataset used by the airport mapper service |
| `APP_CAPABILITIES.md` | Documentation of what the app can do |

---

## `/app` — Core Application

| File | Description |
|------|-------------|
| `main.py` | FastAPI server — exposes `/query`, `/tools`, and the static chat UI. Calls the LangGraph on every query. |
| `graph.py` | **LangGraph workflow** — the 5-node pipeline (Query Parser → Data Ingestion → Signal Extraction → Scoring → Recommendation) |
| `mcp_client.py` | MCP client — connects to and manages sessions with MCP tool servers |
| `models.py` | Shared Pydantic/dataclass models (`TravelIntent`, `Place`, `RankedPlace`, `AreaScores`, etc.) |
| `recommendation_engine.py` | Legacy orchestrator — kept for reference; logic now handled by the LangGraph nodes |

### `/app/services` — Domain Services

#### `/app/services/input`
| File | Description |
|------|-------------|
| `intent_extractor.py` | Calls Groq Llama (via GROQ_API) to extract structured `TravelIntent` from raw user text. Used in **Node 1**. |

#### `/app/services/extraction`
| File | Description |
|------|-------------|
| `geo_resolver.py` | Resolves a city/area name into a `ResolvedArea` with lat/lon using geocoding APIs |

#### `/app/services/mapping`
| File | Description |
|------|-------------|
| `airport_mapper.py` | Finds the nearest airports to a destination using `world-airports.csv` |
| `area_mapper.py` | Maps a list of `Place` objects to geographic `ResolvedArea` zones |

#### `/app/services/scoring`
| File | Description |
|------|-------------|
| `scoring_engine.py` | Pure Python — computes `CrowdScore` and `AuthenticityScore` from Reddit signals and Google data. Used in **Node 4**. |
| `ranker.py` | Deterministic weighted ranking of `Place` objects against a `TravelIntent`. Used in **Node 4**. |

#### `/app/services/cache`
| File | Description |
|------|-------------|
| `cache_manager.py` | Manages caching of resolved destinations, Reddit data, and scores (Redis Tier 1 & 2) |

#### `/app/services/output`
| File | Description |
|------|-------------|
| `explainer.py` | Generates human-readable explanations for why a place was recommended (used for response generation) |

### `/app/utils`
| File | Description |
|------|-------------|
| `logger.py` | Shared logger configuration used across the app |

---

## `/tools` — MCP Tool Servers

These are standalone Python scripts that run as MCP servers. They expose tools the LangGraph's **Node 2 (Data Ingestion)** calls in parallel.

| File | Description |
|------|-------------|
| `hotel_flight_details.py` | **Route B** — Hotel and flight search via Amadeus/Booking MCP |
| `social_media.py` | **Route A** — Tavily search + Reddit signals via `asyncpraw` |
| `map_tools.py` | **Route A & B** — Google Maps MCP for geocoding and place search |
| `weather_tools.py` | **Route A** — OpenWeatherMap MCP for current weather at destination |

---

## `/utils` — Root-Level Utilities
| File | Description |
|------|-------------|
| `date_utils.py` | Date formatting helpers |
| `geocode_utils.py` | Geocoding utility wrappers |
| `string_utils.py` | String manipulation helpers |

---

## `/static` — Frontend
Contains the chat UI served at `http://localhost:8080/` (HTML, CSS, JS).

## `/tests` — Test Suite
Unit and integration tests for individual components.

## `/planner` — Trip Planner (WIP)
Experimental planner module.

## `/database` — DB Layer
Database connection and schema files.

## `/conversations` — Conversation Logs
Auto-generated JSON logs of each conversation turn (for debugging and history).
