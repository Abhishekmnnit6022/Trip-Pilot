"""
Profile, Booking, Telegram, and Weather API endpoints.

This module defines all REST API routes for the TripPilot backend.
All endpoints use Supabase as the database and enforce Row Level Security (RLS)
by forwarding the user's JWT token to the Supabase client.

Endpoints
---------
GET  /api/profile              Fetch the authenticated user's profile
PUT  /api/profile              Update the authenticated user's profile
GET  /api/bookings             List the authenticated user's bookings
POST /api/book                 Create a new booking (simulated payment)
POST /api/telegram/link        Link a Telegram chat ID to user profile
GET  /api/telegram/bot-info    Get the Telegram bot username for linking
GET  /api/weather              Get weather forecast for a city
"""

import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from supabase import create_client

from backend.auth import get_current_user
from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY
from backend.telegram_service import send_booking_confirmation, get_bot_info
from backend.tools.weather_tool import get_weather_forecast
from supabase import ClientOptions

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Service-level Supabase client (no RLS — only for admin operations)
_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_user_client(token: str):
    """
    Create a Supabase client that forwards the user's JWT for RLS enforcement.

    Args:
        token: The user's Supabase access token (JWT).

    Returns:
        A Supabase client instance with the user's auth context.
    """
    return create_client(
        SUPABASE_URL,
        SUPABASE_ANON_KEY,
        options=ClientOptions(headers={"Authorization": f"Bearer {token}"})
    )


# ══════════════════════════════════════════════════════════════════════════════
#   REQUEST / RESPONSE MODELS
# ══════════════════════════════════════════════════════════════════════════════

class ProfileUpdate(BaseModel):
    """Schema for PUT /api/profile request body."""
    full_name: str = ""
    phone_number: str = ""
    birth_date: str | None = None           # "YYYY-MM-DD" or null
    travel_preferences: dict = {}
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""


class ProfileResponse(BaseModel):
    """Schema for profile API responses."""
    id: str
    full_name: str = ""
    phone_number: str = ""
    birth_date: str | None = None
    travel_preferences: dict = {}
    telegram_chat_id: str = ""
    emergency_contact_name: str = ""
    emergency_contact_phone: str = ""


class BookingRequest(BaseModel):
    """Schema for POST /api/book request body."""
    booking_type: str                       # flight | train | hotel
    provider_name: str = ""
    travel_date: str = ""                   # "YYYY-MM-DD"
    details: dict = {}


class BookingResponse(BaseModel):
    """Schema for booking API responses."""
    id: str
    booking_type: str
    provider_name: str
    pnr_or_confirmation_number: str
    booking_date: str
    travel_date: str | None
    details: dict
    status: str


class TelegramLinkRequest(BaseModel):
    """Schema for POST /api/telegram/link request body."""
    telegram_chat_id: str


