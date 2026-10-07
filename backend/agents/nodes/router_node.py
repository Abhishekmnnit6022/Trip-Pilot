"""
Router agent node — parses user message, extracts travel info,
and decides the next pipeline step.
"""

import json
import logging
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.state import TravelState
from backend.agents.nodes.utils import extract_text, clean_llm_json
from backend.llm_factory import get_llm, get_active_llm_info

log = logging.getLogger(__name__)
llm = get_llm()

# ─────────────────────────────────────────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """You are a travel-planning concierge. Analyze the FULL conversation and the
latest user message to extract travel details and decide the next action.

Current known state:
- Origin:              {origin}
- Destination:         {destination}
- Start date:          {start_date}
- End date:            {end_date}
- Num days:            {num_days}
- Budget:              {budget}
- Transport pref:      {transport_preference}
- Train tier:          {train_tier}
- Has transport booked:{has_transport}
- Booking status:      {booking_status}
- Has hotel booked:    {has_hotel}
- Has itinerary:       {has_itinerary}

Rules (follow IN ORDER):
1. Extract any NEW info from the latest message (city names, dates, preferences).
2. For dates like "next Monday" or "tomorrow", compute actual date relative to today ({today}).
3. If destination is missing -> ask for it. action = "ask_user"
4. If origin is missing -> ask where they are traveling from. action = "ask_user"
5. If dates are missing -> ask when they want to travel. action = "ask_user"
6. If origin + destination + dates are known BUT transport_preference is empty -> ask:
   "Would you like to travel by Train or Flight?" action = "ask_user"
7. If transport_preference = "train" AND train_tier is empty -> ask:
   "Which class? 1A (First AC), 2A (Second AC), 3A (Third AC), SL (Sleeper), CC (Chair Car)?"
   action = "ask_user"
8. If transport_preference = "train" AND train_tier known AND no transport booked -> action = "auto_book_train"
9. If transport_preference = "flight" AND no transport booked -> action = "auto_book_flight"
10. If booking_status = "waiting" and user wants alternative transport -> action = "offer_alternate"
11. If booking_status = "waiting" and user declines alternate -> action = "ask_hotel"
12. If transport IS booked AND no hotel booked -> ask about hotel. action = "ask_hotel"
13. If user says YES to hotel (or provides preferences/budget) -> action = "auto_book_hotel"
14. If user says NO to hotel -> action = "generate_itinerary"
15. If hotel IS booked AND no itinerary yet -> action = "generate_itinerary"
16. If user wants return tickets -> action = "search_return"
17. If itinerary exists and user asks to regenerate -> action = "generate_itinerary"
18. CRITICAL: If user says "train" or "flight", extract into transport_preference.
19. CRITICAL: If user mentions a class/tier, extract into train_tier.
    Map: sleeper->SL, first AC->1A, second AC->2A, third AC->3A, chair car->CC.
20. CRITICAL: If message says "Payment completed successfully", set paid_transport or
    paid_hotel to true and move to the next phase.
21. For general questions / chit-chat -> action = "respond"

OUTPUT FORMAT: RETURN ONLY VALID JSON. NO prose, NO markdown, NO explanation.
Your ENTIRE response must be a single JSON object starting with {{ and ending with }}.
The "response" field carries your user-facing message.

