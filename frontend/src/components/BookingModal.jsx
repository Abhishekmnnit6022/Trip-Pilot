/**
 * BookingModal.jsx — 3-Step Booking Wizard
 *
 * A premium modal that guides users through:
 *   Step 1 (Review)   → Pre-filled traveler info + trip details
 *   Step 2 (Payment)  → Simulated payment with UPI / Card selector
 *   Step 3 (Confirmed) → Animated success with PNR display
 *
 * Props:
 *   @param {boolean}  isOpen       - Controls modal visibility
 *   @param {Function} onClose      - Callback to close the modal
 *   @param {Object}   bookingData  - { bookingType, providerName, travelDate, details }
 *   @param {Function} onBooked     - Callback after successful booking; receives the booking response
 */

import { useState, useEffect } from 'react';
import { supabase, API_URL } from '../lib/supabase';
import {
  X, User, Phone, MapPin, Calendar, CreditCard,
  Loader2, Check, ChevronRight, Shield, Smartphone,
  Building2, Plane, Train, Hotel
} from 'lucide-react';

/* ── Step indicator at the top of the wizard ──────────────────────────────── */
function StepIndicator({ currentStep }) {
  const steps = ['Review', 'Payment', 'Confirmed'];
  return (
    <div className="booking-steps">
      {steps.map((label, i) => (
        <div key={label} className={`booking-step ${i <= currentStep ? 'active' : ''} ${i < currentStep ? 'completed' : ''}`}>
          <div className="step-circle">
            {i < currentStep ? <Check size={14} /> : <span>{i + 1}</span>}
          </div>
          <span className="step-label">{label}</span>
          {i < steps.length - 1 && <div className="step-line" />}
        </div>
      ))}
    </div>
  );
}

/* ── Icon for the booking type ────────────────────────────────────────────── */
function TypeIcon({ type }) {
  if (type === 'flight') return <Plane size={18} />;
  if (type === 'train') return <Train size={18} />;
  return <Hotel size={18} />;
}

