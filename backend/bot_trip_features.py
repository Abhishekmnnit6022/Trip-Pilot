import os
import json
import logging
import requests
from dotenv import load_dotenv

# Ensure we use the same Supabase instance
from backend.telegram_bot import _supabase, send_message, API_URL, _get_linked_user_id

load_dotenv()
log = logging.getLogger(__name__)

# To parse ad-hoc expenses and generate checklists
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage

# Global session to dramatically speed up Telegram API calls by reusing TCP/SSL connections
bot_session = requests.Session()

def _get_llm():
    return ChatGroq(model="llama-3.1-8b-instant", temperature=0.2)

def get_booked_trips_for_bot(user_id: str) -> list[dict]:
    """Fetch ONLY active trips that have bookings, renaming them dynamically."""
    import psycopg
    from psycopg.rows import dict_row
    try:
        conn = psycopg.connect(os.getenv("SUPABASE_DB_URL"), row_factory=dict_row)
        cur = conn.cursor()
        
        # 1. Fetch all active trips
        cur.execute("SELECT id, name, status FROM trips WHERE user_id = %s AND status = 'active'", (user_id,))
        all_trips = cur.fetchall()
        
        # 2. Fetch all bookings
        cur.execute("SELECT trip_id, booking_type, details FROM bookings WHERE user_id = %s", (user_id,))
        bookings = cur.fetchall()
        
        booked_trip_ids = set()
        trip_dests = {}
        
        for b in bookings:
            tid = b.get("trip_id")
            if tid:
                booked_trip_ids.add(tid)
                det = b.get("details") or {}
                dest = None
                if b["booking_type"] == "flight":
                    dest = det.get("arrival_airport")
                elif b["booking_type"] == "train":
                    dest = det.get("arrival_station")
                elif b["booking_type"] == "hotel":
                    dest = det.get("name")
                    
                if dest and tid not in trip_dests:
                    dest_clean = str(dest).split(" International")[0].split(" Airport")[0].split(" Junction")[0].strip()
                    trip_dests[tid] = f"Trip: {dest_clean}"
        
        # Filter to only return trips that have bookings
        valid_trips = []
        for t in all_trips:
            if t["id"] in booked_trip_ids:
                t_dict = dict(t)
                valid_trips.append(t_dict)
                
        conn.commit()
        cur.close()
        conn.close()
        return valid_trips
    except Exception as exc:
        log.error("Failed to fetch booked trips via Postgres: %s", exc)
        return []

def handle_my_trips(chat_id: int, user_id: str):
    """Show active trips to select as context."""
    trips = get_booked_trips_for_bot(user_id)
    if not trips:
        send_message(chat_id, "You don't have any booked trips right now. Plan and book a trip on the web app first!")
        return

    # Create inline keyboard for trips
    inline_keyboard = []
    for t in trips:
        inline_keyboard.append([
            {"text": f"🎒 {t['name']}", "callback_data": f"set_trip:{t['id']}"}
        ])

    bot_session.post(
        API_URL + "sendMessage",
        json={
            "chat_id": chat_id,
            "text": "Please select an active trip to manage:\n(This will set it as your active context for checklists and expenses)",
            "reply_markup": {"inline_keyboard": inline_keyboard}
        }
    )

