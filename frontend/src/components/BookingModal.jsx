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

export default function BookingModal({ isOpen, onClose, bookingData, onBooked, tripId }) {
  const [step, setStep] = useState(0);            // 0=Review, 1=Payment, 2=Confirmed
  const [profile, setProfile] = useState(null);     // User profile from API
  const [loading, setLoading] = useState(false);     // Profile fetch spinner
  const [processing, setProcessing] = useState(false); // Payment processing spinner
  const [paymentMethod, setPaymentMethod] = useState('upi'); // upi | card
  const [pnr, setPnr] = useState('');               // PNR after booking
  const [error, setError] = useState('');
  const [paymentIntentId, setPaymentIntentId] = useState('');  // Stripe PI ID
  const [transactionId, setTransactionId] = useState('');      // Stripe txn ID
  const [receiptUrl, setReceiptUrl] = useState('');            // Stripe receipt URL
  const [travelDate, setTravelDate] = useState('');

  /* Reset wizard state every time the modal opens */
  useEffect(() => {
    if (isOpen && bookingData) {
      setTravelDate(bookingData.travelDate || '');
      setStep(0);
      setPnr('');
      setError('');
      setPaymentMethod('upi');
      setPaymentIntentId('');
      setTransactionId('');
      setReceiptUrl('');
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
   * Process payment via Stripe → then create the booking in the database.
   * Flow: create-intent → confirm → book → Telegram notification.
   */
  const handlePayment = async () => {
    setProcessing(true);
    setError('');

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { setError('Session expired. Please log in again.'); setProcessing(false); return; }

      const headers = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.access_token}`,
      };

      // ── Step A: Create Stripe PaymentIntent ──
      const priceNum = parseInt(getPrice().replace(/[^\d]/g, ''), 10) || 4899;
      const intentResp = await fetch(`${API_URL}/api/payment/create-intent`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          amount_inr: priceNum,
          booking_type: bookingData.bookingType,
          provider_name: bookingData.providerName,
          description: `TripPilot ${bookingData.bookingType} booking - ${bookingData.providerName}`,
        }),
      });

      if (!intentResp.ok) { setError('Failed to initialize payment. Try again.'); setProcessing(false); return; }
      const intentData = await intentResp.json();
      setPaymentIntentId(intentData.payment_intent_id);

      // ── Step B: Confirm the payment (Stripe test card auto-charge) ──
      const confirmResp = await fetch(`${API_URL}/api/payment/confirm`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ payment_intent_id: intentData.payment_intent_id }),
      });

      if (!confirmResp.ok) { setError('Payment declined. Please try again.'); setProcessing(false); return; }
      const confirmData = await confirmResp.json();
      setTransactionId(confirmData.transaction_id || confirmData.payment_intent_id);
      setReceiptUrl(confirmData.receipt_url || '');

      // ── Step C: Create the booking record in Supabase ──
      const bookResp = await fetch(`${API_URL}/api/book`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          trip_id: tripId,
          booking_type: bookingData.bookingType,
          provider_name: bookingData.providerName,
          travel_date: travelDate,
          details: {
            ...bookingData.details,
            payment_intent_id: intentData.payment_intent_id,
            transaction_id: confirmData.transaction_id,
            payment_method: confirmData.payment_method || paymentMethod,
            amount_paid: priceNum,
          },
        }),
      });

      if (bookResp.ok) {
        const data = await bookResp.json();
        setPnr(data.pnr_or_confirmation_number);
        setStep(2); // Move to Confirmed step
        if (onBooked) onBooked(data);
      } else {
        setError('Payment succeeded but booking save failed. Contact support.');
      }
    } catch (err) {
      console.error('Payment flow failed:', err);
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

                {/* Select Travel Date */}
                <div className="booking-section">
                  <h3><Calendar size={16} /> Travel Date</h3>
                  <div className="booking-info-grid">
                    <div className="booking-info-item" style={{ width: '100%' }}>
                      <span className="info-label">Select Date</span>
                      <input 
                        type="date" 
                        className="modal-input" 
                        value={travelDate}
                        onChange={(e) => setTravelDate(e.target.value)}
                        style={{ marginTop: '5px', padding: '8px', borderRadius: '6px', border: '1px solid var(--border)', background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
                      />
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

                <div style={{ display: 'flex', justifyContent: 'center', marginTop: '1.5rem', width: '100%' }}>
                  <button className="btn-primary booking-cta" onClick={() => setStep(1)}>
                    Continue to Payment <ChevronRight size={18} />
                  </button>
                </div>
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

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '1.5rem', width: '100%' }}>
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
            </div>

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

            {transactionId && (
              <div className="confirm-transaction">
                <div className="txn-row">
                  <span className="txn-label">Transaction ID</span>
                  <span className="txn-value">{transactionId}</span>
                </div>
                <div className="txn-row">
                  <span className="txn-label">Payment Status</span>
                  <span className="txn-value txn-success">✅ Succeeded</span>
                </div>
                {receiptUrl && (
                  <div className="txn-row">
                    <span className="txn-label">Receipt</span>
                    <a href={receiptUrl} target="_blank" rel="noopener noreferrer" className="txn-link">View Stripe Receipt →</a>
                  </div>
                )}
              </div>
            )}

            <div className="confirm-details">
              <p>📱 A confirmation has been sent to your Telegram (if linked).</p>
              <p>📧 Check your email for the full e-ticket.</p>
              {!transactionId && <p>💳 Payment processed via simulated gateway.</p>}
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '1.5rem', width: '100%' }}>
              <button className="btn-primary booking-cta" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
