"""
SOS Emergency Service — Using Fast2SMS API for India.

This module provides:
  - send_emergency_sms_free(): Sends an SMS alert to the emergency contact
    using the Fast2SMS API (https://www.fast2sms.com/).
"""

import logging
import requests
from backend.config import FAST2SMS_API_KEY

log = logging.getLogger(__name__)


def send_emergency_sms_free(to_phone: str, user_name: str, trip_details: str = "") -> bool:
    """
    Send an emergency SMS using Fast2SMS API.

    Args:
        to_phone:  The emergency contact's phone number.
        user_name: The name of the TripPilot user who triggered the SOS.
        trip_details: Optional string detailing the user's latest trip location/booking.

    Returns:
        True if the SMS was successfully queued, False otherwise.
    """
    if not to_phone:
        log.error("No emergency contact phone number provided.")
        return False
        
    if not FAST2SMS_API_KEY:
        log.error("FAST2SMS_API_KEY is not set in environment variables.")
        return False

    try:
        # Construct the emergency message
        msg = f"🚨 EMERGENCY: {user_name} has triggered an SOS alert on TripPilot and may need help immediately!"
        
        if trip_details:
            msg += f"\n\n📍 Latest Trip Info: {trip_details}"
        else:
            msg += f"\n\n📍 Location: Cannot determine exact coordinates, please contact them immediately."

        # Fast2SMS requires 10-digit number without country code
        # Extract the last 10 digits just to be safe
        clean_phone = "".join(filter(str.isdigit, to_phone))[-10:]

        log.info(f"Attempting to send SMS via Fast2SMS to {clean_phone}")

        url = "https://www.fast2sms.com/dev/bulkV2"
        payload = {
            "route": "q",
            "message": msg,
            "language": "english",
            "flash": 0,
            "numbers": clean_phone
        }
        headers = {
            "authorization": FAST2SMS_API_KEY,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        resp = requests.post(url, data=payload, headers=headers, timeout=10)
        
        data = resp.json()
        if data.get("return") == True:
            log.info("Emergency SMS sent successfully via Fast2SMS!")
            return True
        else:
            log.error("Fast2SMS failed: %s", data.get("message", "Unknown error"))
            return False

    except Exception as exc:
        log.error("Failed to send emergency SMS: %s", exc)
        return False
