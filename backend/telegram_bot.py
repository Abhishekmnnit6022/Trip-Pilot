"""
Interactive Telegram Bot Polling Loop

This module runs a background thread that constantly checks for new messages
sent to the TripPilot Telegram Bot. It handles:

  1. /start command   -> Professional welcome message, asks for phone number
  2. Phone number     -> Matches against user_profiles, asks for DOB verification
  3. DOB verification -> Links Telegram chat_id to the user's account
  4. Menu buttons     -> View Flights, Trains, Hotels, Plan New Trip
  5. Emergency Contact-> Set/update emergency contact info
  6. SOS Emergency    -> 30-second confirmation flow, auto-calls if no response

State Machine:
  LINK_STATE[chat_id] stores the current linking/verification state per user.
  SOS_STATE[chat_id]  stores the active SOS countdown state per user.
"""

import os
import time
import threading
import requests
import logging
from datetime import datetime
from supabase import create_client

from backend.config import TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY

log = logging.getLogger(__name__)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/"
_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# ── In-memory state machines ─────────────────────────────────────────────────

# Account linking state: {chat_id: {"user_id": "...", "expected_dob": "YYYY-MM-DD", "full_name": "..."}}
LINK_STATE = {}

# SOS countdown state: {chat_id: {"user_id": "...", "timer": threading.Timer, "active": True}}
SOS_STATE = {}

# Emergency contact setup state: {chat_id: {"step": "name"|"phone", "name": "..."}}
EC_STATE = {}

# End-trip state: {chat_id: {"trips": [{id, name}, ...], "user_id": "..."}}
TRIP_END_STATE = {}


def send_message(chat_id: int, text: str, reply_markup: dict = None) -> None:
    """
    Send a text message to a Telegram chat.

    Args:
        chat_id:      Telegram chat ID to send the message to.
        text:         Message text (supports HTML parse_mode).
        reply_markup: Optional keyboard markup (ReplyKeyboardMarkup or ReplyKeyboardRemove).
    """
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(API_URL + "sendMessage", json=payload, timeout=10)
    except Exception as e:
        log.error("Telegram send error: %s", e)


