# RoamMate

## Project Overview
RoamMate is a modular trip planning and travel assistant platform. It integrates LLM-powered itinerary planning, mapping, booking, weather, and social media tools.

## Project Structure

```
roam_mate/
│
├── main.py                 # MCP server entrypoint (loads and runs everything)
├── requirements.txt        # Python dependencies
├── .env.example            # Sample environment variables (API keys, secrets, etc.)
├── README.md               # Project overview and setup instructions
│
├── planner/                # Trip planning logic and LLM prompts
│   ├── __init__.py
│   ├── day_planner.py      # Main itinerary logic using LLM and tool calls
│   └── preferences.py      # Collects and processes user preferences
│
├── tools/                  # External integrations/tools (each as own module)
│   ├── __init__.py
│   ├── map_tools.py        # Mapping, geocoding, POI search functions
│   ├── weather_tools.py    # Weather fetch and forecast integration
│   ├── booking_tools.py    # Hotel/ticket booking APIs
│   └── social_tools.py     # Reddit, Instagram, TripAdvisor, etc.
│
├── utils/                  # Pure helper functions, converters, formatters
│   ├── __init__.py
│   ├── date_utils.py       # Date/time parsing and formatting
│   ├── geocode_utils.py    # Coordinates, distance, routing helpers
│   └── string_utils.py     # Text processing, validation
│
├── resources/              # MCP resources (read-only endpoints)
│   ├── __init__.py
│   └── travel_resources.py # Expose trip plans, summaries as resource:// URIs
│
├── tests/                  # Unit and integration tests
│   ├── __init__.py
│   ├── test_tools.py
│   ├── test_utils.py
│   ├── test_planner.py
│   └── test_mcp_server.py
│
├── static/                 # Static files, example configs, static map tiles
│
└── database/               # Database models and management (if needed)
    ├── __init__.py
    └── models.py
```

## Setup Instructions
1. Copy `.env.example` to `.env` and fill in your secrets.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the server: `python main.py`

## Contributing
Pull requests welcome!
