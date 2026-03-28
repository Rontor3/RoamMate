"""
app/graph/builder.py — Assembles the LangGraph state machine and compiles it.

IMPORTANT: Uses a persistent aiosqlite connection (NOT async-with context manager)
so the checkpointer stays alive for the entire server lifespan.
This is required for multi-turn conversations to work correctly.
"""
import os
import aiosqlite
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.graph.state import GraphState, Phase
from app.graph.nodes.intent import detect_intent, should_clarify, route_to_phase, clarify
from app.graph.nodes.discovery import discovery
from app.graph.nodes.planning import planning
from app.graph.nodes.in_destination import in_destination
from app.graph.nodes.quick_setup import quick_setup, ask_vibe, vibe_or_location
from app.graph.nodes.resolve_location import resolve_location, ask_for_location, location_resolved_or_ask
from app.graph.nodes.responder import responder
from app.utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = os.getenv("CHECKPOINT_DB", "conversations/checkpoints.db")


async def _noop(state: GraphState) -> GraphState:
    """No-op pass-through node used as a routing hub."""
    return state


async def build_graph():
    """
    Build and compile the LangGraph.
    Returns (compiled_graph, checkpointer).
    Uses a raw aiosqlite connection so the checkpointer stays alive
    for the entire server lifespan — essential for multi-turn conversations.
    """
    os.makedirs("conversations", exist_ok=True)

    # Persistent connection — do NOT use async-with (that would close it)
    conn = await aiosqlite.connect(DB_PATH)
    checkpointer = AsyncSqliteSaver(conn)
    await checkpointer.setup()

    workflow = StateGraph(GraphState)

    # ── Register nodes ─────────────────────────────────────────────────────────
    workflow.add_node("detect_intent", detect_intent)
    workflow.add_node("clarify", clarify)
    workflow.add_node("route_phase_fn", _noop)

    # Phase 1
    workflow.add_node("discovery", discovery)

    # Phase 2
    workflow.add_node("planning", planning)

    # Phase 3
    workflow.add_node("quick_setup", quick_setup)
    workflow.add_node("ask_vibe", ask_vibe)
    workflow.add_node("resolve_location", resolve_location)
    workflow.add_node("ask_for_location", ask_for_location)
    workflow.add_node("in_destination", in_destination)

    # Final response
    workflow.add_node("responder", responder)

    # ── Entry point ─────────────────────────────────────────────────────────────
    workflow.add_edge(START, "detect_intent")

    # ── After detect_intent: clarify or route ───────────────────────────────────
    workflow.add_conditional_edges(
        "detect_intent",
        should_clarify,
        {"clarify": "clarify", "route_phase": "route_phase_fn"},
    )
    workflow.add_conditional_edges(
        "route_phase_fn",
        route_to_phase,
        {
            "discovery": "discovery",
            "planning": "planning",
            "in_destination": "quick_setup",
        },
    )

    # ── Phase 1 → responder ─────────────────────────────────────────────────────
    workflow.add_edge("discovery", "responder")

    # ── Phase 2 → responder ─────────────────────────────────────────────────────
    workflow.add_edge("planning", "responder")

    # ── Phase 3 ─────────────────────────────────────────────────────────────────
    workflow.add_conditional_edges(
        "quick_setup",
        vibe_or_location,
        {"ask_vibe": "ask_vibe", "resolve_location": "resolve_location"},
    )
    workflow.add_edge("ask_vibe", END)

    workflow.add_conditional_edges(
        "resolve_location",
        location_resolved_or_ask,
        {"in_destination": "in_destination", "ask_for_location": "ask_for_location"},
    )
    workflow.add_edge("ask_for_location", END)
    workflow.add_edge("in_destination", "responder")

    # ── Terminal edges ─────────────────────────────────────────────────────────
    workflow.add_edge("clarify", END)
    workflow.add_edge("responder", END)

    # ── Compile ────────────────────────────────────────────────────────────────
    compiled = workflow.compile(checkpointer=checkpointer)
    logger.info(f"Graph compiled with AsyncSqliteSaver at {DB_PATH}")
    return compiled, checkpointer
