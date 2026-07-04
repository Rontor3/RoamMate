"""
app/api/server.py — FastAPI application.
/chat endpoint: injects GPS location into GraphState, invokes LangGraph.
/reverse-geocode endpoint: server-side Google Maps call (keeps API key private).
"""
import asyncio
import os
import re
import subprocess
import sys
from datetime import datetime
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.schemas import ChatRequest, ChatResponse, ReverseGeocodeRequest
from app.graph.builder import build_graph
from app.utils.conversation_logger import save_conversation
from app.utils.logger import get_logger
from app.utils.place_photos import fetch_place_photos
from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_API_KEY", "")

_FACTOR_PHRASES = {
    "quality": "known for excellent quality and reviews",
    "intent_match": "matches your vibe perfectly",
    "authenticity": "a local favourite, not a tourist trap",
    "crowd_fit": "has the kind of crowd you prefer",
}


def _extract_bold_places(text: str) -> list[str]:
    """Extract **Bold Names** from markdown text — used for DISCOVERY phase photo fetching."""
    names = re.findall(r'\*\*([A-Z][^*]{2,49})\*\*', text)
    return list(dict.fromkeys(names))[:5]


def _build_frontend_places(ranked_places: list, place_photos: list) -> list:
    """Transform ranked_places into the shape expected by PlaceCard."""
    photo_by_name = {p["name"]: p["url"] for p in place_photos if isinstance(p, dict)}
    result = []
    for p in ranked_places[:6]:
        expl = p.get("explanation", {})
        why = _FACTOR_PHRASES.get(expl.get("top_factor", ""), "A great option for your trip")
        vibe_tags = [t.replace("_", " ").title() for t in p.get("tags", [])[:4]]
        # Prefer photo_url baked into the ranked place (from map_tools enrichment),
        # fall back to the post-graph place_photos lookup.
        photo_url = p.get("photo_url") or photo_by_name.get(p.get("name", ""))
        result.append({
            "id": p.get("name", ""),
            "name": p.get("name", ""),
            "photos": [photo_url] if photo_url else [],
            "vibeTags": vibe_tags,
            "distance": "",
            "whyPicked": why,
            "redditHighlights": p.get("review_highlights", []),
            "crowdLevel": "moderate",
            "openingHours": "",
        })
    return result


