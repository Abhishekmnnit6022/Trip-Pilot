"""
Transport agent nodes:
  - flight_agent           — raw flight search
  - train_agent            — raw train search
  - return_agent           — return-journey search (both modes)
  - auto_book_train_agent  — selects best train via LLM, waits for payment
  - auto_book_flight_agent — selects best flight via Travel Twin, waits for payment
  - offer_alternate_agent  — suggests alternate transport when train is waitlisted
"""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.state import TravelState
from backend.agents.nodes.utils import extract_text, clean_llm_json
from backend.tools.flight_tool import search_flights
from backend.tools.train_tool import search_trains_structured
from backend.llm_factory import get_llm

log = logging.getLogger(__name__)
llm = get_llm()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Raw search agents
# ─────────────────────────────────────────────────────────────────────────────

def flight_agent(state: TravelState) -> dict:
    """Search flights from origin to destination."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching flights: %s -> %s on %s", origin, destination, date)
    flights = search_flights(origin, destination, date)

    return {
        "flight_results": json.dumps(flights),
        "messages": [
            AIMessage(content=f"Found {len(flights)} flight(s) from {origin} to {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0),
    }


def train_agent(state: TravelState) -> dict:
    """Search trains from origin to destination."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching trains: %s -> %s on %s", origin, destination, date)
    trains = search_trains_structured(origin, destination, date)

    return {
        "train_results": json.dumps(trains),
        "messages": [
            AIMessage(content=f"Found {len(trains)} train(s) from {origin} to {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def return_agent(state: TravelState) -> dict:
    """Search return flights/trains (destination -> origin)."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    end_date = state.get("end_date", "")

    log.info("Searching return transport: %s -> %s on %s", destination, origin, end_date)

    return_flights = search_flights(destination, origin, end_date)
    return_trains = search_trains_structured(destination, origin, end_date)

    combined = {"flights": return_flights, "trains": return_trains}
    return {
        "return_results": json.dumps(combined),
        "messages": [
            AIMessage(content=(
                f"Found {len(return_flights)} return flight(s) and "
                f"{len(return_trains)} return train(s) from {destination} to {origin}."
            ))
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Auto-book train agent
# ─────────────────────────────────────────────────────────────────────────────

def auto_book_train_agent(state: TravelState) -> dict:
    """Search trains, pick the best one via LLM, and wait for payment."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")
    tier = state.get("train_tier", "SL")
    twin = state.get("travel_twin_profile", {})

    log.info("Searching trains: %s -> %s on %s (class: %s)", origin, destination, date, tier)
    trains = search_trains_structured(origin, destination, date)

    if not trains:
        return {
            "messages": [AIMessage(content=(
                f"Sorry, I could not find any trains from {origin} to {destination} on {date}. "
                "Would you like me to search for flights instead?"
            ))],
            "phase": "ask_user",
            "needs_input": "yes",
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    # Use LLM to pick the best train based on user preferences
    pick_prompt = (
        f"Pick the BEST train from this list for a traveler who prefers class {tier}.\n"
        f"Travel Twin profile: {json.dumps(twin, indent=2)}\n\n"
        f"Trains available:\n{json.dumps(trains, indent=2)}\n\n"
        f'Return ONLY JSON: {{"selected_index": <0-based index>, "reason": "<brief reason>"}}'
    )

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
        f"I have selected the best train based on your preferences!\n\n"
        f"**{selected.get('train_name', 'Express')}** (#{selected.get('train_number', '')})\n"
        f"From: {selected.get('departure_station', origin)} -> {selected.get('arrival_station', destination)}\n"
        f"Departs: {selected.get('departure_time', '')} | Arrives: {selected.get('arrival_time', '')}\n"
        f"Duration: {selected.get('duration', 'N/A')}\n"
        f"Class: **{tier}**\n\n"
        f"_{reason}_\n\n"
        f"Please click **Book Now** on the card below to manually complete the payment."
    )

    return {
        "train_results": json.dumps([selected]),
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Auto-book flight agent
# ─────────────────────────────────────────────────────────────────────────────

def auto_book_flight_agent(state: TravelState) -> dict:
    """Search flights, pick the best one based on Travel Twin, and wait for payment."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")
    twin = state.get("travel_twin_profile", {})

    log.info("Auto-booking flight: %s -> %s on %s", origin, destination, date)
    flights = search_flights(origin, destination, date)

    if not flights:
        return {
            "messages": [AIMessage(content=(
                f"No flights found from {origin} to {destination} on {date}.\n\n"
                "Would you like to proceed with a **train** instead? "
                "If yes, which class do you prefer? (1A, 2A, 3A, SL, CC)"
            ))],
            "phase": "ask_user",
            "needs_input": "yes",
            "transport_preference": "",
            "llm_calls": state.get("llm_calls", 0),
        }

    # Pick best flight based on Twin preferences
    selected = flights[0]
    if len(flights) > 1 and twin:
        budget_sensitivity = twin.get("budget_sensitivity", "medium")
        if budget_sensitivity != "low":
            selected = flights[-1]  # Usually cheapest is last

    msg = (
        f"I have selected the best flight based on your preferences!\n\n"
        f"**{selected.get('airline', 'Airline')}** ({selected.get('flight_number', '')})\n"
        f"From: {selected.get('departure_airport', origin)} -> {selected.get('arrival_airport', destination)}\n"
        f"Departs: {selected.get('departure_time', 'N/A')} | Arrives: {selected.get('arrival_time', 'N/A')}\n\n"
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
# 4. Offer alternate transport agent
# ─────────────────────────────────────────────────────────────────────────────

def offer_alternate_agent(state: TravelState) -> dict:
    """Suggest alternate transport when the train is on the waiting list."""
    origin = state.get("origin", "")
    destination = state.get("destination", "")
    date = state.get("start_date", "")

    log.info("Searching alternate transport: %s -> %s on %s", origin, destination, date)

    prompt = (
        f"The user's train from {origin} to {destination} on {date} is on the WAITING LIST.\n"
        "Suggest 2-3 realistic alternate transport combinations for traveling within India.\n\n"
        "Consider: Bus+Cab combos, Direct bus services (RedBus, VRL), Cab services (Ola, Uber Intercity), "
        "Alternate train routes.\n\n"
        "For each option provide: mode combination, approximate cost in INR, approximate duration, "
        "booking platform.\n\n"
        "Return ONLY JSON array:\n"
        '[{"mode": "...", "cost_inr": 1500, "duration": "6h", "platform": "RedBus + Ola", "description": "..."}]'
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are an Indian transport expert. Suggest practical alternatives."),
            HumanMessage(content=prompt),
        ])
        content = clean_llm_json(extract_text(response.content))
        alternatives = json.loads(content)
    except Exception:
        alternatives = [
            {
                "mode": "Bus + Cab",
                "cost_inr": 2000,
                "duration": "8h",
                "platform": "RedBus + Ola",
                "description": f"Take a bus from {origin} to nearest hub, then cab to {destination}",
            }
        ]

    alt_text = "\n".join([
        f"**Option {i + 1}: {a['mode']}**\n"
        f"  ~{a['cost_inr']:,} INR | {a['duration']} | {a['platform']}\n"
        f"  _{a.get('description', '')}_\n"
        for i, a in enumerate(alternatives)
    ])

    msg = (
        f"Alternate Transport Options\n"
        f"({origin} -> {destination} on {date})\n\n"
        f"{alt_text}\n"
        "Would you like to proceed with any of these, or keep your waiting list ticket?\n\n"
        "You can also say **'book hotel'** to move on to hotel booking."
    )

    return {
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
