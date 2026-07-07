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

CITY_AIRPORT_MAP = {
    "delhi": "DEL", "new delhi": "DEL", "mumbai": "BOM", "bengaluru": "BLR", "bangalore": "BLR",
    "chennai": "MAA", "kolkata": "CCU", "hyderabad": "HYD", "pune": "PNQ", "ahmedabad": "AMD",
    "jaipur": "JAI", "lucknow": "LKO", "prayagraj": "IXD", "allahabad": "IXD", "varanasi": "VNS",
    "patna": "PAT", "chandigarh": "IXC", "kochi": "COK", "cochin": "COK", "thiruvananthapuram": "TRV",
    "trivandrum": "TRV", "guwahati": "GAU", "amritsar": "ATQ", "bhopal": "BHO", "indore": "IDR",
    "nagpur": "NAG", "surat": "STV", "bhubaneswar": "BBI", "ranchi": "IXR", "raipur": "RPR",
    "dehradun": "DED", "goa": "GOI", "panaji": "GOI", "agra": "AGR", "ajmer": "KQH",
    "aurangabad": "IXU", "ayodhya": "AYJ", "bareilly": "BEK", "belagavi": "IXG", "belgaum": "IXG",
    "bhavnagar": "BHU", "bikaner": "BKB", "coimbatore": "CJB", "darjeeling": "IXB", "bagdogra": "IXB",
    "siliguri": "IXB", "dharamshala": "DHM", "dibrugarh": "DIB", "dimapur": "DMU", "durgapur": "RDP",
    "gaya": "GAY", "gorakhpur": "GOP", "gwalior": "GWL", "hubli": "HBX", "jabalpur": "JLR",
    "jaisalmer": "JSA", "jammu": "IXJ", "jamnagar": "JGA", "jamshedpur": "IXW", "jodhpur": "JDH",
    "kanpur": "KNU", "kolhapur": "KLH", "kozhikode": "CCJ", "calicut": "CCJ", "kurnool": "KJB",
    "leh": "IXL", "ludhiana": "LUH", "madurai": "IXM", "mangalore": "IXE", "mysore": "MYQ",
    "nashik": "ISK", "port blair": "IXZ", "rajkot": "RAJ", "shillong": "SHL", "shimla": "SLV",
    "srinagar": "SXR", "tiruchirappalli": "TRZ", "trichy": "TRZ", "tirupati": "TIR", "udaipur": "UDR",
    "vadodara": "BDQ", "vijayawada": "VGA", "visakhapatnam": "VTZ", "warangal": "WGC", "kannur": "CNN",
    "kanyakumari": "TRV", "pondicherry": "PNY", "rajahmundry": "RJA", "shirdi": "SAG", "nanded": "NDC",
    "jalgaon": "JLG", "gondia": "GDB", "kandla": "IXY", "porbandar": "PBD", "bhuj": "BHJ", "diu": "DIU",
    "hissar": "HSS", "kangra": "DHM", "kullu": "KUU", "manali": "KUU", "pathankot": "IXP",
    "bathinda": "BUP", "pantnagar": "PGH", "nainital": "PGH", "haldwani": "PGH", "pithoragarh": "NNS",
    "hazaribagh": "HZD", "bokaro": "BKR", "deoghar": "DGH", "darbhanga": "DBR", "muzaffarpur": "MZU",
    "rajgir": "GAY", "imphal": "IMF", "agartala": "IXA", "aizawl": "AJL", "kohima": "DMU",
    "itanagar": "HGI", "tezpur": "TEZ", "jorhat": "JRH", "lakhimpur": "IXI", "rupsi": "RUP",
    "pakyong": "PYG", "gangtok": "PYG", "agatti": "AGX", "lakshadweep": "AGX", "mathura": "AGR",
    "vrindavan": "AGR", "haridwar": "DED", "rishikesh": "DED", "aligarh": "AGR", "jhansi": "GWL",
    "ujjain": "IDR", "somnath": "DIU", "dwarka": "JGA", "rameshwaram": "IXM", "ooty": "CJB",
    "kodaikanal": "IXM", "munnar": "COK", "wayanad": "CCJ", "hampi": "VDY", "khajuraho": "HJR",
    "puri": "BBI", "konark": "BBI", "mahabaleshwar": "PNQ", "lonavala": "PNQ", "kerala": "COK"
}

def _get_iata(place: str) -> str:
    if not place:
        return ""
    place_clean = place.lower().strip()
    if place_clean in CITY_AIRPORT_MAP:
        return CITY_AIRPORT_MAP[place_clean]
    if len(place_clean) == 3:
        return place_clean.upper()
    return place.upper()


def search_flights(
    origin: str = "",
    destination: str = "",
    date: str = "",
) -> list[dict]:
    """
    Search flights via AviationStack, with Circuit Breaker fallback to Tavily.

    Returns a list of dicts, each containing:
        airline, flight_number, departure_airport, departure_time,
        arrival_airport, arrival_time, status, booking_url
    """
    from backend.circuit_breaker import aviation_breaker

    if not AVIATIONSTACK_API_KEY:
        log.warning("AviationStack API key not configured")
        return _flight_fallback_tavily(origin, destination, date)

    # Circuit Breaker: if OPEN, skip the API entirely
    if not aviation_breaker.allow_request():
        log.warning("[CircuitBreaker] AviationStack circuit is OPEN — using Tavily fallback")
        aviation_breaker.record_fallback()
        return _flight_fallback_tavily(origin, destination, date)

    params: dict = {"access_key": AVIATIONSTACK_API_KEY, "limit": 5}
    if origin:
        params["dep_iata"] = _get_iata(origin)
    if destination:
        params["arr_iata"] = _get_iata(destination)

    try:
        resp = requests.get(API_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        aviation_breaker.record_success()
    except Exception as exc:
        log.error("AviationStack request failed: %s", exc)
        aviation_breaker.record_failure()
        return _flight_fallback_tavily(origin, destination, date)

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
                "travel_date": date,
            }
        )

    return flights


def _flight_fallback_tavily(origin: str, destination: str, date: str) -> list[dict]:
    """Fallback: search for flights via Tavily web search when AviationStack is down."""
    from backend.tools.tavily_tool import search_flights_web
    log.info("[Fallback] Searching flights via Tavily: %s → %s", origin, destination)
    try:
        return search_flights_web(origin, destination, date)
    except Exception as exc:
        log.error("[Fallback] Tavily flight search also failed: %s", exc)
        return []


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
