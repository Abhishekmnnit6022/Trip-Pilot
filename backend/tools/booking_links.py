"""
Generate booking redirect URLs for external travel services.
Users click these to book on the actual platform (IRCTC, MakeMyTrip, Booking.com, etc.).
"""

from urllib.parse import quote_plus
from datetime import datetime


def get_irctc_url() -> str:
    """IRCTC doesn't support deep-linking; returns the train search page."""
    return "https://www.irctc.co.in/nget/train-search"


def get_makemytrip_flight_url(
    origin_code: str, dest_code: str, date: str
) -> str:
    """
    MakeMyTrip flight search URL.
    `date` should be YYYY-MM-DD; it is converted to DD/MM/YYYY for the URL.
    """
    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        formatted = dt.strftime("%d/%m/%Y")
    except ValueError:
        formatted = date
    return (
        f"https://www.makemytrip.com/flight/search?"
        f"itinerary={origin_code}-{dest_code}-{formatted}"
        f"&tripType=O&paxType=A-1_C-0_I-0&cabinClass=E"
    )


def get_skyscanner_url(origin: str, destination: str, date: str) -> str:
    """Skyscanner search URL (uses city names)."""
    return (
        f"https://www.skyscanner.co.in/transport/flights/"
        f"{quote_plus(origin)}/{quote_plus(destination)}/{date}/"
    )


def get_booking_hotel_url(
    destination: str, checkin: str, checkout: str
) -> str:
    """Booking.com hotel search URL."""
    return (
        f"https://www.booking.com/searchresults.html?"
        f"ss={quote_plus(destination)}&checkin={checkin}&checkout={checkout}"
    )


def get_makemytrip_hotel_url(
    destination: str, checkin: str, checkout: str
) -> str:
    """MakeMyTrip hotel search URL."""
    return (
        f"https://www.makemytrip.com/hotels/hotel-listing/"
        f"?city={quote_plus(destination)}&checkin={checkin}&checkout={checkout}"
    )


def get_goibibo_train_url() -> str:
    """Goibibo train booking page (no deep-link support)."""
    return "https://www.goibibo.com/trains/"
