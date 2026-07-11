"""
Enhanced Tavily search helpers for specialized travel queries.
"""

import logging
from tavily import TavilyClient
from backend.config import TAVILY_API_KEY

log = logging.getLogger(__name__)

_client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None


def _safe_search(query: str, max_results: int = 5) -> list[dict]:
    """Run a Tavily search, returning an empty list on failure."""
    if _client is None:
        log.warning("Tavily API key not configured")
        return []
    try:
        resp = _client.search(query=query, max_results=max_results)
        return resp.get("results", [])
    except Exception as exc:
        log.error("Tavily search failed: %s", exc)
        return []


def tavily_search(query: str, max_results: int = 5) -> str:
    """Generic Tavily search — returns formatted markdown text."""
    results = _safe_search(query, max_results)
    if not results:
        return "No results found."

    lines: list[str] = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        snippet = r.get("content", "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
        lines.append(f"{i}. **{title}**\n   {url}\n   {snippet}")
    return "\n\n".join(lines)


def search_trains(origin: str, destination: str, date: str = "") -> str:
    """
    Search for trains between two Indian cities using Tavily.
    Targets railway-specific sites for better results.
    """
    date_part = f" on {date}" if date else ""
    query = (
        f"trains from {origin} to {destination}{date_part} "
        f"schedule timing availability site:railyatri.in OR site:confirmtkt.com "
        f"OR site:trainman.in OR site:indiarailinfo.com"
    )
    return tavily_search(query, max_results=5)


def search_hotels(destination: str, checkin: str = "", checkout: str = "", budget: str = "") -> str:
    """Search for hotels at a destination using Tavily."""
    dates_part = f" checkin {checkin} checkout {checkout}" if checkin else ""
    budget_term = "budget affordable cheap" if budget and any(w in budget.lower() for w in ["cheap", "budget", "low", "economy"]) else "best"
    query = (
        f"{budget_term} hotels in {destination}{dates_part} "
        f"price rating reviews "
        f"site:booking.com OR site:makemytrip.com OR site:goibibo.com"
    )
    return tavily_search(query, max_results=5)


def search_attractions(destination: str) -> str:
    """Search for tourist attractions and things to do."""
    query = f"top tourist places things to do in {destination} travel guide"
    return tavily_search(query, max_results=5)


def search_flights_web(origin: str, destination: str, date: str = "") -> list[dict]:
    """
    Fallback flight search via Tavily web search.
    Returns a list of dicts matching the same schema as flight_tool.search_flights().
    Used when the AviationStack circuit breaker is OPEN.
    """
    from backend.tools.booking_links import get_makemytrip_flight_url

    date_part = f" on {date}" if date else ""
    query = (
        f"flights from {origin} to {destination}{date_part} "
        f"price schedule timing "
        f"site:makemytrip.com OR site:goibibo.com OR site:skyscanner.co.in"
    )
    results = _safe_search(query, max_results=5)
    if not results:
        return []

    booking_url = get_makemytrip_flight_url(origin, destination, date)

    flights: list[dict] = []
    for i, r in enumerate(results[:5], 1):
        title = r.get("title", "Flight Option")
        snippet = r.get("content", "")
        flights.append({
            "airline": title[:50] if title else f"Flight Option {i}",
            "flight_number": "Web Search",
            "departure_airport": origin,
            "departure_iata": "",
            "departure_time": date or "Check website",
            "arrival_airport": destination,
            "arrival_iata": "",
            "arrival_time": "Check website",
            "status": "web_search_result",
            "booking_url": r.get("url", booking_url),
            "travel_date": date,
        })

    log.info("[Tavily Fallback] Found %d flight result(s) for %s → %s", len(flights), origin, destination)
    return flights