_MCP_SCRIPTS = [
    "tools/map_tools.py",
    "tools/weather_tools.py",
    "tools/social_media.py",
    "tools/hotel_flight_details.py",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the graph on startup with a persistent checkpointer."""
    logger.info("Starting RoamMate server...")

    # Kill any processes still holding MCP or frontend ports from a previous run
    _MCP_PORTS = [3001, 3002, 3003, 3004]
    for port in _MCP_PORTS:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True
            )
            pids = result.stdout.strip().split()
            for pid in pids:
                if pid:
                    subprocess.run(["kill", "-9", pid], capture_output=True)
                    logger.info(f"Killed stale process on port {port} (pid={pid})")
        except Exception as e:
            logger.warning(f"Could not clear port {port}: {e}")

    # Start MCP tool servers as subprocesses
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    procs = []
    for script in _MCP_SCRIPTS:
        path = os.path.join(root, script)
        proc = subprocess.Popen([sys.executable, path])
        procs.append(proc)
        logger.info(f"Started MCP server: {script} (pid={proc.pid})")

    # Frontend is now served as static/index.html at GET /
    logger.info("Serving new HTML frontend from static/index.html")

    await asyncio.sleep(2)  # give servers time to bind their ports

    compiled, checkpointer = await build_graph()
    app.state.graph = compiled
    app.state.checkpointer = checkpointer
    app.state.thread_id = "conversation_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"LangGraph compiled and ready | session thread_id={app.state.thread_id}")
    yield

    logger.info("Server shutting down — terminating all subprocesses")
    for proc in procs:
        proc.terminate()


app = FastAPI(title="RoamMate API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.isdir(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
async def root():
    index = os.path.join(static_path, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "RoamMate API v2 running"}


@app.get("/session")
async def session():
    """Returns the server-generated thread_id for this server session."""
    return {"thread_id": app.state.thread_id}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint — multi-turn via LangGraph thread checkpoints.

    Because GraphState.messages uses the add_messages reducer, we only
    ever pass the NEW user message each turn. LangGraph loads the existing
    checkpoint for the thread_id, appends the new message via the reducer,
    and runs the graph forward automatically.
    """
    config = {"configurable": {"thread_id": request.thread_id}}

    graph = app.state.graph
    user_message = {"role": "user", "content": request.message}

    try:
        # LangGraph automatically loads the matching thread checkpoint,
        # applies the add_messages reducer to our new user_message,
        # and starts execution from START to process the new turn.
        state_input: dict = {"messages": [user_message], "tool_events": []}

        # Phase 0 fields — only injected when present; checkpointer persists them across turns
        if request.trip_mode:
            state_input["trip_mode"] = request.trip_mode
        if request.trip_who:
            state_input["trip_who"] = request.trip_who
        if request.trip_season:
            state_input["trip_season"] = request.trip_season

        # Don't pass thread_id inside state_input, it confuses Pregel
        if request.location:
            state_input["current_location"] = request.location.model_dump()

        if request.card_action:
            state_input["card_action"] = request.card_action
            state_input["card_data"] = request.card_data or {}

        final_state = await graph.ainvoke(state_input, config=config)

        response_text = final_state.get("response", "I'm not sure how to help with that. Could you rephrase?")
        messages = final_state.get("messages", [])
        tool_events = final_state.get("tool_events", [])

        # Fetch place photos — ranked_places first, then bold-text extraction, then destination fallback
        photo_names: list[str] = []
        for p in (final_state.get("ranked_places") or [])[:5]:
            name = p.get("name") if isinstance(p, dict) else getattr(p, "name", None)
            if name:
                photo_names.append(name)
        if not photo_names and response_text:
            photo_names = _extract_bold_places(response_text)
        if not photo_names and final_state.get("destination"):
            photo_names = [final_state["destination"]]
        place_photos = await fetch_place_photos(photo_names, GOOGLE_MAPS_KEY) if photo_names else []

        # Attach tool_events to the last assistant message so they appear in the saved JSON
        if tool_events and messages:
            msgs_as_dicts = []
            for m in messages:
                if isinstance(m, dict):
                    msgs_as_dicts.append(m)
                else:
                    msgs_as_dicts.append({"role": getattr(m, "type", "user"), "content": getattr(m, "content", "")})
            # Find and annotate the last assistant message
            for i in reversed(range(len(msgs_as_dicts))):
                if msgs_as_dicts[i].get("role") in ("assistant", "ai"):
                    msgs_as_dicts[i]["tools_used"] = tool_events
                    break
            save_conversation(request.thread_id, msgs_as_dicts)
        else:
            save_conversation(request.thread_id, messages)

        hotel_data = final_state.get("hotel_data") or []
        if not isinstance(hotel_data, list):
            hotel_data = []
        frontend_places = _build_frontend_places(
            final_state.get("ranked_places") or [], place_photos
        )

        return ChatResponse(
            response=response_text,
            thread_id=request.thread_id,
            phase=str(final_state.get("phase", "unknown")),
            photos=place_photos,
            hotels=hotel_data,
            places=frontend_places,
            action=final_state.get("action"),
            payload=final_state.get("payload"),
        )
    except Exception as e:
        logger.exception(f"/chat error for thread {request.thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reverse-geocode")
async def reverse_geocode(request: ReverseGeocodeRequest):
    """Server-side reverse geocoding to keep GOOGLE_MAPS_KEY private."""
    if not GOOGLE_MAPS_KEY:
        raise HTTPException(status_code=503, detail="Google Maps key not configured")

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"latlng": f"{request.lat},{request.lng}", "key": GOOGLE_MAPS_KEY}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as r:
                data = await r.json()
                if data.get("results"):
                    label = data["results"][0].get("formatted_address", f"{request.lat},{request.lng}")
                    return {"label": label, "lat": request.lat, "lng": request.lng}
    except Exception as e:
        logger.error(f"/reverse-geocode error: {e}")

    return {"label": f"{request.lat:.4f},{request.lng:.4f}", "lat": request.lat, "lng": request.lng}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
