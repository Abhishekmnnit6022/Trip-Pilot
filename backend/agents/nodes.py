"""
Agent node functions for the LangGraph travel-planning pipeline.

Node summary
------------
router_agent        — parses user message, extracts info, decides next step
flight_agent        — searches flights via AviationStack
train_agent         — searches trains via Tavily + LLM
hotel_agent         — searches hotels via RapidAPI / Tavily
return_agent        — searches return transport
itinerary_agent     — generates day-by-day itinerary
present_results     — composes a friendly summary of search results
final_agent         — builds the complete trip plan
"""

import json
import logging
from datetime import datetime, timedelta

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.config import LLM_MODEL
from backend.agents.state import TravelState
from backend.tools.flight_tool import search_flights, format_flights_text
from backend.tools.train_tool import search_trains_structured, format_trains_text
from backend.tools.hotel_tool import search_hotels_structured, format_hotels_text
from backend.tools.tavily_tool import search_attractions

log = logging.getLogger(__name__)

llm = ChatGroq(model=LLM_MODEL)

# ─────────────────────────────────────────────────────────────────────────────
# 1. ROUTER AGENT
# ─────────────────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
You are a travel-planning assistant. Analyze the FULL conversation so far and
the latest user message to extract travel details and decide the next action.

Current known state:
- Origin:       {origin}
- Destination:  {destination}
- Start date:   {start_date}
- End date:     {end_date}
- Num days:     {num_days}
- Budget:       {budget}
- Travel mode:  {travel_mode}
- Has flights:  {has_flights}
- Has trains:   {has_trains}
- Has hotels:   {has_hotels}
- Has itinerary:{has_itinerary}

Rules:
1. Extract any NEW info from the latest message (city names, dates, preferences).
2. For dates like "next Monday" or "tomorrow", compute the actual date relative
   to today ({today}).
3. If destination is missing → ask for it.
4. If origin is missing → ask where they are traveling from.
5. If dates are missing → ask when they want to travel.
6. If origin + destination + dates are all known AND no search done yet → action = "search_all"
7. If the user asks for return tickets → action = "search_return"
8. If search results exist and user wants itinerary → action = "generate_itinerary"
9. For general questions / chit-chat → action = "respond"

