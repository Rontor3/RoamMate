"""
app/api/server.py — FastAPI application.
/chat endpoint: injects GPS location into GraphState, invokes LangGraph.
/reverse-geocode endpoint: server-side Google Maps call (keeps API key private).
"""
import os
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
from dotenv import load_dotenv

load_dotenv()

logger = get_logger(__name__)
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the graph on startup with a persistent checkpointer."""
    logger.info("Starting RoamMate server...")
    compiled, checkpointer = await build_graph()
    app.state.graph = compiled
    app.state.checkpointer = checkpointer
    app.state.thread_id = "conversation_" + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"LangGraph compiled and ready | session thread_id={app.state.thread_id}")
    yield
    logger.info("Server shutting down")


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
        
        # Don't pass thread_id inside state_input, it confuses Pregel
        if request.location:
            state_input["current_location"] = request.location.model_dump()
            
        final_state = await graph.ainvoke(state_input, config=config)

        response_text = final_state.get("response", "I'm not sure how to help with that. Could you rephrase?")
        messages = final_state.get("messages", [])
        tool_events = final_state.get("tool_events", [])

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

        return ChatResponse(
            response=response_text,
            thread_id=request.thread_id,
            phase=str(final_state.get("phase", "unknown")),
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
