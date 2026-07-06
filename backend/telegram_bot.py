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

import time
import threading
import requests
import logging
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
            [{"text": "✈️ My Flights"}, {"text": "🚂 My Trains"}],
            [{"text": "🏨 My Hotels"}, {"text": "🌍 Plan New Trip"}],
            [{"text": "📞 Emergency Contact"}],
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

    if text in ["🚨 SOS Emergency", "🆘 SOS EMERGENCY 🆘", "🆘 SOS EMERGENCY", "📞 Emergency Contact"]:
        LINK_STATE.pop(chat_id, None)
        EC_STATE.pop(chat_id, None)

    # ── 1. /start command ────────────────────────────────────────────────────
    if text == "/start":
        LINK_STATE.pop(chat_id, None)
        EC_STATE.pop(chat_id, None)
        # Cancel any active SOS
        if chat_id in SOS_STATE:
            SOS_STATE[chat_id]["active"] = False
            SOS_STATE.pop(chat_id, None)

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
    if text in ["✈️ My Flights", "🚂 My Trains", "🏨 My Hotels"]:
        user_id = _get_linked_user_id(chat_id)

        if not user_id:
            send_message(chat_id, "⚠️ Your account is not linked yet. Please type /start to link your account.")
            return

        if "Flights" in text:
            b_type, emoji = "flight", "✈️"
        elif "Trains" in text:
            b_type, emoji = "train", "🚂"
        else:
            b_type, emoji = "hotel", "🏨"

        # Fetch bookings via RPC (with fallback to direct query)
        try:
            b_resp = _supabase.rpc("bot_get_bookings", {"p_user_id": user_id, "p_booking_type": b_type}).execute()
            bookings = b_resp.data or []
        except Exception:
            b_resp = _supabase.table("bookings").select("*").eq("user_id", user_id).eq("booking_type", b_type).order("booking_date", desc=True).execute()
            bookings = b_resp.data or []

        if not bookings:
            send_message(chat_id, f"You don't have any {b_type} bookings right now.")
            return

        msg = f"Here are your latest <b>{b_type.title()}s</b>:\n\n"
        for b in bookings[:5]:
            msg += f"{emoji} <b>{b['provider_name']}</b>\n"
            
            # Use 'Booking ID' for hotels, 'PNR' for flights/trains
            id_label = "Booking ID" if b_type == 'hotel' else "PNR"
            msg += f"🔖 {id_label}: <code>{b['pnr_or_confirmation_number']}</code>\n"
            
            # Extract rich details if available
            details = b.get('details') or {}
            
            if b_type == 'flight':
                if details.get('flight_number'):
                    msg += f"✈️ Flight: {details['flight_number']}\n"
                if details.get('departure_airport') and details.get('arrival_airport'):
                    msg += f"🗺️ Route: {details['departure_airport']} ➡️ {details['arrival_airport']}\n"
                    
            elif b_type == 'train':
                if details.get('train_number'):
                    msg += f"🚆 Train #: {details['train_number']}\n"
                if details.get('departure_station') and details.get('arrival_station'):
                    msg += f"🛤️ Route: {details['departure_station']} ➡️ {details['arrival_station']}\n"
                    
            elif b_type == 'hotel':
                if details.get('checkin') and details.get('checkout'):
                    msg += f"🛏️ Stay: {details['checkin']} to {details['checkout']}\n"
                    
            msg += f"📅 Date: {b['travel_date'] or 'TBD'}\n\n"

        send_message(chat_id, msg)
        return

    # ── 8. Menu Button: Plan New Trip ────────────────────────────────────────
    if text == "🌍 Plan New Trip":
        send_message(
            chat_id,
            "To generate magical AI itineraries and book new trips, "
            "please visit the TripPilot web app! 🚀"
        )
        return

    # ── 9. Phone Number Input (Account Linking Step 1) ───────────────────────
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

    # ── 10. Menu Command & Fallback ──────────────────────────────────────────
    user_id = _get_linked_user_id(chat_id)
    if user_id and text == "/menu":
        send_message(chat_id, "Here is your menu:", _get_main_menu_keyboard())
        return
        
    if user_id and not (chat_id in LINK_STATE or chat_id in EC_STATE or chat_id in SOS_STATE):
        send_message(
            chat_id,
            "I didn't understand that. Please use the menu buttons below.",
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
                        handle_message(update["message"])
            else:
                log.error("Telegram API Error: %s", resp.text)
                time.sleep(5)

        except Exception as e:
            log.error("Telegram polling error (connection issue): %s", e)
            time.sleep(5)
