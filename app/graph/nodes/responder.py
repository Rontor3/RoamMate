"""
nodes/responder.py — Final response generator (Node 5).
Translates RankExplanation.top_factor to human phrases.
Calls Groq Llama 4 Scout with structured place context.
Never exposes raw scores to the LLM.
"""
import asyncio
import json
import os
from typing import List, Dict, Any

import aiohttp

from app.graph.state import GraphState, Phase
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Human-readable translations for RankExplanation.top_factor
FACTOR_PHRASES = {
    "quality": "known for excellent quality and reviews",
    "intent_match": "matches your vibe perfectly",
    "authenticity": "a local favourite, not a tourist trap",
    "crowd_fit": "has the kind of crowd you prefer",
}


def _build_place_context(ranked_places: List[Dict[str, Any]]) -> str:
    """Convert ranked places to a human-readable context string for the prompt."""
    if not ranked_places:
        return "No specific places found."
    lines = []
    for i, p in enumerate(ranked_places[:6], 1):
        expl = p.get("explanation", {})
        factor = expl.get("top_factor", "")
        phrase = FACTOR_PHRASES.get(factor, "a great option")
        rating_str = f"{p['rating']}/5" if p.get("rating") else "unrated"
        lines.append(f"{i}. **{p['name']}** ({rating_str}) — {phrase}.")
    return "\n".join(lines)


def _build_system_prompt(state: GraphState) -> str:
    """Build the system prompt based on phase and whether it's a first or follow-up turn."""
    dest = state.get("destination", "your destination")
    phase = state.get("phase", Phase.DISCOVERY)
    ranked = state.get("ranked_places") or state.get("nearby_results") or []
    blog = state.get("blog_signals", {})
    weather = state.get("weather_data", {})
    intent = state.get("travel_intent")
    messages = state.get("messages", [])

    # Count prior assistant turns to detect first-turn vs follow-up
    assistant_turns = sum(1 for m in messages if
        (m.get("role") if isinstance(m, dict) else getattr(m, "type", "")) in ("assistant", "ai"))

    place_ctx = _build_place_context(ranked)
    blog_answer = blog.get("top_answer", "")[:400]

    weather_str = ""
    if weather:
        temp = weather.get("temperature") or weather.get("temp", "")
        desc = weather.get("description") or weather.get("weather", "")
        if temp or desc:
            weather_str = f"Current weather in {dest}: {desc} {temp}°C."

    vibe_str = ""
    if intent and intent.vibe:
        vibe_str = f"User vibe: {', '.join(v.value for v in intent.vibe)}."

    interests_str = ""
    if intent and intent.interests:
        interests_str = f"User interests: {', '.join(intent.interests)}."

    if phase == Phase.DISCOVERY:
        if assistant_turns == 0:
            # First time hearing about this destination — give the intro overview
            task = (
                f"The user just told you they want to visit {dest}. Respond like an excited, knowledgeable friend. "
                f"Structure your reply into exactly 3 SHORT sections using markdown bold headers:\n"
                f"**📍 Must-See Spots** – 3-4 iconic or off-beat places, one sentence each.\n"
                f"**🍜 Local Food & Drinks** – 3-4 must-try dishes or drinks.\n"
                f"**📅 Best Time to Go** – one short paragraph on timing and seasons.\n"
                f"End with ONE short follow-up question about their vibe (e.g. adventure/culture/relaxation). "
                f"Keep the whole response under 200 words. Be warm and specific."
            )
        else:
            # Follow-up turn — continue the conversation, don't repeat the intro
            task = (
                f"You are having an ongoing conversation with the user about visiting {dest}. "
                f"The conversation history above contains what you've already discussed. "
                f"DO NOT repeat the Must-See Spots / Food / Best Time template you already gave. "
                f"Instead, respond DIRECTLY to the user's latest message — answer their specific question, "
                f"narrow down recommendations based on what they told you, or dive deeper into their interests. "
                f"{vibe_str} {interests_str} "
                f"Keep it conversational, warm, and under 150 words. End with ONE short follow-up if appropriate."
            )
    elif phase == Phase.PLANNING:
        task = (
            f"Recommend the best places in {dest} based on the user's preferences and the ranked list below. "
            f"{vibe_str} {interests_str} Weave recommendations naturally into 2-3 short paragraphs."
        )
    else:
        task = f"Help the user find great nearby options right now in {dest}. Sound like a local friend."

    system = (
        "You are RoamMate, a knowledgeable and warm travel companion. "
        "You give sharp, specific, and opinionated travel advice — not generic overviews. "
        "You remember the full conversation and NEVER repeat information you've already given. "
        "Use markdown bold for place and food names. Be concise and friendly.\n\n"
        f"CURRENT TASK: {task}\n\n"
        f"{weather_str}\n"
        f"Top places data:\n{place_ctx}\n"
        f"Editorial context: {blog_answer}"
    ).strip()

    return system


async def responder(state: GraphState) -> GraphState:
    """Generate the final response using Groq Llama 4 Scout."""
    system = _build_system_prompt(state)

    # Build conversation history for the LLM so it never repeats itself
    raw_messages = state.get("messages", [])
    history = []
    for m in raw_messages:
        if isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content", "")
        else:
            role = getattr(m, "type", "user")
            content = getattr(m, "content", "")
        if role in ("human", "user"):
            role = "user"
        elif role in ("ai", "assistant"):
            role = "assistant"
        else:
            continue  # skip tool/system messages
        if content:
            history.append({"role": role, "content": str(content)})

    dest = state.get("destination", "unknown")
    phase = state.get("phase", "unknown")
    logger.info(f"[Groq/responder] → phase={phase} dest={dest} history={len(history)} msgs")

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}] + history,
        "max_tokens": 1000,
        "temperature": 0.7,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                response_text = result["choices"][0]["message"]["content"]
                logger.info(f"[Groq/responder] ✓ {len(response_text)} chars generated")
    except Exception as e:
        logger.error(f"[Groq/responder] ✗ {e}")
        dest = state.get("destination", "your destination")
        response_text = f"I found some great options in {dest}! Let me know if you'd like more specific recommendations."

    logger.info("responder: response generated")
    events: list = state.get("tool_events") or []
    events.append(f"[Groq/responder] {len(response_text)} chars generated (phase={state.get('phase', 'unknown')})")   
    return {
        "response": response_text,
        "messages": [{"role": "assistant", "content": response_text}],
        "tool_events": events,
    }
