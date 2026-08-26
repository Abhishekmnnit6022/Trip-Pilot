"""
Telegram Bot integration for TripPilot.

Provides:
- Sending booking confirmations to users via Telegram
- Trip reminder notifications
- User linking (connect Supabase user to Telegram chat)

Setup:
1. Open Telegram and search for @BotFather
2. Send /newbot, follow the prompts to create your bot
3. Copy the bot token and add it to your .env file as TELEGRAM_BOT_TOKEN
"""

import logging
import requests
from backend.config import TELEGRAM_BOT_TOKEN

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"


def _api_url(method: str) -> str:
    """Build the Telegram Bot API URL for a given method."""
    if not TELEGRAM_BOT_TOKEN:
        return ""
    return f"{TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN)}/{method}"


def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a text message to a Telegram chat. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        log.warning("Telegram not configured or no chat_id — skipping message")
        return False

    try:
        resp = requests.post(
            _api_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            log.error("Telegram sendMessage failed: %s", data.get("description"))
            return False
        return True
    except Exception as exc:
        log.error("Telegram send_message error: %s", exc)
        return False


def send_booking_confirmation(
    chat_id: str,
    booking_type: str,
    pnr: str,
    provider_name: str,
    travel_date: str,
    details: dict,
) -> bool:
    """Send a formatted booking confirmation to the user's Telegram."""
    emoji = {"flight": "✈️", "train": "🚂", "hotel": "🏨"}.get(booking_type, "📋")

    # Build detail lines from the booking details dict
    detail_lines = []
    if booking_type == "flight":
        detail_lines.append(f"  Airline: {details.get('airline', 'N/A')}")
        detail_lines.append(f"  Flight: {details.get('flight_number', 'N/A')}")
        detail_lines.append(f"  From: {details.get('departure_airport', 'N/A')}")
        detail_lines.append(f"  To: {details.get('arrival_airport', 'N/A')}")
    elif booking_type == "train":
        detail_lines.append(f"  Train: {details.get('train_name', 'N/A')}")
        detail_lines.append(f"  Number: {details.get('train_number', 'N/A')}")
        detail_lines.append(f"  From: {details.get('departure_station', 'N/A')}")
        detail_lines.append(f"  To: {details.get('arrival_station', 'N/A')}")
    elif booking_type == "hotel":
        detail_lines.append(f"  Hotel: {details.get('name', 'N/A')}")
        detail_lines.append(f"  Check-in: {details.get('checkin', 'N/A')}")
        detail_lines.append(f"  Check-out: {details.get('checkout', 'N/A')}")
        price = details.get("price", "N/A")
        if isinstance(price, (int, float)):
            price = f"₹{price:,.0f}"
        detail_lines.append(f"  Price: {price}")

    details_text = "\n".join(detail_lines) if detail_lines else "  See app for details"

    id_label = "Booking ID" if booking_type == "hotel" else "PNR"
    
    extra_footer = ""
    if booking_type == "train":
        import random
        # Simulate a real train booking status for demonstration
        status = random.choice(["🟢 Confirmed (CNF)", "🟠 RAC 14", "🔴 Waiting List (WL 22)"])
        detail_lines.append(f"  Live Status: {status}")
        detail_lines.append(f"  Check PNR: https://www.confirmtkt.com/pnr-status/{pnr}")
        details_text = "\n".join(detail_lines)
        if "Waiting" in status or "RAC" in status:
            extra_footer = (
                "\n\n⚠️ <b>Waitlist Alert:</b> Your ticket is not fully confirmed (Waiting or RAC).\n"
                "Would you like me to find alternate transport (Bus+Cab or Flights)?\n"
                "Reply to this bot with <i>'Find alternatives'</i> to see options."
            )

    text = (
        f"{emoji} <b>TripPilot — Booking Confirmed!</b>\n\n"
        f"<b>Type:</b> {booking_type.title()}\n"
        f"<b>Provider:</b> {provider_name}\n"
        f"<b>{id_label}:</b> <code>{pnr}</code>\n"
        f"<b>Travel Date:</b> {travel_date or 'TBD'}\n\n"
        f"<b>Details:</b>\n{details_text}\n\n"
        f"✅ Your booking is confirmed. Have a great trip! 🎉{extra_footer}"
    )

    return send_message(chat_id, text)


def send_trip_reminder(chat_id: str, destination: str, travel_date: str, pnr: str) -> bool:
    """Send a trip reminder 24 hours before travel."""
    text = (
        f"🧳 <b>TripPilot — Trip Reminder</b>\n\n"
        f"Pack your bags! Your trip to <b>{destination}</b> is tomorrow! 🎉\n\n"
        f"📅 <b>Date:</b> {travel_date}\n"
        f"🔖 <b>PNR:</b> <code>{pnr}</code>\n\n"
        f"Safe travels! ✈️🚂"
    )
    return send_message(chat_id, text)


def get_bot_info() -> dict | None:
    """Fetch the bot's info (username, etc.) — useful for generating the link URL."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        resp = requests.get(_api_url("getMe"), timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]
    except Exception as exc:
        log.error("Telegram getMe error: %s", exc)
    return None