{{
  "origin": "<city or null>",
  "destination": "<city or null>",
  "start_date": "<YYYY-MM-DD or null>",
  "end_date": "<YYYY-MM-DD or null>",
  "num_days": <int or null>,
  "budget": "<string or null>",
  "transport_preference": "<train|flight or null>",
  "train_tier": "<1A|2A|3A|SL|CC or null>",
  "paid_transport": <true or false>,
  "paid_hotel": <true or false>,
  "action": "<ask_user|auto_book_train|auto_book_flight|ask_hotel|auto_book_hotel|generate_itinerary|search_return|offer_alternate|respond>",
  "response": "<your natural-language reply to the user>"
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Node function
# ─────────────────────────────────────────────────────────────────────────────

def router_agent(state: TravelState) -> dict:
    """Analyze conversation and decide the next pipeline step."""
    origin = state.get("origin", "") or ""
    destination = state.get("destination", "") or ""
    start_date = state.get("start_date", "") or ""
    end_date = state.get("end_date", "") or ""
    num_days = state.get("num_days", 0) or 0
    budget = state.get("budget", "") or ""
    transport_preference = state.get("transport_preference", "") or ""
    train_tier = state.get("train_tier", "") or ""
    auto_booked_transport = state.get("auto_booked_transport", "") or ""
    auto_booked_hotel = state.get("auto_booked_hotel", "") or ""
    booking_status = state.get("booking_status", "") or ""
    itinerary = state.get("itinerary", "") or ""

    system_prompt = _ROUTER_SYSTEM.format(
        origin=origin or "unknown",
        destination=destination or "unknown",
        start_date=start_date or "unknown",
        end_date=end_date or "unknown",
        num_days=num_days or "unknown",
        budget=budget or "unknown",
        transport_preference=transport_preference or "not chosen yet",
        train_tier=train_tier or "not chosen yet",
        has_transport=bool(auto_booked_transport),
        booking_status=booking_status or "none",
        has_hotel=bool(auto_booked_hotel),
        has_itinerary=bool(itinerary),
        today=datetime.now().strftime("%Y-%m-%d"),
    )

    messages_for_llm = [SystemMessage(content=system_prompt)]
    recent = state.get("messages", [])[-6:]
    messages_for_llm.extend(recent)
    messages_for_llm.append(
        HumanMessage(content=(
            "[INSTRUCTION] Your response MUST be a single valid JSON object only. "
            "Start with { and end with }. Do NOT write any prose, greeting, or explanation "
            "outside the JSON. Put your user-facing message inside the \"response\" field."
        ))
    )

    try:
        json_llm = llm.bind(response_format={"type": "json_object"})
        response = json_llm.invoke(messages_for_llm)
    except Exception:
        response = llm.invoke(messages_for_llm)

    active_llm = get_active_llm_info()
    llm_calls = state.get("llm_calls", 0) + 1
    log.info("[ROUTER] LLM responding: %s", active_llm)

    try:
        content_str = clean_llm_json(extract_text(response.content))
        parsed = json.loads(content_str)
        log.info(
            "[ROUTER] action=%s origin=%s dest=%s transport=%s",
            parsed.get("action"), parsed.get("origin"),
            parsed.get("destination"), parsed.get("transport_preference"),
        )
    except json.JSONDecodeError:
        raw_text = extract_text(response.content)
        log.warning("[ROUTER] LLM did not return valid JSON — inferring from state. Raw: %s", raw_text[:300])

        if transport_preference == "train" and train_tier and origin and destination and start_date:
            log.info("[ROUTER] Inferred action=auto_book_train from state (no JSON)")
            return {
                "messages": [AIMessage(content=raw_text.strip() or f"Searching {train_tier} trains from {origin} to {destination}...")],
                "phase": "auto_book_train",
                "needs_input": "",
                "llm_calls": llm_calls,
            }

        tier_map = {
            "1a": "1A", "2a": "2A", "3a": "3A", "sl": "SL", "cc": "CC",
            "sleeper": "SL", "first ac": "1A", "second ac": "2A", "third ac": "3A",
        }
        for keyword, tier_val in tier_map.items():
            last_msg_text = (
                extract_text(state["messages"][-1].content).lower()
                if state.get("messages") else ""
            )
            if keyword in raw_text.lower() or keyword in last_msg_text:
                if transport_preference == "train" and origin and destination and start_date:
                    log.info("[ROUTER] Inferred train_tier=%s from keyword", tier_val)
                    return {
                        "messages": [AIMessage(content=raw_text.strip() or f"Searching {tier_val} trains...")],
                        "phase": "auto_book_train",
                        "train_tier": tier_val,
                        "needs_input": "",
                        "llm_calls": llm_calls,
                    }

        return {
            "messages": [AIMessage(content=raw_text)],
            "phase": "respond",
            "needs_input": "",
            "llm_calls": llm_calls,
        }

    updates: dict = {"llm_calls": llm_calls}

    if parsed.get("origin"):
        updates["origin"] = parsed["origin"]
    if parsed.get("destination"):
        updates["destination"] = parsed["destination"]
    if parsed.get("start_date"):
        updates["start_date"] = parsed["start_date"]
    if parsed.get("end_date"):
        updates["end_date"] = parsed["end_date"]
    if parsed.get("num_days"):
        updates["num_days"] = parsed["num_days"]
        if (updates.get("start_date") or start_date) and not parsed.get("end_date"):
            try:
                sd = datetime.strptime(updates.get("start_date", start_date), "%Y-%m-%d")
                updates["end_date"] = (sd + timedelta(days=parsed["num_days"] - 1)).strftime("%Y-%m-%d")
            except ValueError:
                pass
    if parsed.get("budget"):
        updates["budget"] = parsed["budget"]
    if parsed.get("transport_preference"):
        updates["transport_preference"] = parsed["transport_preference"]
    if parsed.get("train_tier"):
        updates["train_tier"] = parsed["train_tier"]
    if parsed.get("paid_transport"):
        updates["auto_booked_transport"] = "paid"
    if parsed.get("paid_hotel"):
        updates["auto_booked_hotel"] = "paid"

    action = parsed.get("action", "respond")
    reply = parsed.get("response", "I can help you plan your trip!")

    updates["phase"] = action
    updates["needs_input"] = "yes" if action in ("ask_user", "ask_hotel") else ""
    updates["messages"] = [AIMessage(content=reply)]

    return updates
