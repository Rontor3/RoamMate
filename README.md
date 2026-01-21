# RoamMate 🌍✈️

**RoamMate** is a sophisticated, AI-powered travel consultant designed to plan perfect trips with real-time data and actionable booking links. Built with **FastAPI** and the **Model Context Protocol (MCP)**, it offers a seamless, privacy-focused travel planning experience.

## ✨ Key Features

-   **"Invisible Reasoning" Engine**: Uses a sophisticated 5-stage internal process (Intent, Search, Extraction, Linking, Synthesis) to deliver expert advice without technical clutter.
-   **Live Travel Data**: Integrates **Google Custom Search API** to fetch real-time hotel reviews, flight options, and travel blogs.
-   **Deep Linking**: Automatically generates direct booking links for:
    -   🏨 **Hotels** (Booking.com)
    -   ✈️ **Flights** (Google Flights)
    -   🚂 **Trains** (IRCTC & Live Status)
    -   🚌 **Buses** (RedBus)
-   **Rich, Modern UI**:
    -   **Glassmorphic Design**: Clean, modern interface with blurred backgrounds and vibrant gradients.
    -   **Rich Text Support**: Full Markdown rendering (Bold, Lists, Links) using a local `marked.js` instance.
    -   **Responsive**: Optimized for mapped and mobile views.
-   **Privacy First**: Runs locally on your machine. Your travel plans stay with you.

## 🛠️ Tech Stack

-   **Backend**: Python 3.12+, FastAPI, MCP (Model Context Protocol).
-   **Frontend**: Vanilla JavaScript, HTML5, CSS3 (Glassmorphism), Marked.js.
-   **AI Model**: Claude 3 Haiku (via Anthropic API).
-   **Search & Data**: Google Custom Search JSON API, Amadeus API (optional).
-   **Social Insights**: 'SocialTravelInsights' MCP server for extracting travel advice from web sources.

## 🚀 Setup & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Rontor3/RoamMate.git
cd RoamMate
```

### 2. Set Up Environment Variables
Create a `.env` file in the root directory:
```env
ANTHROPIC_API_KEY=your_anthropic_key
GOOGLE_API_KEY=your_google_api_key
GOOGLE_SEARCH_ENGINE_ID=your_search_engine_id
AMADEUS_CLIENT_ID=your_amadeus_id  # Optional
AMADEUS_CLIENT_SECRET=your_amadeus_secret # Optional
AWIN_PUBLISHER_ID=your_affiliate_id # Optional (for Booking.com)
```

### 3. Install Dependencies
Using `pip` or `uv`:
```bash
pip install -r requirements.txt
# OR
uv sync
```

### 4. Run the Application

#### Option A: Local Run
```bash
uv run python app/main.py
# OR
python app/main.py
```

#### Option B: Docker (Recommended)
This is the easiest way to run the app with all dependencies pre-configured.

**1. Using Docker Compose (Fastest)**
```bash
# Build and start in background
docker compose up -d --build
```

**2. Manual Build & Run**
```bash
# Build the image
docker build -t roammate .

# Run the container (injecting .env)
docker run -p 8080:8080 --env-file .env roammate
```

**3. Useful Commands**
- **View Logs**: `docker compose logs -f`
- **Stop App**: `docker compose down`
- **Check Status**: `docker ps`

> [!TIP]
> **Persistence**: Conversational history is stored in the `./conversations` folder. The Docker Compose setup automatically mounts this as a volume, so your history is preserved even if the container is deleted.

Visit **http://localhost:8080** to start planning!

## 📂 Project Structure

```
RoamMate/
├── main.py                  # 'SocialTravelInsights' MCP Server
├── app/
│   ├── main.py              # FastAPI Application & MCP Client
│   └── mcp_client.py        # LLM integration & System Prompt ("Voya")
├── tools/
│   ├── hotel_flight_details.py # 'HotelFlightBooking' MCP Server
│   └── social_media.py      # Social media scraping logic
├── static/                  # Frontend Assets
│   ├── index.html           # Main UI
│   ├── style.css            # Glassmorphic Styling
│   ├── script.js            # Chat Logic & Markdown Parsing
│   └── marked.min.js        # Local Markdown Library
├── conversations/           # JSON logs of chat history
├── .env                     # Secrets (GitIgnored)
└── README.md                # Documentation
```

## 🧠 How It Works

1.  **User Query**: "I want a luxury weekend in Varkala."
2.  **Intent Parsing**: The AI identifies the origin (via IP) and destination.
3.  **Live Search**: Queries Google for the latest "Best luxury hotels in Varkala 2025".
4.  **Synthesis**: The AI parses the search results, extracts top options, and formats them into a narrative.
5.  **Response**: You get a friendly message with embedded, clickable links: *"Check out the [Gateway Varkala](url) for amazing cliff views."*

## 🤝 Contributing

Contributions are welcome! Please fork the repository and submit a pull request.

## 📄 License

MIT License
