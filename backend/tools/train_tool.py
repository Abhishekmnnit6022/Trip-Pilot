"""
Train search using the RailRadar API, with a Tavily fallback when RailRadar is
not configured or temporarily unavailable.
"""

import json
import logging
from functools import lru_cache

import requests
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from backend.config import LLM_MODEL, RAILRADAR_API_KEY
from backend.tools.tavily_tool import search_trains as tavily_train_search
from backend.tools.booking_links import get_irctc_url

log = logging.getLogger(__name__)

_llm = ChatGroq(model=LLM_MODEL)

RAILRADAR_API_BASE = "https://api.railradar.in/v1"

# A city can have many stations.  These are the primary stations travellers
# commonly mean when they enter a city rather than a specific station code.
CITY_STATION_ALIASES = {
    "delhi": "NDLS", "new delhi": "NDLS", "mumbai": "CSMT", "bengaluru": "SBC", "bangalore": "SBC",
    "chennai": "MAS", "kolkata": "HWH", "hyderabad": "SC", "pune": "PUNE", "ahmedabad": "ADI",
    "jaipur": "JP", "lucknow": "LKO", "prayagraj": "PRYJ", "allahabad": "PRYJ", "varanasi": "BSB",
    "patna": "PNBE", "chandigarh": "CDG", "kochi": "ERS", "cochin": "ERS", "thiruvananthapuram": "TVC",
    "trivandrum": "TVC", "guwahati": "GHY", "amritsar": "ASR", "bhopal": "BPL", "indore": "INDB",
    "nagpur": "NGP", "surat": "ST", "bhubaneswar": "BBS", "ranchi": "RNC", "raipur": "R",
    "dehradun": "DDN", "goa": "MAO", "panaji": "MAO", "agra": "AGC", "ajmer": "AII",
    "aurangabad": "AWB", "ayodhya": "AY", "bareilly": "BE", "belagavi": "BGM", "belgaum": "BGM",
    "bhavnagar": "BVC", "bikaner": "BKN", "coimbatore": "CBE", "darjeeling": "NJP", "bagdogra": "NJP",
    "siliguri": "NJP", "dharamshala": "PTK", "dibrugarh": "DBRG", "dimapur": "DMV", "durgapur": "DGR",
    "gaya": "GAYA", "gorakhpur": "GKP", "gwalior": "GWL", "hubli": "UBL", "jabalpur": "JBP",
    "jaisalmer": "JSM", "jammu": "JAT", "jamnagar": "JAM", "jamshedpur": "TATA", "tatanagar": "TATA",
    "jodhpur": "JU", "kanpur": "CNB", "kolhapur": "KOP", "kozhikode": "CLT", "calicut": "CLT",
    "kurnool": "KRNT", "leh": "UHP", "ludhiana": "LDH", "madurai": "MDU", "mangalore": "MAQ",
    "mysore": "MYS", "nashik": "NK", "rajkot": "RJT", "shillong": "GHY", "shimla": "SML",
    "srinagar": "SINA", "tiruchirappalli": "TPJ", "trichy": "TPJ", "tirupati": "TPTY", "udaipur": "UDZ",
    "vadodara": "BRC", "vijayawada": "BZA", "visakhapatnam": "VSKP", "warangal": "WL", "kannur": "CAN",
    "kanyakumari": "CAPE", "pondicherry": "PDY", "rajahmundry": "RJY", "shirdi": "SNSI", "nanded": "NED",
    "jalgaon": "JL", "gondia": "G", "kandla": "GIMB", "porbandar": "PBR", "bhuj": "BHJU",
    "hissar": "HSR", "kangra": "KGRA", "kullu": "KLU", "manali": "KLU", "pathankot": "PTK",
    "bathinda": "BTI", "pantnagar": "PBW", "nainital": "KGM", "haldwani": "HDW", "pithoragarh": "PITH",
    "hazaribagh": "HZBN", "bokaro": "BKSC", "deoghar": "DGHR", "darbhanga": "DBG", "muzaffarpur": "MFP",
    "rajgir": "RGD", "imphal": "TSE", "agartala": "AGTL", "aizawl": "BHRB", "kohima": "DMV",
    "itanagar": "NHLN", "tezpur": "TZTB", "jorhat": "JT", "lakhimpur": "NLP", "gangtok": "NJP",
    "mathura": "MTJ", "vrindavan": "MTJ", "haridwar": "HW", "rishikesh": "RKSH", "aligarh": "ALJN",
    "jhansi": "VGLJ", "ujjain": "UJN", "somnath": "SMNH", "dwarka": "DWK", "rameshwaram": "RMM",
    "ooty": "UAM", "kodaikanal": "KQN", "munnar": "AWY", "wayanad": "CLT", "hampi": "HPT",
    "khajuraho": "KURJ", "puri": "PURI", "konark": "PURI", "mahabaleshwar": "PUNE", "lonavala": "LNL"
}

