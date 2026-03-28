from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
import json
import logging
import os
import asyncio

from app.models import TravelIntent, Place, PlaceAreaMapping, ResolvedArea
from app.services.input.intent_extractor import IntentExtractor
from app.services.scoring.scoring_engine import ScoringEngine
from app.services.scoring.ranker import Ranker

logger = logging.getLogger(__name__)

# Initialize Groq LLM for generic text (e.g. Node 5)
llm = ChatGroq(
    model="llama3-70b-8192",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY", "dummy_key_for_testing"),
)

# Initialize Services
intent_extractor = IntentExtractor()
scoring_engine_service = ScoringEngine()
ranker = Ranker()

# Define the State for the LangGraph
class GraphState(TypedDict):
    """
    Represents the state of the recommendation workflow.
    """
    query: str
    messages: List[Dict[str, Any]]
    extracted_info: Dict[str, Any]
    missing_info: bool
    raw_signals: Dict[str, Any]
    places: List[Dict[str, Any]]
    scores: Dict[str, Any]
    final_recommendation: str

# Node 1: Query Parser (Extracts Info using LLM)
async def query_parser(state: GraphState) -> GraphState:
    logger.info("Executing Node 1: Query Parser using IntentExtractor")
    query = state.get("query", "")
    if not query and state.get("messages"):
        query = state["messages"][-1].get("content", "")
    
    try:
        intent = await intent_extractor.extract(query)
        dest_city = intent.destination.city or ""
        dest_country = intent.destination.country or ""
        dest_val = f"{dest_city} {dest_country}".strip()
        
        state["extracted_info"] = {
            "destination": dest_val if dest_val else None,
            "needs_flight": intent.needs_flight,
            "needs_hotel": intent.needs_hotel,
            "intent_obj": intent  # Store raw intent object for ranker
        }
        
        # Validation checks for missing info
        validation = intent_extractor.validate(intent)
        state["missing_info"] = not validation["valid"]
        
        if state["missing_info"]:
            prompts = intent_extractor.get_clarification_prompts(intent)
            if prompts:
                state["extracted_info"]["clarifying_question"] = prompts[0]
                
    except Exception as e:
        logger.error(f"Error in query_parser: {e}")
        state["missing_info"] = False
        state["extracted_info"] = {"destination": None, "needs_flight": False, "needs_hotel": False}
        
    return state

# Conditional Edge after Node 1
def should_continue(state: GraphState) -> str:
    if state.get("missing_info", False):
        return "ask_clarifying_question"
    return "resilience_router"

# Flow nodes
def ask_clarifying_question(state: GraphState) -> GraphState:
    logger.info("Executing: Ask Clarifying Question")
    state["messages"].append({
        "role": "assistant",
        "content": "I need some more information. Could you specify your destination?"
    })
    return state

def resilience_router(state: GraphState) -> GraphState:
    logger.info("Executing: Resilience Router")
    # Stub: check Redis cache
    return state

def background_task_prefetch(state: GraphState) -> GraphState:
    logger.info("Executing Background Task: Pre-fetch Location")
    # Stub: Redis Tier 1 & 2
    return state

# Node 2: Data Ingestion (Parallel Tool Execution)
async def fetch_route_a(destination: str) -> Dict[str, Any]:
    # Route A (In-Destination): Tavily, OpenWeatherMap, Google Maps Places
    logger.info(f"Fetching Route A data for {destination}...")
    await asyncio.sleep(0.5) # Simulate API call latency
    return {"weather": "Sunny", "reddit_signals": f"Cool places in {destination}"}

async def fetch_route_b(destination: str) -> Dict[str, Any]:
    # Route B (Pre-Trip): Google Maps geocoding, Hotel/Flight Booking
    logger.info(f"Fetching Route B data for {destination}...")
    await asyncio.sleep(0.5)
    return {"flights": [{"price": 400}], "hotels": [{"name": "Grand Hotel", "price": 120, "rating": 4.5}]}

async def data_ingestion(state: GraphState) -> GraphState:
    logger.info("Executing Node 2: Data Ingestion")
    extracted = state.get("extracted_info", {})
    dest = extracted.get("destination", "Unknown")
    
    # Execute Parallel Tool Executions
    route_a_task = fetch_route_a(dest)
    route_b_task = fetch_route_b(dest)
    
    results = await asyncio.gather(route_a_task, route_b_task)
    
    state["raw_signals"] = {
        "route_a": results[0],
        "route_b": results[1]
    }
    return state

class ExtractedSignal(BaseModel):
    places: List[Dict[str, Any]] = Field(description="List of places with their context from reddit and search")
    hotels: List[Dict[str, Any]] = Field(description="Filtered hotels from raw signals")