def handle_callback_query(callback_query: dict):
    """Handle inline button clicks."""
    callback_id = callback_query["id"]
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query.get("data", "")
    message_id = callback_query["message"]["message_id"]

    user_id = _get_linked_user_id(chat_id)
    if not user_id:
        _answer_callback(callback_id, "Please link your account first.")
        return

    if data.startswith("set_trip:"):
        trip_id = data.split(":")[1]
        try:
            _supabase.rpc("bot_set_active_trip", {"p_user_id": user_id, "p_trip_id": trip_id}).execute()
            
            # Fetch the trip name
            resp = _supabase.rpc("bot_get_trip", {"p_trip_id": trip_id}).execute()
            trip_name = resp.data[0]["name"] if resp.data else "Your Trip"
            
            # Show sub-menu for the trip
            inline_keyboard = [
                [{"text": "✈️ Flights", "callback_data": f"view_bkg:{trip_id}:flight"},
                 {"text": "🚂 Trains", "callback_data": f"view_bkg:{trip_id}:train"},
                 {"text": "🏨 Hotels", "callback_data": f"view_bkg:{trip_id}:hotel"}],
                [{"text": "📋 Itinerary Checklist", "callback_data": f"show_itin:{trip_id}"}],
                [{"text": "🧳 Packing Checklist", "callback_data": f"show_pack:{trip_id}"}],
                [{"text": "💰 View Expenses", "callback_data": f"view_exp:{trip_id}"}],
                [{"text": "🔙 Change Trip", "callback_data": "my_trips"},
                 {"text": "🏁 End This Trip", "callback_data": f"end_trip_confirm:{trip_id}"}]
            ]
            
            _answer_callback(callback_id)
            
            bot_session.post(
                API_URL + "editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"✅ Active Trip set to: <b>{trip_name}</b>\n\nWhat would you like to do?\n(You can also just send me a message like <i>'Paid Rs 500 for lunch'</i> to log an expense automatically!)",
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": inline_keyboard}
                },
                timeout=10
            )
        except Exception as exc:
            log.error("Failed to set active trip: %s", exc)
            _answer_callback(callback_id, "Error setting active trip.")

    elif data.startswith("show_itin:"):
        trip_id = data.split(":")[1]
        _handle_show_itinerary(chat_id, message_id, trip_id, callback_id)

    elif data.startswith("toggle_itin:"):
        itin_id = data.split(":")[1]
        _handle_toggle_itinerary(chat_id, message_id, itin_id, callback_id)

    elif data.startswith("view_exp:"):
        trip_id = data.split(":")[1]
        _handle_view_expenses(chat_id, message_id, trip_id, callback_id)

    elif data == "noop":
        _answer_callback(callback_id, "✅ Already completed and logged!", show_alert=False)

    elif data.startswith("view_bkg:"):
        _answer_callback(callback_id)
        _, trip_id, b_type = data.split(":")
        _handle_view_bookings(chat_id, user_id, trip_id, b_type, callback_id)

    elif data == "my_trips":
        handle_my_trips(chat_id, user_id)

    elif data.startswith("end_trip_confirm:"):
        trip_id = data.split(":")[1]
        
        # We need to emulate what happens in telegram_bot.py when a trip is selected for ending
        # But here we already know the trip_id. So we update status to 'completed' and generate PDF.
        try:
            _supabase.table("trips").update({"status": "completed"}).eq("id", trip_id).execute()
            
            # Send initial message
            requests.post(API_URL + "editMessageText", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "🏁 <b>Trip marked as completed!</b>\n\nGenerating your final Expense & Itinerary Report PDF...",
                "parse_mode": "HTML"
            })
            
            # Generate PDF in background to avoid blocking
            import threading
            from backend.telegram_bot import _generate_and_send_pdf
            threading.Thread(target=_generate_and_send_pdf, args=(chat_id, user_id, trip_id), daemon=True).start()
            _answer_callback(callback_id)
        except Exception as exc:
            log.error("Failed to end trip: %s", exc)
            _answer_callback(callback_id, "Error ending trip.")

    elif data.startswith("show_pack:"):
        _answer_callback(callback_id, "Packing list feature coming soon!", show_alert=True)

def _answer_callback(callback_query_id: str, text: str = "", show_alert: bool = False):
    bot_session.post(API_URL + "answerCallbackQuery", json={
        "callback_query_id": callback_query_id,
        "text": text,
        "show_alert": show_alert
    }, timeout=5)