_PARSE_PROMPT = """\
You are a data extraction assistant. Given raw web search results about
Indian trains, extract a JSON array of train objects.

Each object MUST have these keys (use "N/A" for unknown values):
  - train_name: string
  - train_number: string
  - departure_station: string
  - departure_time: string (e.g. "06:15 AM")
  - arrival_station: string
  - arrival_time: string
  - duration: string (e.g. "5h 30m")
  - classes: string (e.g. "SL, 3A, 2A, 1A")
  - runs_on: string (e.g. "Mon, Wed, Fri" or "Daily")

Return ONLY a valid JSON array. No markdown, no explanation.
If you cannot find any trains, return an empty array: []
"""


def _railradar_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {RAILRADAR_API_KEY}"}


@lru_cache(maxsize=1)
def _station_map() -> dict[str, str]:
    """Fetch RailRadar's station-code map once per backend process."""
    response = requests.get(
        f"{RAILRADAR_API_BASE}/lookup/stations",
        headers=_railradar_headers(),
        timeout=15,
    )
    response.raise_for_status()
    stations = response.json().get("data", {})
    if not isinstance(stations, dict):
        raise ValueError("RailRadar returned an invalid station lookup response")
    return {str(code): str(name) for code, name in stations.items()}


def _station_code(place: str) -> str | None:
    """Resolve a city or station name to a RailRadar station code."""
    query = place.casefold().strip()
    if not query:
        return None

    if query in CITY_STATION_ALIASES:
        return CITY_STATION_ALIASES[query]

    stations = _station_map()
    # Permit callers to use a station code directly.
    if place.upper().strip() in stations:
        return place.upper().strip()

    exact = [code for code, name in stations.items() if name.casefold() == query]
    if exact:
        return exact[0]

    # Prefer a city's main terminus (for example, "New Delhi") over a
    # geographically named suburb such as "Delhi Azadpur".
    preferred = [
        code
        for code, name in stations.items()
        if name.casefold() in {f"new {query}", f"{query} jn", f"{query} jn."}
    ]
    if preferred:
        return preferred[0]

    starts_with = [
        code for code, name in stations.items() if name.casefold().startswith(query)
    ]
    return starts_with[0] if starts_with else None


def _format_duration(minutes: int | None) -> str:
    if not isinstance(minutes, int) or minutes < 0:
        return "N/A"
    hours, remainder = divmod(minutes, 60)
    return f"{hours}h {remainder}m" if hours else f"{remainder}m"


def _search_railradar(origin: str, destination: str, date: str) -> list[dict] | None:
    """Fetch structured trains from RailRadar; None means the API was unavailable."""
    from backend.circuit_breaker import railradar_breaker

    if not RAILRADAR_API_KEY:
        return None

    # Circuit Breaker: if OPEN, skip RailRadar entirely
    if not railradar_breaker.allow_request():
        log.warning("[CircuitBreaker] RailRadar circuit is OPEN — skipping to Tavily fallback")
        railradar_breaker.record_fallback()
        return None

    try:
        origin_code = _station_code(origin)
        destination_code = _station_code(destination)
        if not origin_code or not destination_code:
            log.warning("RailRadar could not resolve stations: %s -> %s", origin, destination)
            return []

        response = requests.get(
            f"{RAILRADAR_API_BASE}/trains/between/{origin_code}/{destination_code}",
            headers=_railradar_headers(),
            params={"date": date, "byCity": "true"} if date else {"byCity": "true"},
            timeout=20,
        )
        response.raise_for_status()
        records = response.json().get("data", {}).get("trains", [])
        if not isinstance(records, list):
            railradar_breaker.record_success()
            return []
        railradar_breaker.record_success()
    except requests.RequestException as exc:
        log.error("RailRadar train search failed: %s", exc)
        railradar_breaker.record_failure()
        return None
    except (TypeError, ValueError) as exc:
        log.error("Could not process RailRadar train data: %s", exc)
        railradar_breaker.record_failure()
        return None

    booking_url = get_irctc_url()
    trains: list[dict] = []
    for record in records[:10]:
        train = record.get("train", {})
        from_stop = record.get("from", {})
        to_stop = record.get("to", {})
        run_days = train.get("runDays", [])
        trains.append(
            {
                "train_name": train.get("name", "Unknown Train"),
                "train_number": train.get("number", "N/A"),
                "departure_station": from_stop.get("name", origin),
                "departure_time": from_stop.get("departure", "N/A"),
                "arrival_station": to_stop.get("name", destination),
                "arrival_time": to_stop.get("arrival", "N/A"),
                "duration": _format_duration(record.get("duration")),
                "classes": "Check availability on IRCTC",
                "runs_on": ", ".join(day.title() for day in run_days) or "N/A",
                "booking_url": booking_url,
            }
        )

    log.info("RailRadar found %s train(s): %s -> %s", len(trains), origin, destination)
    return trains


def search_trains_structured(
    origin: str, destination: str, date: str = ""
) -> list[dict]:
    """
    Search for trains and return structured data.
    Uses Tavily to fetch raw data, then LLM to parse it.
    """
    railradar_results = _search_railradar(origin, destination, date)
    if railradar_results:
        return railradar_results

    log.info("RailRadar returned no results or is unavailable; falling back to Tavily train search")
    raw_results = tavily_train_search(origin, destination, date)

    if not raw_results or raw_results == "No results found.":
        log.info("No train search results for %s → %s", origin, destination)
        return []

    try:
        response = _llm.invoke(
            [
                SystemMessage(content=_PARSE_PROMPT),
                HumanMessage(
                    content=(
                        f"Extract train information from these search results "
                        f"for trains from {origin} to {destination}:\n\n"
                        f"{raw_results}"
                    )
                ),
            ]
        )
        trains = json.loads(response.content)
        if not isinstance(trains, list):
            trains = []
    except (json.JSONDecodeError, Exception) as exc:
        log.error("Failed to parse train results: %s", exc)
        trains = []

    # Attach booking URL to every train
    booking_url = get_irctc_url()
    for t in trains:
        t["booking_url"] = booking_url

    return trains


def format_trains_text(trains: list[dict]) -> str:
    """Convert structured train data to readable text for the LLM."""
    if not trains:
        return "No train data available."

    lines: list[str] = []
    for i, t in enumerate(trains, 1):
        lines.append(
            f"{i}. {t.get('train_name', 'Unknown')} ({t.get('train_number', 'N/A')})\n"
            f"   {t.get('departure_station', '?')} ({t.get('departure_time', '?')}) → "
            f"{t.get('arrival_station', '?')} ({t.get('arrival_time', '?')})\n"
            f"   Duration: {t.get('duration', '?')} | Classes: {t.get('classes', '?')}\n"
            f"   Runs on: {t.get('runs_on', '?')}"
        )
    return "\n\n".join(lines)