# ══════════════════════════════════════════════════════════════════════════════
#   PROFILE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/profile", response_model=ProfileResponse)
def get_profile(user: dict = Depends(get_current_user)):
    """
    Fetch the authenticated user's profile.

    If the profile doesn't exist yet (e.g., trigger failed during signup),
    creates a new empty profile row automatically.

    Returns:
        ProfileResponse with all profile fields.
    """
    try:
        client = get_user_client(user["token"])
        resp = (
            client.table("user_profiles")
            .select("*")
            .eq("id", user["user_id"])
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return ProfileResponse(
                id=row["id"],
                full_name=row.get("full_name", ""),
                phone_number=row.get("phone_number", ""),
                birth_date=str(row["birth_date"]) if row.get("birth_date") else None,
                travel_preferences=row.get("travel_preferences") or {},
                telegram_chat_id=row.get("telegram_chat_id", ""),
                emergency_contact_name=row.get("emergency_contact_name", ""),
                emergency_contact_phone=row.get("emergency_contact_phone", ""),
            )
        # Profile doesn't exist yet — create one
        client.table("user_profiles").insert({"id": user["user_id"]}).execute()
        return ProfileResponse(id=user["user_id"])
    except Exception as exc:
        log.error("Failed to fetch profile: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch profile")


@router.put("/profile", response_model=ProfileResponse)
def update_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    """
    Update the authenticated user's profile.

    Uses UPSERT to handle cases where the profile row doesn't exist yet.

    Args:
        body: ProfileUpdate with the fields to update.

    Returns:
        ProfileResponse with the updated profile data.
    """
    update_data: dict = {
        "full_name": body.full_name,
        "phone_number": body.phone_number,
        "travel_preferences": body.travel_preferences,
        "emergency_contact_name": body.emergency_contact_name,
        "emergency_contact_phone": body.emergency_contact_phone,
    }
    if body.birth_date:
        update_data["birth_date"] = body.birth_date

    try:
        client = get_user_client(user["token"])
        # UPSERT so it creates the row if it's missing
        update_data["id"] = user["user_id"]
        resp = (
            client.table("user_profiles")
            .upsert(update_data)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return ProfileResponse(
                id=row["id"],
                full_name=row.get("full_name", ""),
                phone_number=row.get("phone_number", ""),
                birth_date=str(row["birth_date"]) if row.get("birth_date") else None,
                travel_preferences=row.get("travel_preferences") or {},
                telegram_chat_id=row.get("telegram_chat_id", ""),
                emergency_contact_name=row.get("emergency_contact_name", ""),
                emergency_contact_phone=row.get("emergency_contact_phone", ""),
            )
        raise HTTPException(status_code=404, detail="Profile not found")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to update profile: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update profile")


# ══════════════════════════════════════════════════════════════════════════════
#   BOOKING ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

def _generate_pnr() -> str:
    """
    Generate a realistic 8-character PNR / confirmation number.

    Returns:
        An uppercase alphanumeric string like "A3F8B1C2".
    """
    return uuid.uuid4().hex[:8].upper()


@router.post("/book", response_model=BookingResponse)
def create_booking(body: BookingRequest, user: dict = Depends(get_current_user)):
    """
    Simulate a booking — generates a PNR, saves it to the database,
    and sends a Telegram notification if the user has linked their account.

    Args:
        body: BookingRequest with booking_type, provider_name, travel_date, details.

    Returns:
        BookingResponse with the confirmed booking details and PNR.
    """
    if body.booking_type not in ("flight", "train", "hotel"):
        raise HTTPException(status_code=400, detail="booking_type must be flight, train, or hotel")

    pnr = _generate_pnr()
    now = datetime.utcnow().isoformat()

    row = {
        "user_id": user["user_id"],
        "booking_type": body.booking_type,
        "provider_name": body.provider_name,
        "pnr_or_confirmation_number": pnr,
        "booking_date": now,
        "travel_date": body.travel_date or None,
        "details": body.details,
        "status": "confirmed",
    }

    try:
        client = get_user_client(user["token"])
        resp = client.table("bookings").insert(row).execute()
        if resp.data:
            saved = resp.data[0]

            # Send Telegram notification (fire-and-forget, non-blocking)
            try:
                profile_resp = (
                    client.table("user_profiles")
                    .select("telegram_chat_id")
                    .eq("id", user["user_id"])
                    .execute()
                )
                chat_id = ""
                if profile_resp.data:
                    chat_id = profile_resp.data[0].get("telegram_chat_id", "")
                if chat_id:
                    send_booking_confirmation(
                        chat_id=chat_id,
                        booking_type=body.booking_type,
                        pnr=pnr,
                        provider_name=body.provider_name,
                        travel_date=body.travel_date or "",
                        details=body.details,
                    )
            except Exception as tg_exc:
                log.warning("Telegram notification failed (non-fatal): %s", tg_exc)

            return BookingResponse(
                id=saved["id"],
                booking_type=saved["booking_type"],
                provider_name=saved.get("provider_name", ""),
                pnr_or_confirmation_number=saved["pnr_or_confirmation_number"],
                booking_date=str(saved["booking_date"]),
                travel_date=str(saved["travel_date"]) if saved.get("travel_date") else None,
                details=saved.get("details") or {},
                status=saved["status"],
            )
        raise HTTPException(status_code=500, detail="Booking insert returned no data")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to create booking: %s", exc)
        raise HTTPException(status_code=500, detail=f"Booking failed: {exc}")


@router.get("/bookings", response_model=list[BookingResponse])
def list_bookings(user: dict = Depends(get_current_user)):
    """
    List all bookings for the authenticated user, ordered by most recent first.

    Returns:
        A list of BookingResponse objects.
    """
    try:
        client = get_user_client(user["token"])
        resp = (
            client.table("bookings")
            .select("*")
            .eq("user_id", user["user_id"])
            .order("booking_date", desc=True)
            .execute()
        )
        return [
            BookingResponse(
                id=row["id"],
                booking_type=row["booking_type"],
                provider_name=row.get("provider_name", ""),
                pnr_or_confirmation_number=row["pnr_or_confirmation_number"],
                booking_date=str(row["booking_date"]),
                travel_date=str(row["travel_date"]) if row.get("travel_date") else None,
                details=row.get("details") or {},
                status=row["status"],
            )
            for row in (resp.data or [])
        ]
    except Exception as exc:
        log.error("Failed to list bookings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch bookings")


# ══════════════════════════════════════════════════════════════════════════════
#   TELEGRAM ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/telegram/link")
def link_telegram(body: TelegramLinkRequest, user: dict = Depends(get_current_user)):
    """
    Link a Telegram chat ID to the authenticated user's profile.

    Args:
        body: TelegramLinkRequest with the telegram_chat_id string.

    Returns:
        {"status": "linked", "telegram_chat_id": "..."} on success.
    """
    try:
        client = get_user_client(user["token"])
        client.table("user_profiles").update(
            {"telegram_chat_id": body.telegram_chat_id}
        ).eq("id", user["user_id"]).execute()
        return {"status": "linked", "telegram_chat_id": body.telegram_chat_id}
    except Exception as exc:
        log.error("Failed to link Telegram: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to link Telegram")


@router.get("/telegram/bot-info")
def telegram_bot_info():
    """
    Return the Telegram bot's username so the frontend can display a t.me link.

    Returns:
        {"username": "bot_name", "configured": True} or {"username": "", "configured": False}
    """
    info = get_bot_info()
    if info:
        return {"username": info.get("username", ""), "configured": True}
    return {"username": "", "configured": False}


# ══════════════════════════════════════════════════════════════════════════════
#   WEATHER ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/weather")
def weather_forecast(city: str, start_date: str = "", end_date: str = ""):
    """
    Get weather forecast for a city using the free Open-Meteo API.

    Args:
        city:       City name (e.g., "Rishikesh")
        start_date: Optional start date (YYYY-MM-DD)
        end_date:   Optional end date (YYYY-MM-DD)

    Returns:
        Weather forecast dict with daily forecasts and summary.
    """
    if not city.strip():
        raise HTTPException(status_code=400, detail="City is required")
    return get_weather_forecast(city.strip(), start_date, end_date)