def _handle_show_itinerary(chat_id: int, message_id: int, trip_id: str, callback_id: str):
    # Fetch existing itinerary items
    try:
        resp = _supabase.rpc("bot_get_trip_itinerary", {"p_trip_id": trip_id}).execute()
        items = resp.data or []
    except Exception as exc:
        log.error("Error fetching itinerary: %s", exc)
        _answer_callback(callback_id, "Database error.")
        return

    # If empty, generate using LLM
    if not items:
        # Get trip name
        try:
            t_resp = _supabase.rpc("bot_get_trip", {"p_trip_id": trip_id}).execute()
            trip_name = t_resp.data[0]["name"]
        except:
            trip_name = "Trip"

        _answer_callback(callback_id, "Generating itinerary checklist via AI...")
        
        try:
            llm = _get_llm()
            prompt = f"Generate a short 3-item local activity itinerary checklist for a trip named '{trip_name}'. Focus ONLY on local sightseeing, food, or activities. DO NOT include travel elements like flights, trains, or hotel bookings. Include a mix of paid and free activities. Return ONLY valid JSON format as a list of objects with keys 'activity' (string) and 'estimated_cost' (number in INR, use 0 for free activities). Do not include markdown formatting or backticks, just the raw JSON."
            response = llm.invoke([HumanMessage(content=prompt)])
            
            # Clean response text and parse JSON
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]
            content = content.strip()
                
            generated_items = json.loads(content)
            
            # Insert into DB
            for item in generated_items:
                _supabase.table("trip_itinerary").insert({
                    "trip_id": trip_id,
                    "activity": item.get("activity", "Activity"),
                    "estimated_cost": item.get("estimated_cost", 0)
                }).execute()
                
            # Re-fetch
            resp = _supabase.table("trip_itinerary").select("*").eq("trip_id", trip_id).order("created_at").execute()
            items = resp.data or []
        except Exception as exc:
            log.error("Error generating itinerary: %s", exc)
            _answer_callback(callback_id, "Failed to generate AI itinerary.")
            return

    # Render checklist as a new message so we don't erase the main menu
    _render_itinerary_keyboard(chat_id, message_id, items, is_new=True)
    _answer_callback(callback_id)

def _render_itinerary_keyboard(chat_id: int, message_id: int, items: list, is_new: bool = False):
    inline_keyboard = []
    
    # We need the trip_id to build the End Trip button. Get it from the first item if available.
    trip_id = items[0]["trip_id"] if items else ""
    
    for item in items:
        cost_text = f"(Rs {item['estimated_cost']})" if item['estimated_cost'] > 0 else "(Free)"
        if item["is_completed"]:
            text = f"✅ {item['activity']} {cost_text}"
            inline_keyboard.append([{"text": text, "callback_data": "noop"}])
        else:
            text = f"⬜️ {item['activity']} {cost_text}"
            inline_keyboard.append([{"text": text, "callback_data": f"toggle_itin:{item['id']}"}])
        
    if trip_id:
        inline_keyboard.append([
            {"text": "🔙 Change Trip", "callback_data": "my_trips"},
            {"text": "🏁 End This Trip", "callback_data": f"end_trip_confirm:{trip_id}"}
        ])
        
    text_content = "📋 <b>Interactive Itinerary Checklist</b>\nClick an item to mark it as completed. Completing an item will automatically log its estimated cost to your Trip Expenses!"
    
    if is_new:
        bot_session.post(
            API_URL + "sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_content,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": inline_keyboard}
            },
            timeout=10
        )
    else:
        bot_session.post(
            API_URL + "editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text_content,
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": inline_keyboard}
            },
            timeout=10
        )

def _handle_toggle_itinerary(chat_id: int, message_id: int, itin_id: str, callback_id: str):
    try:
        # Fetch current state
        resp = _supabase.table("trip_itinerary").select("*").eq("id", itin_id).execute()
        if not resp.data:
            _answer_callback(callback_id, "Item not found.")
            return
            
        item = resp.data[0]
        is_done = item["is_completed"]
        
        if is_done:
            _answer_callback(callback_id, "Already completed and logged!", show_alert=False)
            return
            
        # Update state
        _supabase.table("trip_itinerary").update({"is_completed": True}).eq("id", itin_id).execute()
        
        # Add expense securely via RPC only if there is a cost
        if item.get("estimated_cost", 0) > 0:
            _supabase.rpc("bot_add_trip_expense", {
                "p_trip_id": item["trip_id"],
                "p_category": "Activities",
                "p_description": item["activity"],
                "p_amount": item["estimated_cost"]
            }).execute()
            
            _answer_callback(callback_id, f"✅ Logged Rs {item['estimated_cost']} to expenses!", show_alert=False)
        else:
            _answer_callback(callback_id, f"✅ Checked off free activity!", show_alert=False)
            
            
        # Re-render
        resp_all = _supabase.rpc("bot_get_trip_itinerary", {"p_trip_id": item["trip_id"]}).execute()
        _render_itinerary_keyboard(chat_id, message_id, resp_all.data, is_new=False)
        
    except Exception as exc:
        log.error("Error toggling itinerary: %s", exc)
        _answer_callback(callback_id, "Database error.")

