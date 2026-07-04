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
from backend.tools.weather_tool import get_weather_forecast

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
    end_date = state.get("end_date", "")
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

    # Get weather forecast
    weather_data = get_weather_forecast(destination, start_date, end_date)
    weather_text = weather_data.get("summary", "Weather data unavailable.")

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

Weather Forecast:
{weather_text}

Please create a day-by-day itinerary with:
- Morning, afternoon, and evening activities
- Suggested transport and hotel from the options above
- Weather-appropriate activity suggestions
- Estimated costs where possible
- Local food recommendations
- Practical tips based on the weather

Format each day clearly with a heading like "## Day 1: [date] — [theme]"
At the end, include a section "## 🌤️ Weather Summary" with the forecast.
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner who creates detailed, practical itineraries. Factor in weather conditions for activity planning."),
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
    """Generate the complete final trip summary with packing checklist."""
    itinerary = state.get("itinerary", "")
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    num_days = state.get("num_days", 0)
    start_date = state.get("start_date", "")
    end_date = state.get("end_date", "")

    # Get weather for packing suggestions
    weather_data = get_weather_forecast(destination, start_date, end_date)
    weather_text = weather_data.get("summary", "Weather data unavailable.")

    prompt = f"""\
Create a final, comprehensive travel plan summary for a {num_days}-day trip
from {origin} to {destination}.

Itinerary:
{itinerary}

Weather Forecast:
{weather_text}

Please provide:
1. A brief trip overview
2. The complete itinerary (reformatted neatly)
3. 🧳 **Compact Packing Checklist** — A very short, COMPACT, weather-appropriate packing list. Only include the most essential 5-10 items. DO NOT provide long detailed categories. Keep it brief.
4. Important travel tips
5. Emergency contacts / useful info for {destination}

Keep it well-organized with clear headings and bullet points.
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner creating a final trip document with weather-aware packing suggestions."),
            HumanMessage(content=prompt),
        ]
    )

    return {
        "messages": [response],
        "phase": "complete",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. BUDGET CHECK NODE  (Cost Estimation)
# ─────────────────────────────────────────────────────────────────────────────

_COST_EXTRACT_PROMPT = """\
You are a financial analyst. Given a travel itinerary, extract the TOTAL
estimated trip cost in Indian Rupees (INR).

Rules:
1. Sum up ALL costs: transport (flights/trains), hotels, food, activities, misc.
2. If exact prices are not listed, estimate reasonable prices for India.
3. Return ONLY a JSON object: {{"total_cost_inr": <integer>}}
4. No markdown, no explanation, just the JSON.

Example: {{"total_cost_inr": 18500}}
"""


def budget_check_node(state: TravelState) -> dict:
    """
    Extract total estimated cost from the itinerary using the LLM.
    
    This is a lightweight node that sits between itinerary_agent and
    the conditional budget routing edge. It uses the LLM to parse
    the generated itinerary and estimate the total trip cost in INR.
    
    The extracted cost is stored in `total_estimated_cost` for the
    routing function to compare against `budget_limit`.
    """
    itinerary = state.get("itinerary", "")
    budget = state.get("budget", "")
    budget_limit = state.get("budget_limit", 0)

    # If no budget was specified, skip cost check entirely
    if not budget_limit and not budget:
        log.info("[BudgetCheck] No budget specified — skipping cost estimation")
        return {
            "total_estimated_cost": 0,
            "llm_calls": state.get("llm_calls", 0),
        }

    # If budget is a text string but budget_limit hasn't been parsed yet,
    # try to extract the numeric value
    if budget and not budget_limit:
        budget_limit = _parse_budget_to_inr(budget)
        log.info("[BudgetCheck] Parsed budget '%s' → ₹%d", budget, budget_limit)

    # Ask LLM to extract cost from itinerary
    try:
        response = llm.invoke([
            SystemMessage(content=_COST_EXTRACT_PROMPT),
            HumanMessage(content=f"Extract the total cost from this itinerary:\n\n{itinerary}"),
        ])
        parsed = json.loads(response.content)
        total_cost = int(parsed.get("total_cost_inr", 0))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[BudgetCheck] Could not parse cost from LLM: %s", exc)
        total_cost = 0

    log.info(
        "[BudgetCheck] Estimated cost: ₹%d | Budget limit: ₹%d | Optimization #%d",
        total_cost, budget_limit, state.get("optimization_count", 0),
    )

    return {
        "total_estimated_cost": total_cost,
        "budget_limit": budget_limit,
        "messages": [
            AIMessage(content=f"💰 Estimated trip cost: ₹{total_cost:,}")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def _parse_budget_to_inr(budget_str: str) -> int:
    """
    Parse a human-readable budget string into an integer INR value.
    
    Handles formats like: "₹15000", "15000", "15k", "15,000", "budget", "luxury"
    """
    import re
    text = budget_str.lower().strip().replace(",", "").replace("₹", "").replace("rs", "").replace("inr", "")

    # Predefined budget tiers
    BUDGET_TIERS = {
        "budget": 10000,
        "cheap": 8000,
        "economy": 12000,
        "moderate": 20000,
        "mid-range": 25000,
        "luxury": 50000,
        "premium": 75000,
        "flexible": 0,
    }
    for keyword, amount in BUDGET_TIERS.items():
        if keyword in text:
            return amount

    # Try to extract number
    match = re.search(r"(\d+)\s*k", text)
    if match:
        return int(match.group(1)) * 1000

    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# 10. BUDGET OPTIMIZER NODE  (Autonomous Cost Reduction)
# ─────────────────────────────────────────────────────────────────────────────

_OPTIMIZER_PROMPT = """\
You are an expert budget travel optimizer. The user's trip costs ₹{total_cost}
but their budget is only ₹{budget_limit}.