def send_photo(chat_id: int, photo: str, caption: str, reply_markup: dict = None) -> None:
    """
    Send a photo to a Telegram chat with an optional caption.

    Args:
        chat_id:      Telegram chat ID.
        photo:        Photo URL or file_id.
        caption:      Photo caption (supports HTML).
        reply_markup: Optional keyboard markup.
    """
    payload = {"chat_id": chat_id, "photo": photo, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(API_URL + "sendPhoto", json=payload, timeout=10)
    except Exception as e:
        log.error("Telegram sendPhoto error: %s", e)


def _get_linked_user_id(chat_id: int) -> str | None:
    """
    Look up the Supabase user_id for a given Telegram chat_id.

    Args:
        chat_id: The Telegram chat ID to look up.

    Returns:
        The user's UUID string if linked, or None if not found.
    """
    try:
        resp = _supabase.rpc("bot_get_profiles").execute()
        profiles = resp.data or []
    except Exception:
        resp = _supabase.table("user_profiles").select("id, telegram_chat_id").execute()
        profiles = resp.data or []

    for p in profiles:
        if p.get("telegram_chat_id") == str(chat_id):
            return p["id"]
    return None


def _get_main_menu_keyboard() -> dict:
    """
    Build the main menu reply keyboard shown after successful account linking.

    Returns:
        A Telegram ReplyKeyboardMarkup dict with all menu options.
    """
    return {
        "keyboard": [
            [{"text": "🎒 My Trips"}, {"text": "🌍 Plan New Trip"}],
            [{"text": "📞 Emergency Contact"}, {"text": "🏁 End Trip"}],
            [{"text": "🆘 SOS EMERGENCY 🆘"}]
        ],
        "resize_keyboard": True
    }


def _handle_sos_timeout(chat_id: int, location_link: str = "") -> None:
    """
    Called automatically after 30 seconds if the user does NOT reply "YES" to the SOS prompt,
    or called immediately if the user shares their live location.

    This function:
      1. Checks if the SOS is still active (user didn't cancel).
      2. Fetches the user's emergency contact from the database.
      3. Initiates an emergency SMS via Textbelt.
      4. Notifies the user on Telegram about the action taken.

    Args:
        chat_id: The Telegram chat ID of the user who triggered SOS.
        location_link: Optional Google Maps link if the user shared their location.
    """
    state = SOS_STATE.get(chat_id)
    if not state or not state.get("active"):
        return  # SOS was cancelled

    user_id = state["user_id"]
    SOS_STATE.pop(chat_id, None)

    # Fetch emergency contact
    try:
        resp = _supabase.rpc("bot_get_emergency_contact", {"p_user_id": user_id}).execute()

        if not resp.data:
            send_message(chat_id, "❌ Could not find your profile. Please contact emergency services directly.")
            return

        profile = resp.data[0]
        ec_name = profile.get("emergency_contact_name", "")
        ec_phone = profile.get("emergency_contact_phone", "")
        user_name = profile.get("full_name", "A TripPilot user")

        if not ec_phone:
            send_message(
                chat_id,
                "⚠️ <b>No emergency contact found!</b>\n\n"
                "You haven't set an emergency contact yet. "
                "Please use '📞 Emergency Contact' to set one up, "
                "or call local emergency services directly."
            )
            return

        # Try to fetch the most recent booking for location/trip details
        trip_details = ""
        if location_link:
            trip_details = f"Live GPS Location: {location_link}"
        else:
            try:
                b_resp = _supabase.table("bookings").select(
                    "booking_type, provider_name, pnr_or_confirmation_number, details"
                ).eq("user_id", user_id).order("booking_date", desc=True).limit(1).execute()
                
                if b_resp.data:
                    latest_trip = b_resp.data[0]
                    bt = latest_trip.get('booking_type', '')
                    dest = latest_trip.get('details', {}).get('arrival_airport') or \
                           latest_trip.get('details', {}).get('arrival_station') or \
                           latest_trip.get('details', {}).get('name') or \
                           latest_trip.get('provider_name')
                    
                    trip_details = f"Traveling via {bt} to/at '{dest}' (PNR: {latest_trip.get('pnr_or_confirmation_number')})"
            except Exception as e:
                log.warning("Could not fetch latest booking for SOS details: %s", e)


        # Attempt to send completely free SMS via Textbelt
        from backend.sos_service import send_emergency_sms_free

        send_message(
            chat_id,
            f"🚨 <b>SOS ACTIVATED!</b>\n\n"
            f"No response received. Sending an emergency SMS with your trip details "
            f"to <b>{ec_name}</b> ({ec_phone}) now…"
        )

        sms_success = send_emergency_sms_free(ec_phone, user_name, trip_details)
        
        if sms_success:
            send_message(chat_id, "✅ <b>Emergency SMS sent successfully</b> to your contact.", _get_main_menu_keyboard())
        else:
            send_message(
                chat_id,
                "⚠️ Could not reach your emergency contact via SMS (Free tier limit reached or invalid number). "
                "Please contact local emergency services directly:\n"
                "🇮🇳 India: <b>112</b> | 🇺🇸 USA: <b>911</b>",
                _get_main_menu_keyboard()
            )

    except Exception as exc:
        log.error("SOS handler error: %s", exc)
        send_message(chat_id, "❌ An error occurred during SOS. Please call emergency services directly.", _get_main_menu_keyboard())


def handle_message(message: dict) -> None:
    """
    Process a single incoming Telegram message through the state machine.

    This is the main message router. It checks the message text against
    known commands, state flows, and menu buttons, then delegates to the
    appropriate handler.

    Args:
        message: The raw Telegram message dict from the getUpdates API.
    """
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # Check for live location sharing (triggers immediate SOS with location)
    if "location" in message:
        lat = message["location"]["latitude"]
        lon = message["location"]["longitude"]
        if chat_id in SOS_STATE and SOS_STATE[chat_id].get("active"):
            # Cancel the 30-sec timer
            timer = SOS_STATE[chat_id].get("timer")
            if timer:
                timer.cancel()
            
            # Formulate the Google Maps link
            location_link = f"https://www.google.com/maps?q={lat},{lon}"
            
            # Immediately trigger the SOS with the live location
            _handle_sos_timeout(chat_id, location_link=location_link)
            return

    if text in ["🚨 SOS Emergency", "🆘 SOS EMERGENCY 🆘", "🆘 SOS EMERGENCY", "📞 Emergency Contact", "🏁 End Trip"]:
        LINK_STATE.pop(chat_id, None)
        EC_STATE.pop(chat_id, None)
        # Don't clear TRIP_END_STATE here if user is clicking End Trip
        if text != "🏁 End Trip":
            TRIP_END_STATE.pop(chat_id, None)

    # ── 1. /start command ────────────────────────────────────────────────────
    if text.startswith("/start"):
        LINK_STATE.pop(chat_id, None)
        EC_STATE.pop(chat_id, None)
        # Cancel any active SOS
        if chat_id in SOS_STATE:
            SOS_STATE[chat_id]["active"] = False
            SOS_STATE.pop(chat_id, None)

        # Check for deep-link payload (e.g., /start <payload>)
        parts = text.split()
        if len(parts) > 1:
            payload = parts[1].strip()
            target_user_id = payload
            
            import base64
            try:
                # Convert base64url back to standard base64
                std_b64 = payload.replace('-', '+').replace('_', '/')
                # Add padding if missing
                padded = std_b64 + '=' * (-len(std_b64) % 4)
                decoded = base64.b64decode(padded).decode('utf-8')
                
                if "_" in decoded:
                    phone_part, dob_part = decoded.split("_", 1)
                    # Use RPC to get profiles and find match
                    try:
                        resp = _supabase.rpc("bot_get_profiles").execute()
                        profiles = resp.data or []
                    except Exception:
                        resp = _supabase.table("user_profiles").select("id, phone_number, birth_date").execute()
                        profiles = resp.data or []
                        
                    for p in profiles:
                        db_phone = (p.get("phone_number") or "").replace(" ", "").replace("+", "").replace("-", "")
                        db_dob = (p.get("birth_date") or "")
                        if db_phone and phone_part.endswith(db_phone[-10:]) and db_dob == dob_part:
                            target_user_id = p["id"]
                            break
            except Exception as e:
                # Fallback to assuming payload is directly a user_id (UUID)
                pass
                
            try:
                # Use the RPC to bypass RLS and link instantly
                _supabase.rpc("bot_link_telegram", {"p_user_id": target_user_id, "p_chat_id": str(chat_id)}).execute()
                
                send_message(
                    chat_id, 
                    "✅ <b>Account Linked Successfully!</b>\n\n"
                    "You are now ready to receive live booking updates, interactive itineraries, and instant SOS alerts directly in Telegram.", 
                    _get_main_menu_keyboard()
                )
                return
            except Exception as e:
                log.error("Failed to auto-link account via deep link: %s", e)

        reply_markup = {"remove_keyboard": True}

        welcome_text = (
            "🌍 <b>Welcome to TripPilot!</b> ✈️\n\n"
            "I am your ultimate AI Travel Planner. I can help you manage your "
            "Flights, Trains, Hotels, and personalized Itineraries instantly.\n\n"
            "To unlock all features, please securely link your account by typing "
            "your <b>registered Phone Number</b> below "
            "(exactly as it appears in the TripPilot app)."
        )

        send_message(chat_id, welcome_text, reply_markup)
        return

    # ── 2. Emergency Contact Setup Flow ──────────────────────────────────────
    if chat_id in EC_STATE:
        ec = EC_STATE[chat_id]

        if text.lower() == "cancel":
            EC_STATE.pop(chat_id, None)
            send_message(chat_id, "Emergency contact setup cancelled.", _get_main_menu_keyboard())
            return

        if ec["step"] == "phone":
            # User is entering the contact phone number
            clean = text.replace(" ", "").replace("-", "")
            if not (clean.startswith("+") and len(clean) >= 10):
                send_message(chat_id, "⚠️ Please enter a valid phone with country code (e.g., +919876543210)")
                return

            user_id = _get_linked_user_id(chat_id)
            if not user_id:
                EC_STATE.pop(chat_id, None)
                send_message(chat_id, "⚠️ Your account is not linked. Type /start first.")
                return

            # Save to database using RPC to bypass RLS
            try:
                _supabase.rpc("bot_set_emergency_contact", {
                    "p_user_id": user_id, 
                    "p_phone": clean
                }).execute()

                EC_STATE.pop(chat_id, None)
                send_message(
                    chat_id,
                    f"✅ <b>Emergency Contact Saved!</b>\n\n"
                    f"📞 Phone: <code>{clean}</code>\n\n"
                    f"In an emergency, tap <b>🆘 SOS EMERGENCY 🆘</b> and "
                    f"if you don't respond within 30 seconds, "
                    f"we'll automatically notify {clean}.",
                    _get_main_menu_keyboard()
                )
            except Exception as exc:
                log.error("Failed to save emergency contact: %s", exc)
                EC_STATE.pop(chat_id, None)
                send_message(chat_id, "❌ Failed to save. Please try again.")
            return

    # ── 3. SOS Confirmation Check ────────────────────────────────────────────
    if chat_id in SOS_STATE and SOS_STATE[chat_id].get("active"):
        if text.upper() in ["YES", "Y", "I'M OK", "IM OK", "OK", "FINE", "SAFE", "✅ I'M OK (CANCEL SOS)", "CANCEL"]:
            # User confirmed they are safe — cancel the SOS
            SOS_STATE[chat_id]["active"] = False
            timer = SOS_STATE[chat_id].get("timer")
            if timer:
                timer.cancel()
            SOS_STATE.pop(chat_id, None)
            send_message(
                chat_id,
                "✅ <b>SOS Cancelled</b>\n\n"
                "Glad you're safe! The emergency alert has been cancelled. 💚",
                _get_main_menu_keyboard()
            )
            return

    # ── 4. Account Linking DOB Verification ──────────────────────────────────
    if chat_id in LINK_STATE:
        state = LINK_STATE[chat_id]

        if text.lower() == "cancel" or text == "/start":
            LINK_STATE.pop(chat_id, None)
            send_message(chat_id, "Linking cancelled. Type /start to try again.")
            return

        expected_dob = state.get("expected_dob")

        if not expected_dob:
            LINK_STATE.pop(chat_id, None)
            send_message(
                chat_id,
                "❌ Security Error: Your profile does not have a Date of Birth set. "
                "Please update your profile on the TripPilot website first, then type /start here."
            )
            return

        if text == expected_dob:
            # ✅ DOB matches — link the account
            try:
                _supabase.rpc("bot_link_telegram", {"p_user_id": state["user_id"], "p_chat_id": str(chat_id)}).execute()
            except Exception as e:
                log.error("RPC Error linking telegram: %s", e)
                _supabase.table("user_profiles").update({"telegram_chat_id": str(chat_id)}).eq("id", state["user_id"]).execute()

            LINK_STATE.pop(chat_id, None)

            send_message(
                chat_id,
                f"✅ <b>Verification Successful!</b>\n\n"
                f"Welcome back, {state['full_name']}! Your Telegram is now "
                f"securely linked to your TripPilot account.\n\n"
                f"Use the menu below to view your bookings and manage your trips.",
                _get_main_menu_keyboard()
            )
        else:
            send_message(
                chat_id,
                "❌ <b>Incorrect Date of Birth.</b>\n\n"
                "Please try again (Format: YYYY-MM-DD) or type 'cancel' to restart."
            )
        return

    # ── 5. Menu Button: Emergency Contact ────────────────────────────────────
    if text == "📞 Emergency Contact":
        user_id = _get_linked_user_id(chat_id)
        if not user_id:
            send_message(chat_id, "⚠️ Your account is not linked yet. Please type /start to link your account.")
            return

        # Show current contact if exists using RPC
        try:
            resp = _supabase.rpc("bot_get_emergency_contact", {"p_user_id": user_id}).execute()

            if resp.data:
                ec_phone = resp.data[0].get("emergency_contact_phone", "")
                if ec_phone:
                    send_message(
                        chat_id,
                        f"📞 <b>Current Emergency Contact:</b>\n\n"
                        f"📱 Phone: <code>{ec_phone}</code>\n\n"
                        f"To update, please enter the new <b>Phone Number</b> below.\n"
                        f"Include the country code (e.g., +919876543210).\n\n"
                        f"Type 'cancel' to keep the current contact."
                    )
                else:
                    send_message(
                        chat_id,
                        "📞 <b>Set Emergency Contact</b>\n\n"
                        "You haven't set an emergency contact yet.\n\n"
                        "Please enter their <b>Phone Number</b> below.\n"
                        "Include the country code (e.g., +919876543210).\n\n"
                        "Type 'cancel' to abort."
                    )
        except Exception:
            send_message(chat_id, "Please enter the <b>Phone Number</b> of your emergency contact below (with country code):")

        EC_STATE[chat_id] = {"step": "phone"}
        return

    # ── 6. Menu Button: SOS Emergency ────────────────────────────────────────
    if text in ["🚨 SOS Emergency", "🆘 SOS EMERGENCY 🆘", "🆘 SOS EMERGENCY"]:
        user_id = _get_linked_user_id(chat_id)
        if not user_id:
            send_message(chat_id, "⚠️ Your account is not linked yet. Type /start first.")
            return

        # Check if emergency contact exists using RPC
        try:
            resp = _supabase.rpc("bot_get_emergency_contact", {"p_user_id": user_id}).execute()
            ec_phone = resp.data[0].get("emergency_contact_phone", "") if resp.data else ""
        except Exception:
            ec_phone = ""

        if not ec_phone:
            send_message(
                chat_id,
                "⚠️ <b>No Emergency Contact Set!</b>\n\n"
                "Please set up an emergency contact first using the "
                "'📞 Emergency Contact' button before using SOS.",
                _get_main_menu_keyboard()
            )
            return

        # Start the SOS countdown
        send_message(
            chat_id,
            "🚨🚨🚨 <b>SOS EMERGENCY ALERT</b> 🚨🚨🚨\n\n"
            "Are you OK? Please reply <b>YES</b> within <b>30 seconds</b> "
            "to cancel this alert.\n\n"
            "📍 <b>Want to send your exact location?</b> Tap the button below!\n\n"
            "⏰ If no response is received, your emergency contact "
            "will be automatically notified with your last known trip details.",
            {
                "keyboard": [
                    [{"text": "📍 Share Location (Send SOS Now)", "request_location": True}],
                    [{"text": "✅ I'm OK (Cancel SOS)"}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True
            }
        )

        # Schedule the auto-call after 30 seconds
        timer = threading.Timer(30.0, _handle_sos_timeout, args=[chat_id])
        timer.daemon = True
        timer.start()

        SOS_STATE[chat_id] = {
            "user_id": user_id,
            "timer": timer,
            "active": True,
        }
        return

    # ── 7. Menu Buttons: View Bookings ───────────────────────────────────────
    # (Bookings are now handled inside the 'My Trips' inline menu)

    # ── 8. Menu Button: End Trip ──────────────────────────────────────────
    if text == "🏁 End Trip":
        user_id = _get_linked_user_id(chat_id)
        if not user_id:
            send_message(chat_id, "⚠️ Your account is not linked yet. Type /start first.")
            return

        # Fetch active trips
        try:
            from backend.bot_trip_features import get_booked_trips_for_bot
            trips = get_booked_trips_for_bot(user_id)
        except Exception as exc:
            log.error("Failed to fetch active trips: %s", exc)
            send_message(chat_id, "❌ Could not fetch your trips. Please try again.")
            return

        if not trips:
            send_message(chat_id, "You don't have any active trips right now.", _get_main_menu_keyboard())
            return

        # Store trips in state and show selection keyboard
        TRIP_END_STATE[chat_id] = {"trips": trips, "user_id": user_id}

        keyboard = [[{"text": f"🏁 {t['name']}"}] for t in trips]
        keyboard.append([{"text": "❌ Cancel"}])

        send_message(
            chat_id,
            "🏁 <b>End a Trip</b>\n\n"
            "Select the trip you want to mark as completed:\n"
            "(An expense report PDF will be generated and sent to you)",
            {"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": True}
        )
        return

    # ── 8b. Trip End Selection Handler ────────────────────────────────────
    if chat_id in TRIP_END_STATE:
        state = TRIP_END_STATE[chat_id]

        if text == "❌ Cancel":
            TRIP_END_STATE.pop(chat_id, None)
            send_message(chat_id, "Trip ending cancelled.", _get_main_menu_keyboard())
            return

        # Match the selected trip name
        selected_name = text.replace("🏁 ", "").strip()
        matched_trip = None
        for t in state["trips"]:
            if t["name"] == selected_name:
                matched_trip = t
                break

        if not matched_trip:
            send_message(chat_id, "⚠️ Please select a trip from the buttons above, or tap ❌ Cancel.")
            return

        trip_id = matched_trip["id"]
        user_id = state["user_id"]
        TRIP_END_STATE.pop(chat_id, None)

        send_message(chat_id, f"⏳ Completing <b>{matched_trip['name']}</b> and generating your expense report...")

        # We extracted the logic into a separate function so it can be reused from bot_trip_features.py
        _generate_and_send_pdf(chat_id, user_id, trip_id)
        return

    # ── 9. Menu Button: My Trips (Active Context) ────────────────────────────
    if text == "🎒 My Trips":
        user_id = _get_linked_user_id(chat_id)
        if not user_id:
            send_message(chat_id, "⚠️ Your account is not linked yet. Type /start first.")
            return
            
        from backend.bot_trip_features import handle_my_trips
        handle_my_trips(chat_id, user_id)
        return

    # ── 10. Menu Button: Plan New Trip ───────────────────────────────────────
    if text == "🌍 Plan New Trip":
        send_message(
            chat_id,
            "To generate magical AI itineraries and book new trips, "
            "please visit the TripPilot web app! 🚀\n\n"
            "🌐 <b>Website:</b> https://trip-pilot-twin.vercel.app"
        )
        return

    # ── 10. Phone Number Input (Account Linking Step 1) ───────────────────────
    clean_text = text.replace(" ", "").replace("+", "").replace("-", "")
    if clean_text.isdigit() and len(clean_text) >= 8:
        # Fetch all profiles to match against
        try:
            resp = _supabase.rpc("bot_get_profiles").execute()
            profiles = resp.data or []
        except Exception:
            resp = _supabase.table("user_profiles").select(
                "id, phone_number, full_name, birth_date, telegram_chat_id"
            ).execute()
            profiles = resp.data or []

        matched_user = None
        for p in profiles:
            db_phone = (p.get("phone_number") or "").replace(" ", "").replace("+", "").replace("-", "")
            if db_phone and clean_text.endswith(db_phone[-10:]):
                matched_user = p
                break

        if matched_user:
            # Move to DOB verification step
            LINK_STATE[chat_id] = {
                "user_id": matched_user["id"],
                "expected_dob": matched_user.get("birth_date"),
                "full_name": matched_user.get("full_name", "Traveler")
            }
            send_message(
                chat_id,
                "🔒 <b>Security Verification</b>\n\n"
                f"Found an account for {matched_user.get('full_name', 'Traveler')}. "
                "To prove this is you, please enter your <b>Date of Birth</b> "
                "exactly as it appears on your profile.\n\n"
                "Format: <code>YYYY-MM-DD</code> (e.g. 1995-08-25)"
            )
        else:
            send_message(
                chat_id,
                "❌ <b>Account Not Found</b>\n\n"
                "I couldn't find a TripPilot account linked to this phone number. "
                "Please make sure you have added your phone number in the "
                "<b>My Profile</b> section of the TripPilot web app, then try again."
            )
        return

    # ── 11. Menu Command & Fallback ──────────────────────────────────────────
    user_id = _get_linked_user_id(chat_id)
    if user_id and text == "/menu":
        send_message(chat_id, "Here is your menu:", _get_main_menu_keyboard())
        return

    if text == "🌍 Plan New Trip":
        send_message(
            chat_id,
            "🌍 <b>Ready to plan your next adventure?</b>\n\n"
            "TripPilot's powerful AI agents handle flight mapping, train schedules, and hotel booking seamlessly.\n\n"
            "👉 <b>Open the Web Dashboard to start:</b>\n"
            "https://trip-pilot-0h4x.onrender.com\n\n"
            "<i>(Once your trip is created, you can track expenses and manage it right here!)</i>",
            _get_main_menu_keyboard()
        )
        return
        
    if user_id and not (chat_id in LINK_STATE or chat_id in EC_STATE or chat_id in SOS_STATE or chat_id in TRIP_END_STATE):
        # Fallback: check if the user has an active trip and this is an ad-hoc expense
        from backend.bot_trip_features import handle_ad_hoc_expense
        handled = handle_ad_hoc_expense(chat_id, user_id, text)
        if not handled:
            send_message(
                chat_id,
                "I didn't understand that. You can send an expense like 'Rs 500 for taxi' if you have an active trip selected, or use the menu below.",
                _get_main_menu_keyboard()
            )


def poll_telegram_forever() -> None:
    """
    Background polling loop that fetches new Telegram messages via Long Polling.

    This function runs indefinitely in a daemon thread. It uses Telegram's
    getUpdates API with a 30-second long-poll timeout, processes each message
    through handle_message(), and gracefully handles connection errors.

    Note: Only ONE instance of this function should run at a time. Running
    multiple instances will cause 409 Conflict errors from Telegram's API.
    """
    if not TELEGRAM_BOT_TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN is missing. Interactive Telegram bot is disabled.")
        return

    offset = 0
    log.info("🚀 Interactive Telegram Bot is now polling for messages...")

    while True:
        try:
            resp = requests.get(
                API_URL + "getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            )

            if resp.ok:
                updates = resp.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        threading.Thread(target=handle_message, args=(update["message"],), daemon=True).start()
                    elif "callback_query" in update:
                        from backend.bot_trip_features import handle_callback_query
                        threading.Thread(target=handle_callback_query, args=(update["callback_query"],), daemon=True).start()
            else:
                log.error("Telegram API Error: %s", resp.text)
                time.sleep(5)

        except Exception as e:
            log.error("Telegram polling error (connection issue): %s", e)
            time.sleep(5)


def _generate_and_send_pdf(chat_id: int, user_id: str, trip_id: str):
    """Generate and send the final PDF report for a trip via Telegram."""
    import tempfile
    import traceback
    
    trip_id = str(trip_id)
    
    # 0. Fetch the trip
    try:
        t_resp = _supabase.rpc("bot_get_trip_by_id", {"p_trip_id": trip_id}).execute()
        if not t_resp.data:
            log.error("Trip not found for PDF generation.")
            return
        matched_trip = t_resp.data[0]
    except Exception as exc:
        log.error("Failed to fetch trip: %s", exc)
        return
        
    # 1. Mark trip as completed
    try:
        _supabase.rpc("bot_complete_trip", {"p_trip_id": trip_id}).execute()
    except Exception as exc:
        log.error("Failed to complete trip: %s", exc)
        send_message(chat_id, "❌ Failed to complete the trip. Please try again.", _get_main_menu_keyboard())
        return

    # 2. Fetch all bookings for this trip
    try:
        b_resp = _supabase.rpc("bot_get_trip_bookings", {"p_trip_id": trip_id}).execute()
        bookings = b_resp.data or []
    except Exception as exc:
        log.error("Failed to fetch trip bookings: %s", exc)
        bookings = []

    # 2b. Fetch custom expenses for this trip
    try:
        e_resp = _supabase.table("trip_expenses").select("*").eq("trip_id", trip_id).execute()
        custom_expenses = e_resp.data or []
    except Exception as exc:
        log.error("Failed to fetch custom expenses: %s", exc)
        custom_expenses = []

    # 3. Fetch user name
    try:
        name_resp = _supabase.rpc("bot_get_user_name", {"p_user_id": user_id}).execute()
        traveler_name = name_resp.data or "Traveler"
    except Exception:
        traveler_name = "Traveler"

    # 4. Generate PDF expense report
    try:
        from backend.pdf_report import generate_trip_report

        pdf_bytes = generate_trip_report(
            trip_name=matched_trip["name"],
            traveler_name=traveler_name,
            bookings=bookings,
            custom_expenses=custom_expenses,
            trip_created=str(matched_trip.get("created_at", "")),
            trip_completed=datetime.now().isoformat(),
        )

        # Write PDF to temp file and send via Telegram
        safe_name = matched_trip["name"].replace(" ", "_")[:30]
        tmp_path = os.path.join(tempfile.gettempdir(), f"TripPilot_{safe_name}_Report.pdf")
        with open(tmp_path, "wb") as f:
            f.write(pdf_bytes)

        # Send PDF via Telegram sendDocument API
        with open(tmp_path, "rb") as f:
            requests.post(
                API_URL + "sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": f"📊 <b>Expense Report — {matched_trip['name']}</b>\n\n"
                               f"Total bookings: {len(bookings)}\n"
                               f"Trip has been marked as completed. ✅",
                    "parse_mode": "HTML",
                },
                files={"document": (f"TripPilot_{safe_name}_Report.pdf", f, "application/pdf")},
                timeout=30,
            )

        # Clean up temp file
        try:
            os.remove(tmp_path)
        except Exception:
            pass

        log.info("[EndTrip] PDF sent for trip '%s' (user: %s)", matched_trip["name"], user_id)

    except Exception as exc:
        err_details = traceback.format_exc()
        log.error("Failed to generate/send PDF report: %s\n%s", exc, err_details)
        send_message(
            chat_id,
            f"✅ Trip <b>{matched_trip['name']}</b> has been completed!\n\n"
            f"⚠️ Could not generate the PDF report: {str(exc)}"
        )

    send_message(chat_id, "🎉 Trip completed! Use the menu to view your other trips.", _get_main_menu_keyboard())