def _handle_view_expenses(chat_id: int, message_id: int, trip_id: str, callback_id: str):
    try:
        resp = _supabase.rpc("bot_get_trip_expenses", {"p_trip_id": trip_id}).execute()
        expenses = resp.data or []
        
        if not expenses:
            _answer_callback(callback_id, "No custom expenses logged yet.", show_alert=True)
            return
            
        text = "💰 <b>Logged Custom Expenses:</b>\n\n"
        total = 0
        for e in expenses:
            text += f"• {e['description']} (<i>{e['category']}</i>) : <b>Rs {e['amount']}</b>\n"
            total += e['amount']
            
        text += f"\n<b>Total: Rs {total}</b>"
        
        bot_session.post(
            API_URL + "sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=10
        )
        _answer_callback(callback_id)
    except Exception as exc:
        log.error("Error viewing expenses: %s", exc)
        _answer_callback(callback_id, "Error viewing expenses.")

def _handle_view_bookings(chat_id: int, user_id: str, trip_id: str, b_type: str, callback_id: str):
    try:
        b_resp = _supabase.rpc("bot_get_trip_bookings", {
            "p_user_id": user_id, 
            "p_trip_id": trip_id, 
            "p_booking_type": b_type
        }).execute()
        bookings = b_resp.data or []
    except Exception as exc:
        log.error("Failed to fetch specific bookings: %s", exc)
        _answer_callback(callback_id, "Error fetching bookings.")
        return

    if not bookings:
        _answer_callback(callback_id, f"You don't have any {b_type} bookings for this trip.", show_alert=True)
        return

    emoji = "✈️" if b_type == "flight" else ("🚂" if b_type == "train" else "🏨")
    msg = f"Here are your <b>{b_type.title()}s</b> for this trip:\n\n"
    for b in bookings[:5]:
        msg += f"{emoji} <b>{b['provider_name']}</b>\n"
        
        id_label = "Booking ID" if b_type == 'hotel' else "PNR"
        msg += f"🔖 {id_label}: <code>{b['pnr_or_confirmation_number']}</code>\n"
        
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

    bot_session.post(API_URL + "sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
    _answer_callback(callback_id)

def handle_ad_hoc_expense(chat_id: int, user_id: str, text: str) -> bool:
    """Check if the user has an active trip and try to parse the text as an expense."""
    try:
        resp = _supabase.rpc("bot_get_active_trip_context", {"p_user_id": user_id}).execute()
        active_trips = resp.data or []
        if not active_trips:
            return False # No active context, fallback to default error
            
        trip = active_trips[0]
        trip_id = trip["trip_id"]
        trip_name = trip["name"]
        
        # Check if text mentions a number
        if not any(char.isdigit() for char in text):
            return False # Doesn't look like an expense
            
        send_message(chat_id, "⏳ Analyzing your message for expenses...")
        
        # Use LLM to parse
        llm = _get_llm()
        prompt = f"Extract expense details from this message: '{text}'. Return ONLY valid JSON format with keys: 'is_expense' (boolean), 'amount' (number in INR), 'category' (string like 'Food', 'Transport', 'Shopping', 'Other'), 'description' (string). If it is not an expense, set 'is_expense' to false. Do not include markdown or backticks."
        response = llm.invoke([HumanMessage(content=prompt)])
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        content = content.strip()
            
        data = json.loads(content)
        
        if not data.get("is_expense"):
            return False
            
        # Log the expense
        _supabase.rpc("bot_add_trip_expense", {
            "p_trip_id": trip_id,
            "p_category": data.get("category", "Other"),
            "p_description": data.get("description", "Ad-hoc expense"),
            "p_amount": data.get("amount", 0)
        }).execute()
        
        inline_keyboard = [
            [{"text": "🔙 Change Trip", "callback_data": "my_trips"},
             {"text": "🏁 End This Trip", "callback_data": f"end_trip_confirm:{trip_id}"}]
        ]
        
        send_message(chat_id, f"✅ <b>Expense Logged for {trip_name}!</b>\n\n📝 {data.get('description')}\n🏷 {data.get('category')}\n💰 Rs {data.get('amount')}", {"parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}})
        return True
        
    except Exception as exc:
        log.error("Ad-hoc expense error: %s", exc)
        return False
