"""
Stripe Payment Service — Test Mode Integration.

This module provides a clean interface to Stripe's Payment Intent API
for processing simulated payments in TripPilot's booking wizard.

Uses Stripe Test Mode (completely free, no credit card required).
Test card: 4242 4242 4242 4242, any future expiry, any CVC.

Usage:
    from backend.stripe_service import create_payment_intent, confirm_payment

    # Step 1: Create a payment intent when user clicks "Pay"
    intent = create_payment_intent(amount_inr=4899, booking_type="flight", user_id="...")

    # Step 2: Confirm the payment (simulates success in test mode)
    result = confirm_payment(intent["payment_intent_id"])
"""

import logging
import os
from backend.config import STRIPE_SECRET_KEY

log = logging.getLogger(__name__)

# Lazy-initialize stripe to avoid import errors if not installed
_stripe = None


def _get_stripe():
    """Lazy-load and configure the stripe module."""
    global _stripe
    if _stripe is None:
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            _stripe = stripe
            log.info("Stripe SDK initialized in %s mode",
                      "TEST" if "sk_test" in (STRIPE_SECRET_KEY or "") else "LIVE")
        except ImportError:
            log.error("stripe package not installed. Run: pip install stripe")
            raise
    return _stripe


def is_stripe_configured() -> bool:
    """Check if Stripe is properly configured with a valid API key."""
    return bool(STRIPE_SECRET_KEY and STRIPE_SECRET_KEY.startswith("sk_"))


def create_payment_intent(
    amount_inr: int,
    booking_type: str,
    user_id: str,
    provider_name: str = "",
    description: str = "",
) -> dict:
    """
    Create a Stripe PaymentIntent for a booking.

    Args:
        amount_inr:     Amount in INR (e.g. 4899 for ₹4,899)
        booking_type:   "flight", "train", or "hotel"
        user_id:        The authenticated user's Supabase UUID
        provider_name:  Name of the airline/train/hotel
        description:    Human-readable payment description

    Returns:
        dict with:
            - payment_intent_id: str (Stripe PI ID)
            - client_secret: str (for frontend confirmation)
            - amount: int (in smallest unit — paise)
            - currency: str ("inr")
            - status: str (Stripe status)
    """
    if not is_stripe_configured():
        log.warning("Stripe not configured — returning simulated payment intent")
        return _simulated_payment_intent(amount_inr, booking_type, user_id)

    stripe = _get_stripe()
    amount_paise = amount_inr * 100  # Stripe uses smallest currency unit

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_paise,
            currency="inr",
            description=description or f"TripPilot {booking_type.title()} Booking",
            metadata={
                "user_id": user_id,
                "booking_type": booking_type,
                "provider_name": provider_name,
                "platform": "TripPilot",
            },
            # Auto-confirm in test mode for seamless UX
            automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        )

        log.info(
            "[Stripe] PaymentIntent created: %s | ₹%d | %s",
            intent.id, amount_inr, booking_type,
        )

        return {
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,
            "amount": amount_paise,
            "amount_inr": amount_inr,
            "currency": "inr",
            "status": intent.status,
        }

    except Exception as exc:
        log.error("[Stripe] Failed to create PaymentIntent: %s", exc)
        # Fallback to simulated payment if Stripe fails
        return _simulated_payment_intent(amount_inr, booking_type, user_id)


def confirm_payment(payment_intent_id: str) -> dict:
    """
    Confirm a Stripe PaymentIntent (simulates card charge in test mode).

    Args:
        payment_intent_id: The Stripe PaymentIntent ID (pi_...)

    Returns:
        dict with status, receipt_url, and transaction details.
    """
    if not is_stripe_configured() or payment_intent_id.startswith("sim_"):
        return _simulated_confirmation(payment_intent_id)

    stripe = _get_stripe()

    try:
        # In test mode, confirm with a test payment method
        intent = stripe.PaymentIntent.confirm(
            payment_intent_id,
            payment_method="pm_card_visa",  # Stripe test card
        )

        log.info(
            "[Stripe] Payment confirmed: %s | Status: %s",
            intent.id, intent.status,
        )

        # Get the latest charge for receipt URL
        receipt_url = ""
        if intent.latest_charge:
            try:
                charge = stripe.Charge.retrieve(intent.latest_charge)
                receipt_url = charge.receipt_url or ""
            except Exception:
                pass

        return {
            "payment_intent_id": intent.id,
            "status": intent.status,
            "receipt_url": receipt_url,
            "amount_inr": intent.amount // 100,
            "currency": intent.currency,
            "payment_method": "Visa •••• 4242 (Test)",
            "transaction_id": intent.latest_charge or intent.id,
        }

    except Exception as exc:
        log.error("[Stripe] Payment confirmation failed: %s", exc)
        return {
            "payment_intent_id": payment_intent_id,
            "status": "failed",
            "error": str(exc),
        }


def get_payment_status(payment_intent_id: str) -> dict:
    """Retrieve the current status of a payment intent."""
    if not is_stripe_configured() or payment_intent_id.startswith("sim_"):
        return {"payment_intent_id": payment_intent_id, "status": "succeeded"}

    stripe = _get_stripe()
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return {
            "payment_intent_id": intent.id,
            "status": intent.status,
            "amount_inr": intent.amount // 100,
        }
    except Exception as exc:
        log.error("[Stripe] Status check failed: %s", exc)
        return {"payment_intent_id": payment_intent_id, "status": "unknown", "error": str(exc)}


# ── Simulated fallback (when Stripe is not configured) ───────────────────────

def _simulated_payment_intent(amount_inr: int, booking_type: str, user_id: str) -> dict:
    """Generate a simulated payment intent for demo/testing without Stripe."""
    import uuid
    sim_id = f"sim_pi_{uuid.uuid4().hex[:16]}"
    log.info("[SimulatedPayment] Created: %s | ₹%d", sim_id, amount_inr)
    return {
        "payment_intent_id": sim_id,
        "client_secret": f"{sim_id}_secret_simulated",
        "amount": amount_inr * 100,
        "amount_inr": amount_inr,
        "currency": "inr",
        "status": "requires_confirmation",
    }


def _simulated_confirmation(payment_intent_id: str) -> dict:
    """Simulate a successful payment confirmation."""
    import uuid
    log.info("[SimulatedPayment] Confirmed: %s", payment_intent_id)
    return {
        "payment_intent_id": payment_intent_id,
        "status": "succeeded",
        "receipt_url": "",
        "amount_inr": 0,
        "currency": "inr",
        "payment_method": "Simulated Payment (Demo Mode)",
        "transaction_id": f"sim_txn_{uuid.uuid4().hex[:12]}",
    }
