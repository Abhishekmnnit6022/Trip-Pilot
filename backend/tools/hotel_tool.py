"""
Hotel search using RapidAPI (Booking.com) with Tavily fallback.
Returns structured data for the frontend to render as cards.
"""

import json
import logging
import requests
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from backend.config import RAPIDAPI_KEY, LLM_MODEL
from backend.tools.tavily_tool import search_hotels as tavily_hotel_search
from backend.tools.booking_links import get_booking_hotel_url, get_makemytrip_hotel_url

log = logging.getLogger(__name__)

_llm = ChatGroq(model=LLM_MODEL)

RAPIDAPI_HOST = "booking-com15.p.rapidapi.com"
DESTINATION_URL = f"https://{RAPIDAPI_HOST}/api/v1/hotels/searchDestination"
SEARCH_URL = f"https://{RAPIDAPI_HOST}/api/v1/hotels/searchHotels"


def _rapidapi_headers() -> dict[str, str]:
    """Return the authentication headers shared by Booking.com API requests."""
    return {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }


def _resolve_destination(destination: str) -> tuple[str, str] | None:
    """Resolve a user-entered place name to Booking.com's destination ID and type."""
    try:
        resp = requests.get(
            DESTINATION_URL,
            headers=_rapidapi_headers(),
            params={"query": destination},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("data", [])
    except Exception as exc:
        log.error("RapidAPI destination lookup failed for %s: %s", destination, exc)
        return None

    if not isinstance(results, list):
        return None

    normalized = destination.casefold().strip()
    city_results = [item for item in results if item.get("search_type", "").casefold() == "city"]
    exact_city = next(
        (
            item
            for item in city_results
            if item.get("name", "").casefold() == normalized
            or item.get("city_name", "").casefold() == normalized
        ),
        None,
    )
    match = exact_city or (city_results[0] if city_results else results[0])
    dest_id = match.get("dest_id")
    search_type = match.get("search_type")
    if not dest_id or not search_type:
        return None

    return str(dest_id), str(search_type).lower()


def _search_rapidapi(
    destination: str, checkin: str, checkout: str
) -> list[dict]:
    """Search hotels via RapidAPI Booking.com endpoint."""
    if not RAPIDAPI_KEY:
        log.warning("RapidAPI key not configured, skipping hotel API search")
        return []

    resolved_destination = _resolve_destination(destination)
    if not resolved_destination:
        log.warning("RapidAPI could not resolve hotel destination: %s", destination)
        return []

    dest_id, search_type = resolved_destination
    log.info("RapidAPI resolved %s to %s (%s)", destination, dest_id, search_type)
    params = {
        "dest_id": dest_id,
        "search_type": search_type,
        "arrival_date": checkin,
        "departure_date": checkout,
        "adults": "2",
        "room_qty": "1",
        "page_number": "1",
        "units": "metric",
        "temperature_unit": "c",
        "languagecode": "en-us",
        "currency_code": "INR",
    }

    try:
        resp = requests.get(SEARCH_URL, headers=_rapidapi_headers(), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("RapidAPI hotel search failed: %s", exc)
        return []

    hotels: list[dict] = []
    items = data.get("data", {}).get("hotels", []) if isinstance(data.get("data"), dict) else []

    for hotel in items[:6]:
        prop = hotel.get("property", {})
        hotels.append(
            {
                "name": prop.get("name", "Unknown Hotel"),
                "rating": prop.get("reviewScore", "N/A"),
                "rating_word": prop.get("reviewScoreWord", ""),
                "price": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("value", "N/A"),
                "currency": prop.get("priceBreakdown", {}).get("grossPrice", {}).get("currency", "INR"),
                "photo_url": prop.get("photoUrls", [""])[0] if prop.get("photoUrls") else "",
                "checkin": checkin,
                "checkout": checkout,
                "booking_url": get_booking_hotel_url(destination, checkin, checkout),
            }
        )

    return hotels


_PARSE_PROMPT = """\
You are a data extraction assistant. Given raw web search results about hotels,
extract a JSON array of hotel objects.

Each object MUST have these keys (use "N/A" for unknown values):
  - name: string
  - rating: string or number
  - rating_word: string (e.g. "Excellent", "Good")
  - price: string (e.g. "₹2,500/night" or "N/A")
  - amenities: string (e.g. "WiFi, Pool, Breakfast")

Return ONLY a valid JSON array. No markdown, no explanation.
If you cannot find any hotels, return an empty array: []
"""


def _search_tavily_fallback(
    destination: str, checkin: str, checkout: str
) -> list[dict]:
    """Fallback: search hotels via Tavily + LLM parsing."""
    raw = tavily_hotel_search(destination, checkin, checkout)
    if not raw or raw == "No results found.":
        return []

    try:
        response = _llm.invoke(
            [
                SystemMessage(content=_PARSE_PROMPT),
                HumanMessage(
                    content=(
                        f"Extract hotel information from these search results "
                        f"for hotels in {destination}:\n\n{raw}"
                    )
                ),
            ]
        )
        hotels = json.loads(response.content)
        if not isinstance(hotels, list):
            hotels = []
    except (json.JSONDecodeError, Exception) as exc:
        log.error("Failed to parse hotel results: %s", exc)
        hotels = []

    booking_url = get_booking_hotel_url(destination, checkin, checkout)
    mmt_url = get_makemytrip_hotel_url(destination, checkin, checkout)
    for h in hotels:
        h.setdefault("photo_url", "")
        h.setdefault("checkin", checkin)
        h.setdefault("checkout", checkout)
        h["booking_url"] = booking_url
        h["mmt_url"] = mmt_url

    return hotels


def search_hotels_structured(
    destination: str, checkin: str = "", checkout: str = ""
) -> list[dict]:
    """
    Search hotels — tries RapidAPI first, falls back to Tavily.
    Returns a list of hotel dicts.
    """
    hotels = _search_rapidapi(destination, checkin, checkout)
    if not hotels:
        log.info("RapidAPI returned no results, falling back to Tavily")
        hotels = _search_tavily_fallback(destination, checkin, checkout)
    return hotels


def format_hotels_text(hotels: list[dict]) -> str:
    """Convert structured hotel data to readable text for the LLM."""
    if not hotels:
        return "No hotel data available."

    lines: list[str] = []
    for i, h in enumerate(hotels, 1):
        price_str = h.get("price", "N/A")
        if isinstance(price_str, (int, float)):
            price_str = f"₹{price_str:,.0f}"
        lines.append(
            f"{i}. {h.get('name', 'Unknown')}\n"
            f"   Rating: {h.get('rating', 'N/A')} {h.get('rating_word', '')}\n"
            f"   Price: {price_str}\n"
            f"   Amenities: {h.get('amenities', 'N/A')}"
        )
    return "\n\n".join(lines)
