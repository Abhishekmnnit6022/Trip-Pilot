"""
Results presentation node — composes a summary of all search results.
"""

import json
import logging

from langchain_core.messages import AIMessage

from backend.agents.state import TravelState

log = logging.getLogger(__name__)


def present_results(state: TravelState) -> dict:
    """Compose a friendly message summarizing all search results."""
    flights = json.loads(state.get("flight_results", "[]") or "[]")
    trains = json.loads(state.get("train_results", "[]") or "[]")
    hotels = json.loads(state.get("hotel_results", "[]") or "[]")
    destination = state.get("destination", "your destination")

    parts = [
        f"Here are the best travel options I found for your trip to **{destination}**!\n",
        "*(Personalized using your Travel Twin profile)*\n",
    ]

    if flights:
        parts.append(f"**{len(flights)} Flight(s)** available")
    if trains:
        parts.append(f"**{len(trains)} Train(s)** available")
    if hotels:
        parts.append(f"**{len(hotels)} Hotel(s)** found")

    parts.append(
        "\nYou can browse the options above and click **Book Now** to book on the "
        "respective platform. Would you also like me to:\n"
        "- Search for **return tickets**?\n"
        "- Generate a **day-by-day itinerary**?"
    )

    return {
        "messages": [AIMessage(content="\n".join(parts))],
        "phase": "results_shown",
        "needs_input": "yes",
        "llm_calls": state.get("llm_calls", 0),
    }
