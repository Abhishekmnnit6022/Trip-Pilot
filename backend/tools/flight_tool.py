"""
Flight search using AviationStack API.
Returns structured data (list of dicts) for the frontend to render as cards.
"""

import logging
import requests
from backend.config import AVIATIONSTACK_API_KEY
from backend.tools.booking_links import get_makemytrip_flight_url, get_skyscanner_url

log = logging.getLogger(__name__)

API_URL = "http://api.aviationstack.com/v1/flights"


def search_flights(
    origin: str = "",
    destination: str = "",
    date: str = "",
) -> list[dict]:
    """
    Search flights via AviationStack.

    Returns a list of dicts, each containing:
        airline, flight_number, departure_airport, departure_time,
        arrival_airport, arrival_time, status, booking_url
    """
    if not AVIATIONSTACK_API_KEY:
        log.warning("AviationStack API key not configured")
        return []

    params: dict = {"access_key": AVIATIONSTACK_API_KEY, "limit": 5}
    if origin:
        params["dep_iata"] = origin.upper()
    if destination:
        params["arr_iata"] = destination.upper()

    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("AviationStack request failed: %s", exc)
        return []

    flights: list[dict] = []
    for flight in (data.get("data") or [])[:5]:
        dep = flight.get("departure") or {}
        arr = flight.get("arrival") or {}
        airline_info = flight.get("airline") or {}
        flight_info = flight.get("flight") or {}

        airline = airline_info.get("name", "Unknown Airline")
        flight_number = flight_info.get("iata", "N/A")
        dep_airport = dep.get("airport", "Unknown")
        dep_iata = dep.get("iata", "")
        dep_time = dep.get("scheduled", "")
        arr_airport = arr.get("airport", "Unknown")
        arr_iata = arr.get("iata", "")
        arr_time = arr.get("scheduled", "")
        status = flight.get("flight_status", "Unknown")

        booking_url = get_makemytrip_flight_url(
            dep_iata or origin, arr_iata or destination, date
        )

        flights.append(
            {
                "airline": airline,
                "flight_number": flight_number,
                "departure_airport": dep_airport,
                "departure_iata": dep_iata,
                "departure_time": dep_time,
                "arrival_airport": arr_airport,
                "arrival_iata": arr_iata,
                "arrival_time": arr_time,
                "status": status,
                "booking_url": booking_url,
            }
        )

    return flights


def format_flights_text(flights: list[dict]) -> str:
    """Convert structured flight data to readable text for the LLM."""
    if not flights:
        return "No flight data available."

    lines: list[str] = []
    for i, f in enumerate(flights, 1):
        lines.append(
            f"{i}. {f['airline']} ({f['flight_number']})\n"
            f"   {f['departure_airport']} → {f['arrival_airport']}\n"
            f"   Departure: {f['departure_time']}\n"
            f"   Arrival: {f['arrival_time']}\n"
            f"   Status: {f['status']}"
        )
    return "\n\n".join(lines)
