"""
Hotel agent nodes:
  - hotel_agent           — raw hotel search
  - auto_book_hotel_agent — selects best hotel via rating, waits for payment
"""

import json
import logging

from langchain_core.messages import AIMessage

from backend.agents.state import TravelState
from backend.tools.hotel_tool import search_hotels_structured

log = logging.getLogger(__name__)

_HOTEL_SYSTEM = """You are the Hotel Booking Agent.
Find accommodations for the user's trip to {destination}.
Trip dates: {start_date} to {end_date}
Budget limit: {budget} (Aim for {budget_limit} INR or lower if specified)

The user's Travel Twin Profile (learned from past bookings) is:
{travel_twin}

Instructions:
1. Use the 'search_hotels' tool to fetch hotel results from Booking.com.
2. Incorporate the user's Travel Twin preferences (e.g. hotel_preference_stars) when selecting.
3. Return a maximum of 3 hotels sorted to balance budget and star preference.
4. Your output MUST be ONLY valid JSON matching this schema (no markdown wrappers):
[
  {"hotel_name": "...", "rating": 4.5, "price_per_night": 5000, "total_price": 10000,
   "booking_url": "...", "image_url": "..."}
]
"""


def hotel_agent(state: TravelState) -> dict:
    """Search hotels at the destination."""
    destination = state.get("destination", "")
    checkin = state.get("start_date", "")
    checkout = state.get("end_date", "")
    budget = state.get("budget", "")

    log.info("Searching hotels in %s (%s to %s) budget: %s", destination, checkin, checkout, budget)
    hotels = search_hotels_structured(destination, checkin, checkout, budget)

    return {
        "hotel_results": json.dumps(hotels),
        "messages": [
            AIMessage(content=f"Found {len(hotels)} hotel(s) in {destination}.")
        ],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


def auto_book_hotel_agent(state: TravelState) -> dict:
    """Search hotels, pick the best one by rating, and wait for payment."""
    destination = state.get("destination", "")
    checkin = state.get("start_date", "")
    checkout = state.get("end_date", "")
    budget = state.get("budget", "")

    log.info("Auto-booking hotel in %s (%s to %s)", destination, checkin, checkout)
    hotels = search_hotels_structured(destination, checkin, checkout, budget)

    if not hotels:
        return {
            "messages": [AIMessage(content=(
                f"I couldn't find hotels in {destination} for your dates. "
                "Let me proceed with generating your itinerary instead!"
            ))],
            "phase": "generate_itinerary",
            "llm_calls": state.get("llm_calls", 0),
        }

    def _parse_rating(r):
        try:
            return float(r)
        except (ValueError, TypeError):
            return 0.0

    sorted_hotels = sorted(hotels, key=lambda h: _parse_rating(h.get("rating")), reverse=True)
    selected = sorted_hotels[0]

    price = selected.get("price", selected.get("price_per_night", "N/A"))
    price_str = f"{price:,.0f}/night" if isinstance(price, (int, float)) else str(price)

    msg = (
        f"I have selected the best hotel based on your preferences!\n\n"
        f"**{selected.get('name', selected.get('hotel_name', 'Hotel'))}**\n"
        f"Rating: {selected.get('rating', 'N/A')}\n"
        f"Price: {price_str}\n"
        f"Check-in: {checkin} | Check-out: {checkout}\n\n"
        f"Please click **Book Now** on the card below to manually complete the payment.\n\n"
        f"**Would you like me to generate a personalized day-by-day itinerary now?**"
    )

    return {
        "hotel_results": json.dumps([selected]),
        "messages": [AIMessage(content=msg)],
        "phase": "ask_user",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
