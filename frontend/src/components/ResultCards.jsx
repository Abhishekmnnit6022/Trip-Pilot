import { ExternalLink } from 'lucide-react';

export function FlightCard({ flight }) {
  return (
    <div className="result-card flight-card">
      <div className="card-badge">✈️ Flight</div>
      <h4>{flight.airline}</h4>
      <p className="card-flight-number">{flight.flight_number}</p>
      <div className="card-route">
        <div className="card-point">
          <span className="card-label">From</span>
          <span className="card-value">{flight.departure_airport}</span>
          <span className="card-time">{flight.departure_time ? new Date(flight.departure_time).toLocaleString() : 'N/A'}</span>
        </div>
        <div className="card-arrow">→</div>
        <div className="card-point">
          <span className="card-label">To</span>
          <span className="card-value">{flight.arrival_airport}</span>
          <span className="card-time">{flight.arrival_time ? new Date(flight.arrival_time).toLocaleString() : 'N/A'}</span>
        </div>
      </div>
      <div className="card-status">Status: {flight.status}</div>
      {flight.booking_url && (
        <a href={flight.booking_url} target="_blank" rel="noopener noreferrer" className="btn-book">
          Book on MakeMyTrip <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}

export function TrainCard({ train }) {
  return (
    <div className="result-card train-card">
      <div className="card-badge">🚂 Train</div>
      <h4>{train.train_name}</h4>
      <p className="card-flight-number">#{train.train_number}</p>
      <div className="card-route">
        <div className="card-point">
          <span className="card-label">From</span>
          <span className="card-value">{train.departure_station}</span>
          <span className="card-time">{train.departure_time}</span>
        </div>
        <div className="card-arrow">→</div>
        <div className="card-point">
          <span className="card-label">To</span>
          <span className="card-value">{train.arrival_station}</span>
          <span className="card-time">{train.arrival_time}</span>
        </div>
      </div>
      <div className="card-meta">
        <span>⏱ {train.duration}</span>
        <span>🎫 {train.classes}</span>
        <span>📅 {train.runs_on}</span>
      </div>
      {train.booking_url && (
        <a href={train.booking_url} target="_blank" rel="noopener noreferrer" className="btn-book btn-book-irctc">
          Book on IRCTC <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}

export function HotelCard({ hotel }) {
  const priceDisplay = typeof hotel.price === 'number'
    ? `₹${hotel.price.toLocaleString()}`
    : hotel.price || 'N/A';

  return (
    <div className="result-card hotel-card">
      <div className="card-badge">🏨 Hotel</div>
      {hotel.photo_url && (
        <img src={hotel.photo_url} alt={hotel.name} className="hotel-photo" />
      )}
      <h4>{hotel.name}</h4>
      <div className="hotel-rating">
        <span className="rating-score">{hotel.rating}</span>
        <span className="rating-word">{hotel.rating_word}</span>
      </div>
      <div className="hotel-price">{priceDisplay}</div>
      {hotel.amenities && <p className="hotel-amenities">{hotel.amenities}</p>}
      {hotel.booking_url && (
        <a href={hotel.booking_url} target="_blank" rel="noopener noreferrer" className="btn-book btn-book-hotel">
          Book on Booking.com <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}