export default function BookingModal({ isOpen, onClose, bookingData, onBooked }) {
  const [step, setStep] = useState(0);            // 0=Review, 1=Payment, 2=Confirmed
  const [profile, setProfile] = useState(null);     // User profile from API
  const [loading, setLoading] = useState(false);     // Profile fetch spinner
  const [processing, setProcessing] = useState(false); // Payment processing spinner
  const [paymentMethod, setPaymentMethod] = useState('upi'); // upi | card
  const [pnr, setPnr] = useState('');               // PNR after booking
  const [error, setError] = useState('');

  /* Reset wizard state every time the modal opens */
  useEffect(() => {
    if (isOpen) {
      setStep(0);
      setPnr('');
      setError('');
      setPaymentMethod('upi');
      fetchProfile();
    }
  }, [isOpen]);

  /**
   * Fetch the authenticated user's profile so we can pre-fill
   * the Review step with their name, phone, etc.
   */
  const fetchProfile = async () => {
    setLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      const resp = await fetch(`${API_URL}/api/profile`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setProfile(data);
      }
    } catch (err) {
      console.error('Failed to fetch profile for booking:', err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Simulate the payment + create the booking in the database.
   * Shows a realistic 2-second processing delay before confirming.
   */
  const handlePayment = async () => {
    setProcessing(true);
    setError('');

    // Simulate payment processing delay (1.5–2.5s)
    await new Promise((r) => setTimeout(r, 1500 + Math.random() * 1000));

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { setError('Session expired. Please log in again.'); setProcessing(false); return; }

      const resp = await fetch(`${API_URL}/api/book`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          booking_type: bookingData.bookingType,
          provider_name: bookingData.providerName,
          travel_date: bookingData.travelDate,
          details: bookingData.details,
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        setPnr(data.pnr_or_confirmation_number);
        setStep(2); // Move to Confirmed step
        if (onBooked) onBooked(data);
      } else {
        setError('Payment failed. Please try again.');
      }
    } catch (err) {
      console.error('Booking failed:', err);
      setError('Network error. Please check your connection.');
    } finally {
      setProcessing(false);
    }
  };

  if (!isOpen || !bookingData) return null;

  const { bookingType, providerName, details } = bookingData;
  const emoji = bookingType === 'flight' ? '✈️' : bookingType === 'train' ? '🚂' : '🏨';

  /* ── Helper: compute display price ──────────────────────────────────────── */
  const getPrice = () => {
    const p = details?.price;
    if (typeof p === 'number') return `₹${p.toLocaleString('en-IN')}`;
    if (typeof p === 'string' && p !== 'N/A') return p;
    // Simulate a price for flights/trains that don't have one
    const simulated = bookingType === 'hotel' ? '₹3,499' : bookingType === 'flight' ? '₹4,899' : '₹1,250';
    return simulated;
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content booking-modal" onClick={(e) => e.stopPropagation()}>

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="modal-header">
          <h2>{emoji} Book {bookingType.charAt(0).toUpperCase() + bookingType.slice(1)}</h2>
          <button className="modal-close" onClick={onClose} disabled={processing}>
            <X size={20} />
          </button>
        </div>

        <StepIndicator currentStep={step} />

        {/* ── Step 1: Review ─────────────────────────────────────────────── */}
        {step === 0 && (
          <div className="modal-body booking-review">
            {loading ? (
              <div className="modal-loading">
                <Loader2 size={28} className="spin" />
                <span>Loading your details…</span>
              </div>
            ) : (
              <>
                {/* Traveler Info */}
                <div className="booking-section">
                  <h3><User size={16} /> Traveler Information</h3>
                  <div className="booking-info-grid">
                    <div className="booking-info-item">
                      <span className="info-label">Full Name</span>
                      <span className="info-value">{profile?.full_name || 'Not set'}</span>
                    </div>
                    <div className="booking-info-item">
                      <span className="info-label">Phone</span>
                      <span className="info-value">{profile?.phone_number || 'Not set'}</span>
                    </div>
                  </div>
                </div>

                {/* Trip Details */}
                <div className="booking-section">
                  <h3><TypeIcon type={bookingType} /> {bookingType.charAt(0).toUpperCase() + bookingType.slice(1)} Details</h3>
                  <div className="booking-detail-card">
                    <div className="detail-provider">
                      <strong>{providerName}</strong>
                      {details?.flight_number && <span className="detail-sub">Flight {details.flight_number}</span>}
                      {details?.train_number && <span className="detail-sub">Train #{details.train_number}</span>}
                    </div>

                    {/* Route (flights & trains) */}
                    {(details?.departure_airport || details?.departure_station) && (
                      <div className="detail-route">
                        <div className="detail-point">
                          <MapPin size={14} />
                          <span>{details.departure_airport || details.departure_station}</span>
                        </div>
                        <ChevronRight size={16} className="detail-arrow" />
                        <div className="detail-point">
                          <MapPin size={14} />
                          <span>{details.arrival_airport || details.arrival_station}</span>
                        </div>
                      </div>
                    )}

                    {/* Hotel dates */}
                    {details?.checkin && (
                      <div className="detail-dates">
                        <span><Calendar size={14} /> Check-in: {details.checkin}</span>
                        <span><Calendar size={14} /> Check-out: {details.checkout}</span>
                      </div>
                    )}

                    {/* Duration (trains) */}
                    {details?.duration && (
                      <div className="detail-meta">⏱ Duration: {details.duration}</div>
                    )}
                  </div>
                </div>

                {/* Price Summary */}
                <div className="booking-section booking-price-summary">
                  <div className="price-row">
                    <span>Base Fare</span>
                    <span>{getPrice()}</span>
                  </div>
                  <div className="price-row price-sub">
                    <span>Taxes & Fees</span>
                    <span>Included</span>
                  </div>
                  <div className="price-row price-total">
                    <span>Total</span>
                    <span>{getPrice()}</span>
                  </div>
                </div>

                <button className="btn-primary booking-cta" onClick={() => setStep(1)}>
                  Continue to Payment <ChevronRight size={18} />
                </button>
              </>
            )}
          </div>
        )}

        {/* ── Step 2: Payment ────────────────────────────────────────────── */}
        {step === 1 && (
          <div className="modal-body booking-payment">
            <div className="booking-section">
              <h3><CreditCard size={16} /> Payment Method</h3>
              <div className="payment-methods">
                <button
                  className={`payment-method ${paymentMethod === 'upi' ? 'selected' : ''}`}
                  onClick={() => setPaymentMethod('upi')}
                >
                  <Smartphone size={20} />
                  <div>
                    <strong>UPI</strong>
                    <span>Google Pay, PhonePe, Paytm</span>
                  </div>
                </button>
                <button
                  className={`payment-method ${paymentMethod === 'card' ? 'selected' : ''}`}
                  onClick={() => setPaymentMethod('card')}
                >
                  <CreditCard size={20} />
                  <div>
                    <strong>Credit / Debit Card</strong>
                    <span>Visa, Mastercard, RuPay</span>
                  </div>
                </button>
                <button
                  className={`payment-method ${paymentMethod === 'netbanking' ? 'selected' : ''}`}
                  onClick={() => setPaymentMethod('netbanking')}
                >
                  <Building2 size={20} />
                  <div>
                    <strong>Net Banking</strong>
                    <span>All major banks</span>
                  </div>
                </button>
              </div>
            </div>

            <div className="booking-amount-box">
              <span className="amount-label">Amount to Pay</span>
              <span className="amount-value">{getPrice()}</span>
            </div>

            {error && <div className="booking-error">{error}</div>}

            <div className="payment-secure">
              <Shield size={14} />
              <span>256-bit SSL encrypted · Secure payment</span>
            </div>

            <button
              className="btn-primary booking-cta pay-btn"
              onClick={handlePayment}
              disabled={processing}
            >
              {processing ? (
                <>
                  <Loader2 size={18} className="spin" />
                  Processing Payment…
                </>
              ) : (
                <>Pay {getPrice()} <ChevronRight size={18} /></>
              )}
            </button>

            <button className="booking-back" onClick={() => setStep(0)} disabled={processing}>
              ← Back to Review
            </button>
          </div>
        )}

        {/* ── Step 3: Confirmed ──────────────────────────────────────────── */}
        {step === 2 && (
          <div className="modal-body booking-confirmed-step">
            <div className="confirm-animation">
              <div className="confirm-circle">
                <Check size={36} />
              </div>
            </div>
            <h3 className="confirm-title">Booking Confirmed! 🎉</h3>
            <p className="confirm-subtitle">
              Your {bookingType} with <strong>{providerName}</strong> has been successfully booked.
            </p>

            <div className="confirm-pnr-box">
              <span className="pnr-label">Your PNR / Confirmation Number</span>
              <span className="pnr-value">{pnr}</span>
            </div>

            <div className="confirm-details">
              <p>📱 A confirmation has been sent to your Telegram (if linked).</p>
              <p>📧 Check your email for the full e-ticket.</p>
            </div>

            <button className="btn-primary booking-cta" onClick={onClose}>
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
