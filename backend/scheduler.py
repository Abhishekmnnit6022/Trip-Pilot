"""
Background scheduler for trip reminders.

Runs a daily check: if any booking has a travel_date within the next 24 hours,
sends the user a Telegram reminder.
"""

import logging
from datetime import datetime, timedelta
from contextlib import suppress

from supabase import create_client
from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY
from backend.telegram_service import send_trip_reminder

log = logging.getLogger(__name__)

_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def check_and_send_reminders():
    """
    Query bookings where travel_date is tomorrow and the user has a
    linked Telegram account. Send each user a reminder.
    """
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.utcnow().strftime("%Y-%m-%d")

    log.info("Checking reminders for travel dates: %s to %s", today, tomorrow)

    try:
        # Get confirmed bookings with travel_date = tomorrow
        bookings_resp = (
            _supabase.table("bookings")
            .select("*")
            .eq("travel_date", tomorrow)
            .eq("status", "confirmed")
            .execute()
        )
        bookings = bookings_resp.data or []

        if not bookings:
            log.info("No upcoming trips for tomorrow")
            return

        # Collect unique user IDs
        user_ids = list({b["user_id"] for b in bookings})

        # Fetch profiles with telegram_chat_id
        profiles_resp = (
            _supabase.table("user_profiles")
            .select("id, telegram_chat_id, full_name")
            .in_("id", user_ids)
            .execute()
        )
        profiles = {p["id"]: p for p in (profiles_resp.data or [])}

        sent_count = 0
        for booking in bookings:
            user_id = booking["user_id"]
            profile = profiles.get(user_id)
            if not profile or not profile.get("telegram_chat_id"):
                continue

            chat_id = profile["telegram_chat_id"]
            details = booking.get("details") or {}
            destination = (
                details.get("arrival_airport")
                or details.get("arrival_station")
                or details.get("name")
                or "your destination"
            )

            success = send_trip_reminder(
                chat_id=chat_id,
                destination=destination,
                travel_date=str(booking["travel_date"]),
                pnr=booking["pnr_or_confirmation_number"],
            )

            if success:
                sent_count += 1

        log.info("Sent %d reminder(s) for %d booking(s)", sent_count, len(bookings))

    except Exception as exc:
        log.error("Reminder check failed: %s", exc)