# Node 3: Signal Extraction
def signal_extraction(state: GraphState) -> GraphState:
    logger.info("Executing Node 3: Signal Extraction")
    
    # 1. Use Groq to extract JSON
    raw_signals = str(state.get("raw_signals", {}))
    structured_llm = llm.with_structured_output(ExtractedSignal)
    prompt = (
        "You are an AI that extracts signals from raw data. "
        "Extract the places and hotels mentioned in the data. "
        f"Data: {raw_signals}"
    )
    
    try:
        result = structured_llm.invoke(prompt)
        places = result.places
        hotels = result.hotels
        
        # 2. Heuristic Filter (Drop < 4.2 stars)
        filtered_hotels = [h for h in hotels if h.get("rating", 0.0) >= 4.2]
        
        state["places"] = places + filtered_hotels
    except Exception as e:
        logger.error(f"Error in signal_extraction: {e}")
        state["places"] = []
    
    return state

# Node 4: Scoring Engine
def scoring_engine(state: GraphState) -> GraphState:
    logger.info("Executing Node 4: Scoring Engine using services")
    places = state.get("places", [])
    raw_signals = state.get("raw_signals", {})
    reddit_text = raw_signals.get("route_a", {}).get("reddit_signals")
    
    intent_data = state.get("extracted_info", {}).get("intent_obj")
    intent = intent_data if isinstance(intent_data, TravelIntent) else TravelIntent()
    
    # Generate AreaScores
    area_scores = scoring_engine_service.score_area(reddit_text=reddit_text)
    
    # Map raw places to PlaceAreaMapping
    mappings = []
    for p in places:
        try:
            place_obj = Place(
                place_id=p.get('place_id', p.get('name', 'unknown')),
                name=p.get('name', 'Unknown Place'),
                place_type=p.get('type', 'point_of_interest'),
                lat=p.get('lat', 0.0),
                lon=p.get('lon', 0.0),
                rating=p.get('rating'),
                review_count=p.get('review_count', 0),
                price_level=p.get('price_level'),
                tags=p.get('tags', [])
            )
            mapping = PlaceAreaMapping(place=place_obj)
            mappings.append(mapping)
        except Exception as e:
            logger.warning(f"Failed to map place {p}: {e}")
            
    if not mappings:
        state["scores"] = {"places_scored": 0}
        return state

    # Rank
    try:
        ranked_places = ranker.rank_places(mappings, intent, area_scores)
        
        # Format back to dict for state
        scored_places = []
        for rp in ranked_places:
            scored_places.append({
                "name": rp.place.name,
                "rating": rp.place.rating,
                "final_score": rp.rank_score,
                "explanation": rp.explanation.top_factor if rp.explanation else ""
            })
            
        state["places"] = scored_places
        state["scores"] = {"places_scored": len(scored_places)}
    except Exception as e:
        logger.error(f"Error ranking places: {e}")
        state["scores"] = {"places_scored": 0}
        
    return state

# Node 5: Recommendation Service
def recommendation_service(state: GraphState) -> GraphState:
    logger.info("Executing Node 5: Recommendation Service")
    # Stub: Groq Llama 3 generating final response & link injection
    state["final_recommendation"] = "This is a stub recommendation."
    state["messages"].append({"role": "assistant", "content": state["final_recommendation"]})
    return state

# Build the LangGraph
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("query_parser", query_parser)
workflow.add_node("ask_clarifying_question", ask_clarifying_question)
workflow.add_node("resilience_router", resilience_router)
workflow.add_node("background_task_prefetch", background_task_prefetch)
workflow.add_node("data_ingestion", data_ingestion)
workflow.add_node("signal_extraction", signal_extraction)
workflow.add_node("scoring_engine", scoring_engine)
workflow.add_node("recommendation_service", recommendation_service)

# Add edges
workflow.add_edge(START, "query_parser")

# Conditional Edge out of Query Parser
workflow.add_conditional_edges(
    "query_parser",
    should_continue,
    {
        "ask_clarifying_question": "ask_clarifying_question",
        "resilience_router": "resilience_router"
    }
)

workflow.add_edge("ask_clarifying_question", END)

# Parallel branch from resilience router (simplified as sequence for now, but background_task can run async or as a parallel branch)
workflow.add_edge("resilience_router", "background_task_prefetch")
workflow.add_edge("background_task_prefetch", "data_ingestion")
workflow.add_edge("data_ingestion", "signal_extraction")
workflow.add_edge("signal_extraction", "scoring_engine")
workflow.add_edge("scoring_engine", "recommendation_service")
workflow.add_edge("recommendation_service", END)

# Compile
app_graph = workflow.compile()