Respond with ONLY valid JSON (no markdown):
{{
  "origin": "<city or null>",
  "destination": "<city or null>",
  "start_date": "<YYYY-MM-DD or null>",
  "end_date": "<YYYY-MM-DD or null>",
  "num_days": <int or null>,
  "budget": "<string or null>",
  "travel_mode": "<flight|train|both or null>",
  "action": "<ask_user|search_all|search_return|generate_itinerary|respond>",
  "response": "<your natural-language reply to the user>"
}}
"""


def router_agent(state: TravelState) -> dict:
    """Analyze conversation and decide the next pipeline step."""
    origin = state.get("origin", "") or ""
    destination = state.get("destination", "") or ""
    start_date = state.get("start_date", "") or ""
    end_date = state.get("end_date", "") or ""
    num_days = state.get("num_days", 0) or 0
    budget = state.get("budget", "") or ""
    travel_mode = state.get("travel_mode", "") or ""
    flight_results = state.get("flight_results", "") or ""
    train_results = state.get("train_results", "") or ""
    hotel_results = state.get("hotel_results", "") or ""
    itinerary = state.get("itinerary", "") or ""

    system_prompt = _ROUTER_SYSTEM.format(
        origin=origin or "unknown",
        destination=destination or "unknown",
        start_date=start_date or "unknown",
        end_date=end_date or "unknown",
        num_days=num_days or "unknown",
        budget=budget or "unknown",
        travel_mode=travel_mode or "unknown",
        has_flights=bool(flight_results),
        has_trains=bool(train_results),
        has_hotels=bool(hotel_results),
        has_itinerary=bool(itinerary),
        today=datetime.now().strftime("%Y-%m-%d"),
    )

    messages_for_llm = [SystemMessage(content=system_prompt)]
    # Include the last few messages for context (limit to avoid token overflow)
    recent = state.get("messages", [])[-10:]
    messages_for_llm.extend(recent)

    response = llm.invoke(messages_for_llm)
    llm_calls = state.get("llm_calls", 0) + 1

    # Parse the JSON response
    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError:
        # If LLM didn't return valid JSON, treat as a general response
        return {
            "messages": [AIMessage(content=response.content)],
            "phase": "respond",
            "needs_input": "",
            "llm_calls": llm_calls,
        }

    # Update state with any newly extracted info
    updates: dict = {"llm_calls": llm_calls}

    if parsed.get("origin") and not origin:
        updates["origin"] = parsed["origin"]
    if parsed.get("destination") and not destination:
        updates["destination"] = parsed["destination"]
    if parsed.get("start_date") and not start_date:
        updates["start_date"] = parsed["start_date"]
    if parsed.get("end_date") and not end_date:
        updates["end_date"] = parsed["end_date"]
    if parsed.get("num_days") and not num_days:
        updates["num_days"] = parsed["num_days"]
        # Auto-compute end_date if we have start_date + num_days
        if updates.get("start_date") or start_date:
            try:
                sd = datetime.strptime(
                    updates.get("start_date", start_date), "%Y-%m-%d"
                )
                updates["end_date"] = (
                    sd + timedelta(days=parsed["num_days"] - 1)
                ).strftime("%Y-%m-%d")
            except ValueError:
                pass
    if parsed.get("budget") and not budget:
        updates["budget"] = parsed["budget"]
    if parsed.get("travel_mode") and not travel_mode:
        updates["travel_mode"] = parsed["travel_mode"]

    action = parsed.get("action", "respond")
    reply = parsed.get("response", "I can help you plan your trip!")

    updates["phase"] = action
    updates["needs_input"] = "yes" if action == "ask_user" else ""
    updates["messages"] = [AIMessage(content=reply)]

    return updates


# ─────────────────────────────────────────────────────────────────────────────
# 2. FLIGHT AGENT
# ─────────────────────────────────────────────────────────────────────────────

def flight_agent(state: TravelState) -> dict:
    """Search flights from origin to destination."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching flights: %s → %s on %s", origin, destination, date)
    flights = search_flights(origin, destination, date)

    return {
        "flight_results": json.dumps(flights),
        "messages": [
            AIMessage(content=f"✈️ Found {len(flights)} flight(s) from {origin} to {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRAIN AGENT
# ─────────────────────────────────────────────────────────────────────────────

def train_agent(state: TravelState) -> dict:
    """Search trains from origin to destination."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching trains: %s → %s on %s", origin, destination, date)
    trains = search_trains_structured(origin, destination, date)

    return {
        "train_results": json.dumps(trains),
        "messages": [
            AIMessage(content=f"🚂 Found {len(trains)} train(s) from {origin} to {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,  # LLM used inside train_tool
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. HOTEL AGENT
# ─────────────────────────────────────────────────────────────────────────────

def hotel_agent(state: TravelState) -> dict:
    """Search hotels at the destination."""
    destination = state.get("destination", "")
    checkin = state.get("start_date", "")
    checkout = state.get("end_date", "")

    log.info("Searching hotels in %s (%s to %s)", destination, checkin, checkout)
    hotels = search_hotels_structured(destination, checkin, checkout)

    return {
        "hotel_results": json.dumps(hotels),
        "messages": [
            AIMessage(content=f"🏨 Found {len(hotels)} hotel(s) in {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. RETURN TRANSPORT AGENT
# ─────────────────────────────────────────────────────────────────────────────

def return_agent(state: TravelState) -> dict:
    """Search return flights/trains (destination → origin)."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    end_date = state.get("end_date", "")

    log.info("Searching return transport: %s → %s on %s", destination, origin, end_date)

    return_flights = search_flights(destination, origin, end_date)
    return_trains = search_trains_structured(destination, origin, end_date)

    combined = {
        "flights": return_flights,
        "trains": return_trains,
    }

    total = len(return_flights) + len(return_trains)
    return {
        "return_results": json.dumps(combined),
        "messages": [
            AIMessage(
                content=(
                    f"🔄 Found {len(return_flights)} return flight(s) and "
                    f"{len(return_trains)} return train(s) from {destination} to {origin}."
                )
            )
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. PRESENT RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def present_results(state: TravelState) -> dict:
    """Compose a friendly message summarizing all search results."""
    flights = json.loads(state.get("flight_results", "[]") or "[]")
    trains = json.loads(state.get("train_results", "[]") or "[]")
    hotels = json.loads(state.get("hotel_results", "[]") or "[]")
    destination = state.get("destination", "your destination")

    parts = [
        f"Here are the best travel options I found for your trip to **{destination}**! 🎉\n"
    ]

    if flights:
        parts.append(f"✈️ **{len(flights)} Flight(s)** available")
    if trains:
        parts.append(f"🚂 **{len(trains)} Train(s)** available")
    if hotels:
        parts.append(f"🏨 **{len(hotels)} Hotel(s)** found")

    parts.append(
        "\nYou can browse the options above and click **Book Now** to book on the "
        "respective platform. Would you also like me to:\n"
        "- 🔄 Search for **return tickets**?\n"
        "- 📋 Generate a **day-by-day itinerary**?"
    )

    return {
        "messages": [AIMessage(content="\n".join(parts))],
        "phase": "results_shown",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. ITINERARY AGENT
# ─────────────────────────────────────────────────────────────────────────────

def itinerary_agent(state: TravelState) -> dict:
    """Generate a day-by-day itinerary using the LLM."""
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    num_days = state.get("num_days", 0) or 3
    start_date = state.get("start_date", "")
    budget = state.get("budget", "")
    flights_text = format_flights_text(
        json.loads(state.get("flight_results", "[]") or "[]")
    )
    trains_text = format_trains_text(
        json.loads(state.get("train_results", "[]") or "[]")
    )
    hotels_text = format_hotels_text(
        json.loads(state.get("hotel_results", "[]") or "[]")
    )

    # Get tourist attractions
    attractions = search_attractions(destination)

    prompt = f"""\
Create a detailed {num_days}-day travel itinerary for a trip from {origin} to {destination}.
Start date: {start_date}
Budget: {budget or "flexible"}

Available Transport:
{flights_text}

{trains_text}

Available Hotels:
{hotels_text}

Tourist Attractions & Things To Do:
{attractions}

Please create a day-by-day itinerary with:
- Morning, afternoon, and evening activities
- Suggested transport and hotel from the options above
- Estimated costs where possible
- Local food recommendations
- Practical tips

Format each day clearly with a heading like "## Day 1: [date] — [theme]"
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner who creates detailed, practical itineraries."),
            HumanMessage(content=prompt),
        ]
    )

    return {
        "itinerary": response.content,
        "messages": [AIMessage(content="📋 Your itinerary is ready!")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. FINAL AGENT
# ─────────────────────────────────────────────────────────────────────────────

def final_agent(state: TravelState) -> dict:
    """Generate the complete final trip summary."""
    itinerary = state.get("itinerary", "")
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    num_days = state.get("num_days", 0)

    prompt = f"""\
Create a final, comprehensive travel plan summary for a {num_days}-day trip
from {origin} to {destination}.

Itinerary:
{itinerary}

Please provide:
1. A brief trip overview
2. The complete itinerary (reformatted neatly)
3. Packing suggestions
4. Important travel tips
5. Emergency contacts / useful info for {destination}

Keep it well-organized with clear headings and bullet points.
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner creating a final trip document."),
            HumanMessage(content=prompt),
        ]
    )

    return {
        "messages": [response],
        "phase": "complete",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
