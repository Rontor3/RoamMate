# 🌍 RoamMate - Application Capabilities & Functions

This document outlines the core functions, services, and integrations implemented in the RoamMate application.

## 🛠️ MCP Servers & Tools
These are the AI-powered tools exposed to the agent and user:

### 1. Social Travel Insights (`SocialTravelInsights`)
- **`scrape_and_extract_travel_advice(user_prefs)`**: 
  - Searches Reddit for travel discussions based on user location & interests.
  - Extracts place names, food recommendations, and itineraries using an LLM.
  - Summarizes community sentiment.

### 2. Hotel & Flight Booking (`HotelFlightBooking`)
- **`search_flights(origin, destination, date, currency)`**: 
  - Finds real-time flight options using Amadeus API.
  - Returns prices (default INR), airlines, and booking links.
- **`search_hotels(city_code, budget)`**: 
  - Lists top rated hotels in a city.
  - Provides deep links to Booking.com with affiliate tracking.
- **`perform_live_search(query)`**: 
  - Google Custom Search for real-time events, news, or specific queries (e.g., "concerts in Mumbai today").
- **`get_current_info(ip)`**: 
  - Detects user location and current date/time to provide context-aware answers.
- **`generate_travel_links(type, names)`**: 
  - Creates affiliate/booking links for hotels, flights, trains, and buses.

---

## 🧠 Recommendation Engine (`app/recommendation_engine.py`)
The intelligent core that processes user requests:

### 1. Input Processing
- **Intent Extraction** (`services/input/intent_extractor.py`):
  - Uses Llama-3 (via Groq) to parse natural language (e.g., "romantic trip to Paris") into structured data (Budget, Vibe, Duration).
- **Geo Resolution** (`services/extraction/geo_resolver.py`):
  - Converts place names to coordinates using Google Geocoding API (with Nominatim fallback).
  - Caches results to reduce API costs.

### 2. Scoring & Ranking
- **Scoring Engine** (`services/scoring/scoring_engine.py`):
  - **Crowd Score**: Estimates busyness based on Reddit mentions and popularity signals.
  - **Authenticity Score**: Detects "hidden gems" vs "tourist traps" using local language and rating patterns.
- **Ranker** (`services/scoring/ranker.py`):
  - Personalizes results by weighting factors (Quality, Crowd, Authenticity) based on user vibe (e.g., "Quiet" prioritizes low crowd).

### 3. Mapping
- **Airport Mapper** (`services/mapping/airport_mapper.py`):
  - Finds nearest airports to a destination.
  - Filters by airport size (Large/Medium) and distance.
- **Area Mapper** (`services/mapping/area_mapper.py`):
  - Maps specific places (cafes, museums) to their neighborhood/area for context.

### 4. Output Generation
- **Explainer** (`services/output/explainer.py`):
  - Generates natural language reasons for WHY a place was recommended (e.g., "This hidden gem is perfect for your quiet trip...").
- **Cache Manager** (`services/cache/cache_manager.py`):
  - Saves City and Place data to JSON files to speed up repeat queries.

---

## 🔌 API & System
- **FastAPI Server** (`app/main.py`):
  - **`/query`**: Endpoint for chat interface to send user messages.
  - **`/tools`**: Endpoint to list available MCP capabilities.
  - **Static Files**: Serves the frontend web interface.
