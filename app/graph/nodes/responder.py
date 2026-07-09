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
from app.services.stage_machine import resolve_stage, determine_action as _stage_determine_action
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

    # Detect if destination is a region/state vs a specific city — driven purely by intent extractor
    is_region = bool(intent and intent.destination.region and not intent.destination.city)

    # ── Origin known, no destination yet ────────────────────────────────────────
    # "Weekend trip from Mumbai" — suggest where to go rather than asking a blank question
    origin_city = intent.origin_city if intent else None
    has_real_dest = bool(intent and (intent.destination.city or intent.destination.region))
    if origin_city and not has_real_dest and phase == Phase.DISCOVERY:
        duration_str = intent.duration.value if (intent and intent.duration) else "weekend"
        task = (
            f"The user wants a {duration_str} trip departing from {origin_city} but hasn't named a destination yet. "
            f"Sound like an excited local friend who knows great escapes from {origin_city}. "
            f"Suggest exactly 3-4 specific destinations. For each use this format:\n"
            f"**[Destination]** — [travel time/distance from {origin_city}] · [one punchy sentence: what makes it special and who it suits]\n"
            f"{vibe_str} {interests_str}\n"
            f"After the list, ask ONE casual question: which of these sounds good, or do they have a different vibe in mind? "
            f"Keep the whole response under 200 words. Be warm and specific — no generic tourist blurb."
        )
        system = (
            "You are RoamMate, a knowledgeable and warm travel companion. "
            "You give sharp, specific, and opinionated travel advice — not generic overviews. "
            "Use markdown bold for destination names. Be concise and friendly.\n\n"
            f"CURRENT TASK: {task}\n\n"
            f"{weather_str}"
        ).strip()
        return system

    if phase == Phase.DISCOVERY:
        if assistant_turns == 0:
            if is_region:
                # Region/state — orient the user around cities/areas first
                task = (
                    f"The user wants to visit {dest}, which covers multiple cities and areas. "
                    f"Respond like an excited friend who knows {dest} deeply. "
                    f"Structure your reply into exactly 3 SHORT sections using markdown bold headers:\n"
                    f"**🗺️ Where to Go** – List 4-5 distinct cities or areas in {dest}, one line each. "
                    f"For EACH, say what it's best known for and who it suits (e.g. 'Jaipur – forts, palaces, best for history lovers'). "
                    f"Do NOT list specific monuments or restaurants yet.\n"
                    f"**🍜 Regional Food to Try** – 3-4 dishes unique to {dest}, one line each.\n"
                    f"**📅 Best Time to Visit** – one short paragraph on seasons and timing.\n"
                    f"End with ONE question asking which city/area interests them most or what vibe they're after. "
                    f"Keep the whole response under 220 words. Be specific and opinionated."
                )
            else:
                # Specific city — dive into spots, food, timing
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
            latest_msg = ""
            for m in reversed(state.get("messages", [])):
                role = m.get("role") if isinstance(m, dict) else getattr(m, "type", "")
                if role in ("human", "user"):
                    latest_msg = (m.get("content") if isinstance(m, dict) else getattr(m, "content", "")).lower()
                    break

            # If they've now named a specific city within the region, zoom in
            city = intent.destination.city if intent else None
            if is_region and city:
                task = (
                    f"The user was exploring {dest} and has now focused on {city}. "
                    f"Respond like a local expert on {city} specifically. "
                    f"Use markdown headers (##) and bullet points. Cover: best neighbourhoods/areas to stay, "
                    f"top spots that match their vibe ({vibe_str}), must-try local food specific to {city}. "
                    f"DO NOT repeat the region overview. Keep under 250 words."
                )
            else:
                needs_structure = any(kw in latest_msg for kw in [
                    "itinerar", "plan", "schedule", "day", "week", "stay", "hotel", "hostel",
                    "resort", "airbnb", "hidden gem", "local", "vendor", "how should", "how do"
                ])
                if needs_structure:
                    task = (
                        f"You are having an ongoing conversation about visiting {dest}. "
                        f"The user just asked: respond DIRECTLY and use clear markdown headers (##) and bullet points. "
                        f"DO NOT repeat anything already covered. {vibe_str} {interests_str} "
                        f"Be specific — name actual places, dishes, homestays. Keep it under 300 words."
                    )
                else:
                    task = (
                        f"You are having an ongoing conversation about visiting {dest}. "
                        f"Respond DIRECTLY to the user's latest message in a warm, conversational tone. "
                        f"DO NOT repeat the Must-See Spots / Food / Best Time intro. "
                        f"{vibe_str} {interests_str} "
                        f"Keep it under 120 words. End with ONE short follow-up if appropriate."
                    )
    elif phase == Phase.PLANNING:
        hotel_data = state.get("hotel_data") or []
        intent = state.get("travel_intent")
        acc_type = (intent.accommodation_type or "stay") if intent else "stay"
        budget_str = (f" Budget: {intent.budget.value}." if intent and intent.budget else "") if intent else ""

        hotel_section = ""
        if hotel_data:
            exceptional = [h for h in hotel_data if h.get("exceptional")]
            regular = [h for h in hotel_data if not h.get("exceptional")]

            def _fmt(h):
                name = h.get("name", "")
                url = h.get("url", "")
                score = h.get("review_score")
                price = h.get("price_inr")
                acc = h.get("accommodation_type", "")
                cancel = " ✅ Free cancellation" if h.get("free_cancellation") else ""
                urgency = f" ⚡ {h['urgency']}" if h.get("urgency") else ""
                highlights = h.get("highlights") or []
                highlight_str = f" · {', '.join(str(x) for x in highlights[:3])}" if highlights else ""
                description = h.get("description", "")
                desc_str = f' — "{description}"' if description else ""
                room = h.get("room_type", "")
                room_str = f" ({room})" if room else ""
                meta = " | ".join(filter(None, [
                    f"⭐ {score}/10" if score else None,
                    f"₹{price:,}/stay" if price else None,
                    acc,
                    f"{h.get('review_count')} reviews" if h.get("review_count") else None,
                ]))
                line = f"**{name}**"
                return f"- {line}{room_str} — {meta}{cancel}{urgency}{highlight_str}{desc_str}"

            hotel_lines = [_fmt(h) for h in regular[:4]]
            exceptional_lines = [_fmt(h) for h in exceptional[:2]]

            hotel_section = (
                f"\n\nHOTEL DATA (type:{acc_type},{budget_str}):\n"
                f"Available picks (real Booking.com availability + INR prices):\n"
                + "\n".join(hotel_lines)
            )
            if exceptional_lines:
                hotel_section += "\n💎 Exceptional/unique stays:\n" + "\n".join(exceptional_lines)

        task = (
            f"Create a structured travel plan for {dest}. {vibe_str} {interests_str}\n"
            f"Use clear markdown headers (##) and subheaders (###) for each section.\n"
            f"Structure your response with these sections (use only what's relevant):\n"
            f"## 🗺️ Overview — 2 sentences on what makes {dest} special for this trip.\n"
            f"## 📍 Top Places to Visit — bullet list, one line per place with why it fits their vibe.\n"
            f"## 🍽️ Where to Eat & Drink — 3-4 specific local spots or dishes, not generic advice.\n"
            f"## 🏨 Where to Stay — for each hotel in the data below, write 1-2 sentences explaining "
            f"specifically why it suits the user's vibe ({vibe_str}) and budget ({budget_str}). "
            f"Reference its highlights, description, and review score — not just name and price. "
            f"Call out any exceptional/unique stays separately under ### 💎 Hidden Gem Stays.\n"
            f"## 🚗 Getting Around — practical transport tips.\n"
            f"## 💡 Local Tips — 2-3 things most tourists don't know.\n"
            f"Keep each section tight — max 4 bullet points or 3 sentences. Total under 450 words."
            f"{hotel_section}"
        )
    else:
        # IN_DESTINATION phase
        origin = intent.origin_city if intent else None
        duration_str = intent.duration.value if (intent and intent.duration) else "weekend"
        if origin:
            # User is based in origin and wants nearby trip suggestions
            task = (
                f"The user is based in {origin} and is looking for a {duration_str} getaway nearby. "
                f"Recommend 4-5 specific destinations reachable within a few hours from {origin}. "
                f"For each destination, give: distance/travel time from {origin}, one-line highlight of why it's worth visiting, "
                f"and who it suits best. {vibe_str} {interests_str}\n"
                f"Use markdown bold for destination names. Keep it under 220 words. "
                f"End with ONE question asking if any of these sound interesting or if they want more details on one."
            )
        else:
            task = (
                f"The user is currently in or near {dest}. Help them find great options right now. "
                f"Sound like a local friend. {vibe_str} {interests_str} Keep under 180 words."
            )

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

    stage = resolve_stage(state)
    action, payload = await _stage_determine_action(stage, state)
    events.append(f"[action] {action or 'none'} stage={stage}")

    # Update one-time flags when their card is sent — prevents re-sending same card next turn
    places_shown = state.get("places_shown", False) or action == "show_place_cards"
    pace_shown = state.get("pace_shown", False) or action == "show_pace_options"
    routes_shown = state.get("routes_shown", False) or action == "show_route_arcs"

    return {
        "response": response_text,
        "messages": [{"role": "assistant", "content": response_text}],
        "tool_events": events,
        "action": action,
        "payload": payload,
        "conversation_stage": stage,
        "places_shown": places_shown,
        "pace_shown": pace_shown,
        "routes_shown": routes_shown,
        "show_scene_strip": state.get("show_scene_strip", False),
        "skip_graph": False,
        "destination_candidates": state.get("destination_candidates") or {},
    }
