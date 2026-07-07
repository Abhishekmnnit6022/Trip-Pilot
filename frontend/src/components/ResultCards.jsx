/**
 * ResultCards.jsx — Flight, Train, and Hotel result cards
 *
 * Each card displays structured travel data returned by the AI agents
 * and provides a "Book Now" button that opens the BookingModal.
 *
 * Exports:
 *   FlightCard({ flight, onBook })  — Renders a single flight result
 *   TrainCard({ train, onBook })    — Renders a single train result
 *   HotelCard({ hotel, onBook })    — Renders a single hotel result
 *
 * @param {Function} onBook - Callback receiving { bookingType, providerName, travelDate, details }
 */

import { Plane, Train as TrainIcon, Hotel, Star, Clock, Ticket, CalendarDays } from 'lucide-react';

/* ═══════════════════════════════════════════════════════════════════════════
   FLIGHT CARD
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Render a single flight search result as a premium card.
 *
 * @param {Object}   props.flight - Flight data from AviationStack / Tavily
 * @param {Function} props.onBook - Opens the booking modal with this flight's data
 */
export function FlightCard({ flight, onBook }) {
  /** Format an ISO date string into a short, readable time. */
  const formatTime = (iso) => {
    if (!iso) return 'N/A';
    try { return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }
    catch { return iso; }
  };

  const handleBook = () => {
    onBook({
      bookingType: 'flight',
      providerName: flight.airline,
      travelDate: flight.travel_date || (flight.departure_time ? flight.departure_time.split('T')[0] : ''),
      details: {
        airline: flight.airline,
        flight_number: flight.flight_number,
        departure_airport: flight.departure_airport,
        arrival_airport: flight.arrival_airport,
        departure_time: flight.departure_time,
        arrival_time: flight.arrival_time,
      },
    });
  };

  return (
    <div className="result-card flight-card">
      <div className="card-badge"><Plane size={12} /> Flight</div>
      <h4>{flight.airline}</h4>
      <p className="card-flight-number">{flight.flight_number}</p>
      <div className="card-route">
        <div className="card-point">
          <span className="card-label">From</span>
          <span className="card-value">{flight.departure_airport}</span>
          <span className="card-time">{formatTime(flight.departure_time)}</span>
        </div>
        <div className="card-arrow">
          <div className="route-line" />
          <Plane size={14} className="route-icon" />
          <div className="route-line" />
        </div>
        <div className="card-point">
          <span className="card-label">To</span>
          <span className="card-value">{flight.arrival_airport}</span>
          <span className="card-time">{formatTime(flight.arrival_time)}</span>
        </div>
      </div>
      <div className="card-status">Status: {flight.status || 'Scheduled'}</div>
      <button className="btn-book btn-book-flight" onClick={handleBook}>
        Book Now <Plane size={14} />
      </button>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   TRAIN CARD
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Render a single train search result as a premium card.
 *
 * @param {Object}   props.train  - Train data from RailRadar / Tavily
 * @param {Function} props.onBook - Opens the booking modal with this train's data
 */
export function TrainCard({ train, onBook }) {
  const handleBook = () => {
    onBook({
      bookingType: 'train',
      providerName: train.train_name,
      travelDate: train.travel_date || '',
      details: {
        train_name: train.train_name,
        train_number: train.train_number,
        departure_station: train.departure_station,
        arrival_station: train.arrival_station,
        departure_time: train.departure_time,
        arrival_time: train.arrival_time,
        duration: train.duration,
      },
    });
  };

  return (
    <div className="result-card train-card">
      <div className="card-badge"><TrainIcon size={12} /> Train</div>
      <h4>{train.train_name}</h4>
      <p className="card-flight-number">#{train.train_number}</p>
      <div className="card-route">
        <div className="card-point">
          <span className="card-label">From</span>
          <span className="card-value">{train.departure_station}</span>
          <span className="card-time">{train.departure_time}</span>
        </div>
        <div className="card-arrow">
          <div className="route-line" />
          <TrainIcon size={14} className="route-icon" />
          <div className="route-line" />
        </div>
        <div className="card-point">
          <span className="card-label">To</span>
          <span className="card-value">{train.arrival_station}</span>
          <span className="card-time">{train.arrival_time}</span>
        </div>
      </div>
      <div className="card-meta">
        <span><Clock size={12} /> {train.duration}</span>
        <span><Ticket size={12} /> {train.classes}</span>
        <span><CalendarDays size={12} /> {train.runs_on}</span>
      </div>
      <button className="btn-book btn-book-train" onClick={handleBook}>
        Book Now <TrainIcon size={14} />
      </button>
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   HOTEL CARD
   ═══════════════════════════════════════════════════════════════════════════ */

/**
 * Render a single hotel search result as a premium card.
 *
 * @param {Object}   props.hotel  - Hotel data from Booking.com / Tavily
 * @param {Function} props.onBook - Opens the booking modal with this hotel's data
 */
export function HotelCard({ hotel, onBook }) {
  /** Format the price into a readable currency string. */
  const priceDisplay = typeof hotel.price === 'number'
    ? `₹${hotel.price.toLocaleString('en-IN')}`
    : hotel.price || 'N/A';

  /** Render star icons for the hotel rating. */
  const renderStars = () => {
    const score = parseFloat(hotel.rating) || 0;
    const starCount = Math.round(score / 2); // Convert 0-10 scale to 0-5 stars
    return (
      <div className="hotel-stars">
        {[1, 2, 3, 4, 5].map((s) => (
          <Star key={s} size={14} className={s <= starCount ? 'star-filled' : 'star-empty'} />
        ))}
      </div>
    );
  };

  const handleBook = () => {
    onBook({
      bookingType: 'hotel',
      providerName: hotel.name,
      travelDate: hotel.checkin || '',
      details: {
        name: hotel.name,
        rating: hotel.rating,
        price: hotel.price,
        checkin: hotel.checkin,
        checkout: hotel.checkout,
      },
    });
  };

  return (
    <div className="result-card hotel-card">
      <div className="card-badge"><Hotel size={12} /> Hotel</div>
      {hotel.photo_url && (
        <img src={hotel.photo_url} alt={hotel.name} className="hotel-photo" loading="lazy" />
      )}
      <h4>{hotel.name}</h4>
      <div className="hotel-rating">
        {renderStars()}
        <span className="rating-score">{hotel.rating}</span>
        <span className="rating-word">{hotel.rating_word}</span>
      </div>
      <div className="hotel-price">{priceDisplay}<span className="price-per">/night</span></div>
      {hotel.amenities && <p className="hotel-amenities">{hotel.amenities}</p>}
      <button className="btn-book btn-book-hotel" onClick={handleBook}>
        Book Now <Hotel size={14} />
      </button>
    </div>
  );
}