You need to reduce the cost by ₹{overshoot}.

Current itinerary:
{itinerary}

Available transport data:
Flights: {flights}
Trains: {trains}
Hotels: {hotels}

OPTIMIZATION STRATEGIES (apply in order):
1. Replace flights with trains (saves 40-60%)
2. Replace luxury/5-star hotels with budget/3-star hotels (saves 50-70%)
3. Suggest cheaper dining options (local dhabas vs restaurants)
4. Recommend free/low-cost tourist activities over paid ones
5. Optimize travel dates if flexibility exists

Respond with ONLY valid JSON (no markdown):
{{
    "optimized_itinerary": "<complete re-written itinerary with cheaper options>",
    "cost_savings": "<explanation of what was changed and estimated savings>",
    "new_estimated_cost": <integer in INR>,
    "changes_made": ["<change 1>", "<change 2>", ...]
}}
"""


def budget_optimizer_node(state: TravelState) -> dict:
    """
    Autonomously optimize the trip to fit within the user's budget.
    
    This node is triggered when the budget_check_node determines that
    total_estimated_cost > budget_limit. It instructs the LLM to find
    cheaper alternatives (swap flights for trains, 5-star for 3-star, etc.)
    and generates a new optimized itinerary.
    
    The optimization_count is incremented to prevent infinite loops (max 2).
    After optimization, the pipeline re-enters the itinerary flow.
    """
    total_cost = state.get("total_estimated_cost", 0)
    budget_limit = state.get("budget_limit", 0)
    overshoot = total_cost - budget_limit
    itinerary = state.get("itinerary", "")
    optimization_count = state.get("optimization_count", 0)
    flights_text = state.get("flight_results", "[]")
    trains_text = state.get("train_results", "[]")
    hotels_text = state.get("hotel_results", "[]")

    log.info(
        "[BudgetOptimizer] Optimizing trip (attempt #%d): ₹%d → ₹%d (overshoot: ₹%d)",
        optimization_count + 1, total_cost, budget_limit, overshoot,
    )

    prompt = _OPTIMIZER_PROMPT.format(
        total_cost=f"{total_cost:,}",
        budget_limit=f"{budget_limit:,}",
        overshoot=f"{overshoot:,}",
        itinerary=itinerary,
        flights=flights_text,
        trains=trains_text,
        hotels=hotels_text,
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are an expert budget travel optimizer. Your job is to reduce trip costs while maintaining a great travel experience."),
            HumanMessage(content=prompt),
        ])
        parsed = json.loads(response.content)
        optimized_itinerary = parsed.get("optimized_itinerary", itinerary)
        new_cost = int(parsed.get("new_estimated_cost", total_cost))
        changes = parsed.get("changes_made", [])
        savings_text = parsed.get("cost_savings", "")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[BudgetOptimizer] Could not parse optimizer response: %s", exc)
        optimized_itinerary = itinerary
        new_cost = total_cost
        changes = []
        savings_text = ""

    # Build user-facing message
    changes_str = "\n".join(f"  • {c}" for c in changes) if changes else "  • Minor adjustments made"
    msg = (
        f"🔄 **Budget Optimization (Round {optimization_count + 1})**\n\n"
        f"💸 Previous cost: ₹{total_cost:,}\n"
        f"🎯 Target budget: ₹{budget_limit:,}\n"
        f"✅ New estimated cost: ₹{new_cost:,}\n\n"
        f"**Changes made:**\n{changes_str}"
    )
    if savings_text:
        msg += f"\n\n📝 {savings_text}"

    return {
        "itinerary": optimized_itinerary,
        "total_estimated_cost": new_cost,
        "optimization_count": optimization_count + 1,
        "messages": [AIMessage(content=msg)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }

