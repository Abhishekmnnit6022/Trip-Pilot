"""
Agent node functions for the LangGraph travel-planning pipeline.

Node summary
------------
router_agent           — parses user message, extracts info, decides next step in the guided flow
ask_user_agent         — pauses execution to prompt the user for missing details or payment
auto_book_train_agent  — selects best train based on profile, prompts for manual payment via BookingModal
auto_book_flight_agent — selects best flight based on profile, prompts for manual payment
auto_book_hotel_agent  — selects best hotel based on profile, prompts for manual payment
offer_alternate_agent  — triggered when train is waitlisted, offers alternate transport combos
generate_itinerary     — builds day-by-day JSON itinerary using Unsplash images and strict schema
"""

import json
import logging
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.config import LLM_MODEL, GEMINI_API_KEY
from backend.agents.state import TravelState
from backend.tools.flight_tool import search_flights, format_flights_text
from backend.tools.train_tool import search_trains_structured, format_trains_text
from backend.tools.hotel_tool import search_hotels_structured, format_hotels_text
from backend.tools.tavily_tool import search_attractions
from backend.tools.weather_tool import get_weather_forecast
from backend.llm_factory import get_llm

log = logging.getLogger(__name__)

llm = get_llm()

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(item.get("text", "") for item in content if isinstance(item, dict) and "text" in item)
    return str(content)

def clean_llm_json(raw: str) -> str:
    """
    Strip Qwen/thinking-model <think>...</think> blocks and extract the
    outermost JSON object or array from the remaining text.
    Works for both {} and [] payloads.
    """
    import re
    # Remove <think>...</think> blocks (including nested)
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Try to find outermost JSON object
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        return m.group(0)
    # Fallback: try array
    m = re.search(r'\[.*\]', cleaned, re.DOTALL)
    if m:
        return m.group(0)
    return cleaned

# ─────────────────────────────────────────────────────────────────────────────
# 1. ROUTER AGENT
# ─────────────────────────────────────────────────────────────────────────────

_ROUTER_SYSTEM = """\
You are a travel-planning concierge. Analyze the FULL conversation and the
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
3. If destination is missing → ask for it. action = "ask_user"
4. If origin is missing → ask where they are traveling from. action = "ask_user"
5. If dates are missing → ask when they want to travel. action = "ask_user"
6. If origin + destination + dates are known BUT transport_preference is empty → ask: "Would you like to travel by 🚂 Train or ✈️ Flight?" action = "ask_user"
7. If transport_preference = "train" AND train_tier is empty → ask: "Which class do you prefer? 1A (First AC), 2A (Second AC), 3A (Third AC), SL (Sleeper), or CC (Chair Car)?" action = "ask_user"
8. If transport_preference = "train" AND train_tier is known AND no transport booked → action = "auto_book_train"
9. If transport_preference = "flight" AND no transport booked → action = "auto_book_flight"
10. If booking_status = "waiting" and user says they want alternative transport → action = "offer_alternate"
11. If booking_status = "waiting" and user says keep waiting or declines alternate → move on to ask about hotel. action = "ask_hotel"
12. If transport IS booked AND no hotel booked AND user hasn't been asked about hotel yet → ask: "Would you also like me to book a hotel? If yes, any specific preferences or budget?" action = "ask_hotel"
13. If user says YES to hotel (or provides hotel preferences/budget) → action = "auto_book_hotel"
14. If user says NO to hotel → action = "generate_itinerary"
15. If hotel IS booked AND no itinerary yet → action = "generate_itinerary"
16. If user wants return tickets → action = "search_return"
17. If itinerary exists and user asks to regenerate → action = "generate_itinerary"
18. CRITICAL: If user says "train" or "flight" when asked about transport mode, extract it into transport_preference.
19. CRITICAL: If user mentions a class/tier (like "sleeper", "AC", "3A", "first class"), extract it into train_tier. Map: sleeper→SL, first AC/1AC→1A, second AC/2AC→2A, third AC/3AC→3A, chair car/CC→CC.
20. CRITICAL: If the user message says "Payment completed successfully", determine if it was for transport or hotel. If it was transport, set `paid_transport` to true. If hotel, set `paid_hotel` to true. Acknowledge the payment and move to the next phase (ask_hotel or generate_itinerary).
21. For general questions / chit-chat → action = "respond"

Respond with ONLY valid JSON (no markdown):
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
    # Include the last few messages for context (limit to avoid token overflow)
    recent = state.get("messages", [])[-10:]
    messages_for_llm.extend(recent)

    response = llm.invoke(messages_for_llm)
    llm_calls = state.get("llm_calls", 0) + 1

    # Parse the JSON response
    try:
        content_str = clean_llm_json(extract_text(response.content))
        parsed = json.loads(content_str)
        log.info("[ROUTER] action=%s origin=%s dest=%s transport=%s",
                 parsed.get('action'), parsed.get('origin'), parsed.get('destination'),
                 parsed.get('transport_preference'))
    except json.JSONDecodeError:
        raw_text = extract_text(response.content)
        log.warning("[ROUTER] LLM did not return valid JSON — inferring action from state")

        # --- Smart fallback: infer action from current state ---
        # If the user replied with a train tier and we know origin/dest/date, proceed with booking
        if transport_preference == "train" and train_tier and origin and destination and start_date:
            log.info("[ROUTER] Inferred action=auto_book_train from state (no JSON)")
            return {
                "messages": [AIMessage(content=raw_text.strip() or f"Got it! Searching for 3A trains from {origin} to {destination}...")],
                "phase": "auto_book_train",
                "needs_input": "",
                "llm_calls": llm_calls,
            }
        # If the user replied with a tier keyword directly
        tier_map = {"1a": "1A", "2a": "2A", "3a": "3A", "sl": "SL", "cc": "CC",
                    "sleeper": "SL", "first ac": "1A", "second ac": "2A", "third ac": "3A"}
        for keyword, tier_val in tier_map.items():
            if keyword in raw_text.lower() or (state.get("messages") and keyword in extract_text(state["messages"][-1].content).lower()):
                if transport_preference == "train" and origin and destination and start_date:
                    log.info("[ROUTER] Inferred train_tier=%s and action=auto_book_train from keyword", tier_val)
                    return {
                        "messages": [AIMessage(content=raw_text.strip() or f"Perfect! Searching {tier_val} trains...")],
                        "phase": "auto_book_train",
                        "train_tier": tier_val,
                        "needs_input": "",
                        "llm_calls": llm_calls,
                    }
        # Default: return whatever the LLM said
        return {
            "messages": [AIMessage(content=raw_text)],
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
    if parsed.get("transport_preference") and not transport_preference:
        updates["transport_preference"] = parsed["transport_preference"]
    if parsed.get("train_tier") and not train_tier:
        updates["train_tier"] = parsed["train_tier"]

    # Handle manual payment completion
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

_HOTEL_SYSTEM = """\
You are the Hotel Booking Agent.
Find accommodations for the user's trip to {destination}.
Trip dates: {start_date} to {end_date}
Budget limit: {budget} (Aim for {budget_limit} INR or lower if specified)

The user's Travel Twin Profile (learned from past bookings) is:
{travel_twin}

Instructions:
1. Use the 'search_hotels' tool to fetch hotel results from Booking.com.
2. IMPORTANT: Incorporate the user's Travel Twin preferences (e.g. hotel_preference_stars) when selecting the best hotels to display.
3. Your output MUST be ONLY valid JSON matching this schema:
[
  {{"hotel_name": "...", "rating": 4.5, "price_per_night": 5000, "total_price": 10000, "booking_url": "...", "image_url": "..."}}
]
4. Return a maximum of 3 hotels. Sort them to balance the user's budget and their Travel Twin star preference.
5. Do NOT wrap the JSON in markdown code blocks. Start directly with `[` and end with `]`.
"""

def hotel_agent(state: TravelState) -> dict:
    """Search hotels at the destination."""
    destination = state.get("destination", "")
    checkin = state.get("start_date", "")
    checkout = state.get("end_date", "")
    budget = state.get("budget", "")

    system_prompt = _HOTEL_SYSTEM.format(
        destination=destination,
        start_date=checkin,
        end_date=checkout,
        budget=budget,
        budget_limit=state.get("budget_limit", 0),
        travel_twin=json.dumps(state.get("travel_twin_profile", {}), indent=2)
    )

    log.info("Searching hotels in %s (%s to %s) with budget: %s", destination, checkin, checkout, budget)
    hotels = search_hotels_structured(destination, checkin, checkout, budget)

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
        f"Here are the best travel options I found for your trip to **{destination}**! 🎉\n",
        f"*(🧠 Personalized using your Travel Twin profile)*\n"
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
You are the Expert Itinerary Planner.
You have the following confirmed details for a trip to {destination}:
- Dates: {start_date} to {end_date} ({num_days} days)
- Flights: {flights_text}
- Trains: {trains_text}
- Hotels: {hotels_text}

The user's Travel Twin Profile (learned from past behavior) is:
{json.dumps(state.get("travel_twin_profile", {}), indent=2)}

7-Day Weather Forecast for {destination}:
{weather_text}

Instructions:
1. Generate a detailed day-by-day itinerary.
2. IMPORTANT: Tailor the activities to match the user's Travel Twin (e.g., if 'early_mornings' is 'low', start activities later).
3. If weather indicates rain on a specific day, suggest indoor activities.
4. For each place, provide a realistic description, cost estimate, and timing.
5. Provide a search query for an image of the place (e.g., "Triveni Sangam Prayagraj", "Eiffel Tower Paris").
6. You MUST return EXACTLY this JSON structure and absolutely nothing else:
{{
  "days": [
    {{
      "day_number": 1,
      "theme": "Brief Theme (e.g., ARRIVAL & SPIRITUAL SERENITY)",
      "places": [
        {{
          "name": "Place Name",
          "address": "Brief Address or Area",
          "rating": 4.8,
          "timing": "6:00 AM - 9:00 PM",
          "cost": "Free or ₹500",
          "description": "Short engaging description of the activity.",
          "image_search_query": "high quality search query for unsplash"
        }}
      ]
    }}
  ]
}}
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner who creates detailed, practical itineraries and returns ONLY valid JSON."),
            HumanMessage(content=prompt),
        ]
    )
    
    # Clean the JSON
    content = clean_llm_json(extract_text(response.content))

    return {
        "itinerary": content.strip(),
        "messages": [AIMessage(content="📋 Your custom trip plan is ready!")],
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

User's Travel Twin Profile (learned from past behavior):
{json.dumps(state.get("travel_twin_profile", {}), indent=2)}

Weather Forecast:
{weather_text}

Please provide:
1. A brief trip overview
2. The complete itinerary (reformatted neatly)
3. 🧳 **Compact Packing Checklist** — A very short, COMPACT, weather-appropriate packing list. Only include the most essential 5-10 items. DO NOT provide long detailed categories. Keep it brief.
4. Important travel tips
5. Emergency contacts / useful info for {destination}
6. 🧠 **Travel Twin Personalization** — Briefly explain (2-3 sentences) how this itinerary was tailored to the user's learned habits (e.g., budget sensitivity, walking tolerance, early mornings).

Keep it well-organized with clear headings and bullet points.
"""

    response = llm.invoke(
        [
            SystemMessage(content="You are an expert travel planner creating a final trip document with weather-aware packing suggestions."),
            HumanMessage(content=prompt),
        ]
    )

    msg_content = extract_text(response.content)
    return {
        "messages": [AIMessage(content=msg_content)],
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
        content = clean_llm_json(extract_text(response.content))
        parsed = json.loads(content)
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

The user's Travel Twin Profile is:
{travel_twin}

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
        travel_twin=json.dumps(state.get("travel_twin_profile", {}), indent=2)
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are an expert budget travel optimizer. Your job is to reduce trip costs while maintaining a great travel experience."),
            HumanMessage(content=prompt),
        ])
        content = extract_text(response.content).strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        content = content.strip()
        parsed = json.loads(content)
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


# ─────────────────────────────────────────────────────────────────────────────
# 11. AUTO-BOOK TRAIN AGENT
# ─────────────────────────────────────────────────────────────────────────────

def _generate_pnr() -> str:
    """Generate a 15-digit PNR number."""
    import random
    return "".join(str(random.randint(0, 9)) for _ in range(15))


def _simulate_booking_status() -> str:
    """Simulate a booking status (70% confirmed, 30% waiting)."""
    import random
    return "confirmed" if random.random() < 0.7 else "waiting"


def _save_booking_to_supabase(user_id: str, booking_type: str, provider: str,
                               pnr: str, travel_date: str, details: dict,
                               status: str, trip_id: str = None) -> bool:
    """Save a booking record to the Supabase bookings table."""
    try:
        from supabase import create_client
        from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY
        sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        record = {
            "user_id": user_id,
            "booking_type": booking_type,
            "provider_name": provider,
            "pnr_or_confirmation_number": pnr,
            "travel_date": travel_date,
            "status": status,
            "details": details,
        }
        if trip_id:
            record["trip_id"] = trip_id
        sb.table("bookings").insert(record).execute()
        return True
    except Exception as exc:
        log.error("Failed to save booking to Supabase: %s", exc)
        return False


def _send_telegram_booking_notification(user_id: str, booking_type: str,
                                         provider: str, pnr: str,
                                         travel_date: str, details: dict,
                                         status: str) -> None:
    """Send booking notification via Telegram if user is linked."""
    try:
        from supabase import create_client
        from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY, TELEGRAM_BOT_TOKEN
        if not TELEGRAM_BOT_TOKEN:
            return
        sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        resp = sb.table("user_profiles").select("telegram_chat_id").eq("id", user_id).execute()
        if not resp.data or not resp.data[0].get("telegram_chat_id"):
            return
        chat_id = resp.data[0]["telegram_chat_id"]

        emoji = {"flight": "✈️", "train": "🚂", "hotel": "🏨"}.get(booking_type, "📋")
        status_emoji = "✅ Confirmed" if status == "confirmed" else "⏳ Waiting List"

        detail_lines = []
        if booking_type == "train":
            detail_lines.append(f"  🚂 Train: {details.get('train_name', 'N/A')}")
            detail_lines.append(f"  #️⃣ Number: {details.get('train_number', 'N/A')}")
            detail_lines.append(f"  📍 From: {details.get('departure_station', 'N/A')}")
            detail_lines.append(f"  📍 To: {details.get('arrival_station', 'N/A')}")
            detail_lines.append(f"  🎫 Class: {details.get('class', 'N/A')}")
        elif booking_type == "flight":
            detail_lines.append(f"  ✈️ Airline: {details.get('airline', 'N/A')}")
            detail_lines.append(f"  #️⃣ Flight: {details.get('flight_number', 'N/A')}")
            detail_lines.append(f"  📍 From: {details.get('departure_airport', 'N/A')}")
            detail_lines.append(f"  📍 To: {details.get('arrival_airport', 'N/A')}")
        elif booking_type == "hotel":
            detail_lines.append(f"  🏨 Hotel: {details.get('name', 'N/A')}")
            detail_lines.append(f"  ⭐ Rating: {details.get('rating', 'N/A')}")
            price = details.get('price', 'N/A')
            if isinstance(price, (int, float)):
                price = f"₹{price:,.0f}"
            detail_lines.append(f"  💰 Price: {price}")

        details_text = "\n".join(detail_lines)
        text = (
            f"{emoji} <b>TripPilot — Auto-Booked!</b>\n\n"
            f"<b>Type:</b> {booking_type.title()}\n"
            f"<b>Provider:</b> {provider}\n"
            f"<b>PNR:</b> <code>{pnr}</code>\n"
            f"<b>Status:</b> {status_emoji}\n"
            f"<b>Date:</b> {travel_date or 'TBD'}\n\n"
            f"<b>Details:</b>\n{details_text}\n\n"
            f"{'🎉 Your booking is confirmed! Have a great trip!' if status == 'confirmed' else '⏳ Your ticket is on the waiting list. We will notify you when confirmed.'}"
        )

        import requests as req
        API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/"
        req.post(API_URL + "sendMessage", json={
            "chat_id": chat_id, "text": text, "parse_mode": "HTML"
        }, timeout=10)
    except Exception as exc:
        log.warning("Failed to send Telegram booking notification: %s", exc)


def auto_book_train_agent(state: TravelState) -> dict:
    """Search trains, pick the best one, and wait for payment."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")
    tier = state.get("train_tier", "SL")
    twin = state.get("travel_twin_profile", {})

    log.info("Searching trains: %s → %s on %s (class: %s)", origin, destination, date, tier)
    trains = search_trains_structured(origin, destination, date)

    if not trains:
        return {
            "messages": [AIMessage(content=(
                f"😔 I couldn't find any trains from {origin} to {destination} on {date}. "
                "Would you like me to search for flights instead?"
            ))],
            "phase": "ask_user",
            "needs_input": "yes",
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    # Use LLM to pick the best train based on user preferences
    train_list_text = json.dumps(trains, indent=2)
    pick_prompt = f"""Pick the BEST train from this list for a traveler who prefers class {tier}.
Travel Twin profile: {json.dumps(twin, indent=2)}

Trains available:
{train_list_text}

Return ONLY JSON: {{"selected_index": <0-based index of best train>, "reason": "<brief reason>"}}"""

    try:
        response = llm.invoke([
            SystemMessage(content="You are a train booking expert. Pick the best train."),
            HumanMessage(content=pick_prompt),
        ])
        content = extract_text(response.content).strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        parsed = json.loads(content.strip())
        idx = int(parsed.get("selected_index", 0))
        reason = parsed.get("reason", "Best available option")
    except Exception:
        idx = 0
        reason = "Selected the first available train"

    if idx >= len(trains):
        idx = 0
    selected = trains[idx]
    msg = (
        f"🚂 **I have selected the best train based on your preferences!**\n\n"
        f"**{selected.get('train_name', 'Express')}** (#{selected.get('train_number', '')})\n"
        f"📍 {selected.get('departure_station', origin)} → {selected.get('arrival_station', destination)}\n"
        f"🕐 {selected.get('departure_time', '')} — {selected.get('arrival_time', '')}\n"
        f"⏱️ Duration: {selected.get('duration', 'N/A')}\n"
        f"🎫 Class: **{tier}**\n\n"
        f"💡 _{reason}_\n\n"
        f"Please click **Book Now** on the card below to manually complete the payment."
    )

    result = {
        "train_results": json.dumps([selected]),
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 12. AUTO-BOOK FLIGHT AGENT
# ─────────────────────────────────────────────────────────────────────────────

def auto_book_flight_agent(state: TravelState) -> dict:
    """Search flights, pick the best one based on Travel Twin, and auto-book."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")
    twin = state.get("travel_twin_profile", {})

    log.info("Auto-booking flight: %s → %s on %s", origin, destination, date)
    flights = search_flights(origin, destination, date)

    if not flights:
        return {
            "messages": [AIMessage(content=(
                f"✈️ No flights found from {origin} to {destination} on {date}.\n\n"
                "Would you like to proceed with a **train** instead? "
                "If yes, which class do you prefer? (1A, 2A, 3A, SL, CC)"
            ))],
            "phase": "ask_user",
            "needs_input": "yes",
            "transport_preference": "",  # Reset so user can choose train
            "llm_calls": state.get("llm_calls", 0),
        }

    # Pick best flight based on Twin preferences
    selected = flights[0]  # Default to first

    if len(flights) > 1 and twin:
        budget_sensitivity = twin.get("budget_sensitivity", "medium")
        if budget_sensitivity == "low":
            # User doesn't care about budget → pick premium/first available
            selected = flights[0]
        else:
            selected = flights[-1]  # Usually cheapest is last

    msg = (
        f"✈️ **I have selected the best flight based on your preferences!**\n\n"
        f"**{selected.get('airline', 'Airline')}** ({selected.get('flight_number', '')})\n"
        f"📍 {selected.get('departure_airport', origin)} → {selected.get('arrival_airport', destination)}\n"
        f"🕐 Departs: {selected.get('departure_time', 'N/A')}\n"
        f"🛬 Arrives: {selected.get('arrival_time', 'N/A')}\n\n"
        f"Please click **Book Now** on the card below to manually complete the payment."
    )

    return {
        "flight_results": json.dumps([selected]),
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 13. AUTO-BOOK HOTEL AGENT
# ─────────────────────────────────────────────────────────────────────────────

def auto_book_hotel_agent(state: TravelState) -> dict:
    """Search hotels, pick the best one based on preferences, and auto-book."""
    destination = state.get("destination", "")
    checkin = state.get("start_date", "")
    checkout = state.get("end_date", "")
    budget = state.get("budget", "")
    twin = state.get("travel_twin_profile", {})

    log.info("Auto-booking hotel in %s (%s to %s)", destination, checkin, checkout)
    hotels = search_hotels_structured(destination, checkin, checkout, budget)

    if not hotels:
        return {
            "messages": [AIMessage(content=(
                f"🏨 I couldn't find hotels in {destination} for your dates. "
                "Let me proceed with generating your itinerary instead!"
            ))],
            "phase": "generate_itinerary",
            "llm_calls": state.get("llm_calls", 0),
        }

    # Pick best hotel: highest rating within budget
    def _parse_rating(r):
        try:
            return float(r)
        except (ValueError, TypeError):
            return 0.0

    sorted_hotels = sorted(hotels, key=lambda h: _parse_rating(h.get("rating")), reverse=True)
    selected = sorted_hotels[0]

    price = selected.get("price", selected.get("price_per_night", "N/A"))
    if isinstance(price, (int, float)):
        price_str = f"₹{price:,.0f}/night"
    else:
        price_str = str(price)

    msg = (
        f"🏨 **I have selected the best hotel based on your preferences!**\n\n"
        f"**{selected.get('name', selected.get('hotel_name', 'Hotel'))}**\n"
        f"⭐ Rating: {selected.get('rating', 'N/A')}\n"
        f"💰 Price: {price_str}\n"
        f"📅 Check-in: {checkin}\n"
        f"📅 Check-out: {checkout}\n\n"
        f"Please click **Book Now** on the card below to manually complete the payment.\n\n"
        f"**Would you like me to generate a personalized day-by-day itinerary for your trip now?**"
    )

    return {
        "hotel_results": json.dumps([selected]),
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 14. ALTERNATE TRANSPORT AGENT (Waitlist Handler)
# ─────────────────────────────────────────────────────────────────────────────

def offer_alternate_agent(state: TravelState) -> dict:
    """Suggest alternate transport when train is on waiting list."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching alternate transport: %s → %s on %s", origin, destination, date)

    # Use LLM to generate alternate transport suggestions
    prompt = f"""The user's train from {origin} to {destination} on {date} is on the WAITING LIST.
Suggest 2-3 realistic alternate transport combinations for traveling within India.

Consider:
- Bus + Cab combos (e.g., KSRTC/UPSRTC bus to nearest hub, then shared cab)
- Direct bus services (RedBus, VRL, SRS)
- Cab services (Ola Outstation, Uber Intercity)
- Alternate train routes (connecting trains)

For each option provide:
- Mode combination (e.g., "Bus to Haridwar + Shared Cab to Rishikesh")
- Approximate cost in INR
- Approximate duration
- Booking platform

Return ONLY JSON array:
[
  {{"mode": "...", "cost_inr": 1500, "duration": "6h", "platform": "RedBus + Ola", "description": "..."}}
]"""

    try:
        response = llm.invoke([
            SystemMessage(content="You are an Indian transport expert. Suggest practical alternatives."),
            HumanMessage(content=prompt),
        ])
        content = clean_llm_json(extract_text(response.content))
        alternatives = json.loads(content)
    except Exception:
        alternatives = [
            {"mode": f"Bus + Cab", "cost_inr": 2000, "duration": "8h",
             "platform": "RedBus + Ola", "description": f"Take a bus from {origin} to nearest hub, then cab to {destination}"}
        ]

    # Format alternatives as a nice message
    alt_text = "\n".join([
        f"**Option {i+1}: {a['mode']}**\n"
        f"  💰 ≈₹{a['cost_inr']:,} | ⏱️ {a['duration']} | 📱 {a['platform']}\n"
        f"  _{a.get('description', '')}_\n"
        for i, a in enumerate(alternatives)
    ])

    msg = (
        f"🔄 **Alternate Transport Options**\n"
        f"({origin} → {destination} on {date})\n\n"
        f"{alt_text}\n"
        f"Would you like to proceed with any of these options, or would you prefer to keep your waiting list ticket and hope it gets confirmed?\n\n"
        f"You can also say **'book hotel'** to move on to hotel booking."
    )

    return {
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }

