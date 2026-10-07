"""
Shared utility helpers used across all agent node modules.
"""

import re
import logging

log = logging.getLogger(__name__)


def extract_text(content) -> str:
    """Convert LLM response content to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and "text" in item
        )
    return str(content)


def clean_llm_json(raw: str) -> str:
    """
    Strip Qwen/thinking-model <think>...</think> blocks and extract the
    outermost JSON object or array from the remaining text.
    Works for both {} and [] payloads.
    """
    # Remove <think>...</think> blocks (including nested)
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Try to find outermost JSON object
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        return m.group(0)
    # Fallback: try array
    m = re.search(r'\[.*\]', cleaned, re.DOTALL)
    if m:
        return m.group(0)
    return cleaned


# ─────────────────────────────────────────────────────────────────────────────
# Booking helpers (shared by transport & hotel agents)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_pnr() -> str:
    """Generate a 15-digit PNR number."""
    import random
    return "".join(str(random.randint(0, 9)) for _ in range(15))


def _simulate_booking_status() -> str:
    """Simulate a booking status (70% confirmed, 30% waiting)."""
    import random
    return "confirmed" if random.random() < 0.7 else "waiting"


def _save_booking_to_supabase(
    user_id: str, booking_type: str, provider: str,
    pnr: str, travel_date: str, details: dict,
    status: str, trip_id: str = None
) -> bool:
    """Save a booking record to the Supabase bookings table."""
    try:
        from supabase import create_client
        from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY
        sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        record = {
            "user_id": user_id,
            "booking_type": booking_type,
            "provider_name": provider,
            "pnr_or_confirmation_number": pnr,
            "travel_date": travel_date,
            "status": status,
            "details": details,
        }
        if trip_id:
            record["trip_id"] = trip_id
        sb.table("bookings").insert(record).execute()
        return True
    except Exception as exc:
        log.error("Failed to save booking to Supabase: %s", exc)
        return False


def _send_telegram_booking_notification(
    user_id: str, booking_type: str,
    provider: str, pnr: str,
    travel_date: str, details: dict,
    status: str,
) -> None:
    """Send booking notification via Telegram if user is linked."""
    try:
        from supabase import create_client
        from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY, TELEGRAM_BOT_TOKEN
        if not TELEGRAM_BOT_TOKEN:
            return
        sb = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        resp = (
            sb.table("user_profiles")
            .select("telegram_chat_id")
            .eq("id", user_id)
            .execute()
        )
        if not resp.data or not resp.data[0].get("telegram_chat_id"):
            return
        chat_id = resp.data[0]["telegram_chat_id"]

        emoji = {"flight": "✈️", "train": "🚂", "hotel": "🏨"}.get(booking_type, "📋")
        status_emoji = "✅ Confirmed" if status == "confirmed" else "⏳ Waiting List"

        detail_lines = []
        if booking_type == "train":
            detail_lines.append(f"  🚂 Train: {details.get('train_name', 'N/A')}")
            detail_lines.append(f"  #️⃣ Number: {details.get('train_number', 'N/A')}")
            detail_lines.append(f"  📍 From: {details.get('departure_station', 'N/A')}")
            detail_lines.append(f"  📍 To: {details.get('arrival_station', 'N/A')}")
            detail_lines.append(f"  🎫 Class: {details.get('class', 'N/A')}")
        elif booking_type == "flight":
            detail_lines.append(f"  ✈️ Airline: {details.get('airline', 'N/A')}")
            detail_lines.append(f"  #️⃣ Flight: {details.get('flight_number', 'N/A')}")
            detail_lines.append(f"  📍 From: {details.get('departure_airport', 'N/A')}")
            detail_lines.append(f"  📍 To: {details.get('arrival_airport', 'N/A')}")
        elif booking_type == "hotel":
            detail_lines.append(f"  🏨 Hotel: {details.get('name', 'N/A')}")
            detail_lines.append(f"  ⭐ Rating: {details.get('rating', 'N/A')}")
            price = details.get('price', 'N/A')
            if isinstance(price, (int, float)):
                price = f"₹{price:,.0f}"
            detail_lines.append(f"  💰 Price: {price}")

        details_text = "\n".join(detail_lines)
        text = (
            f"{emoji} <b>TripPilot — Auto-Booked!</b>\n\n"
            f"<b>Type:</b> {booking_type.title()}\n"
            f"<b>Provider:</b> {provider}\n"
            f"<b>PNR:</b> <code>{pnr}</code>\n"
            f"<b>Status:</b> {status_emoji}\n"
            f"<b>Date:</b> {travel_date or 'TBD'}\n\n"
            f"<b>Details:</b>\n{details_text}\n\n"
            f"{'🎉 Your booking is confirmed! Have a great trip!' if status == 'confirmed' else '⏳ Your ticket is on the waiting list. We will notify you when confirmed.'}"
        )

        import requests as req
        API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/"
        req.post(
            API_URL + "sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as exc:
        log.warning("Failed to send Telegram booking notification: %s", exc)
