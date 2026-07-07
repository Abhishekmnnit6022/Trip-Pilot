import { useState } from 'react';
import { MapPin, Calendar, Users, Search } from 'lucide-react';

export default function TravelWidget({ onSubmit, disabled }) {
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [travelers, setTravelers] = useState('1');
  const [expanded, setExpanded] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!destination.trim()) return;

    let prompt = `Plan a trip to ${destination.trim()}`;
    if (origin.trim()) prompt += ` from ${origin.trim()}`;
    if (startDate) {
      const sd = new Date(startDate);
      prompt += ` starting ${sd.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}`;
    }
    if (endDate && startDate) {
      const s = new Date(startDate);
      const e = new Date(endDate);
      const days = Math.ceil((e - s) / (1000 * 60 * 60 * 24)) + 1;
      if (days > 0) prompt += ` for ${days} days`;
    }
    if (travelers && travelers !== '2') {
      prompt += ` for ${travelers} people`;
    }
    prompt += '.';

    onSubmit(prompt);

    // Reset
    setOrigin('');
    setDestination('');
    setStartDate('');
    setEndDate('');
    setTravelers('1');
    setExpanded(false);
  };

  // Get today in YYYY-MM-DD for the date inputs
  const today = new Date().toISOString().split('T')[0];

  return (
    <div className="travel-widget">
      {!expanded ? (
        <button
          className="travel-widget-toggle"
          onClick={() => setExpanded(true)}
          type="button"
          disabled={disabled}
        >
          <Search size={16} />
          <span>Quick Search — Fill in trip details</span>
        </button>
      ) : (
        <form className="travel-widget-form" onSubmit={handleSubmit}>
          <div className="tw-row">
            <div className="tw-field">
              <label><MapPin size={14} /> From</label>
              <input
                type="text"
                placeholder="Delhi"
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
              />
            </div>
            <div className="tw-field">
              <label><MapPin size={14} /> To</label>
              <input
                type="text"
                placeholder="Goa"
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="tw-row">
            <div className="tw-field">
              <label><Calendar size={14} /> Start Date</label>
              <input
                type="date"
                value={startDate}
                min={today}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="tw-field">
              <label><Calendar size={14} /> End Date</label>
              <input
                type="date"
                value={endDate}
                min={startDate || today}
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
            <div className="tw-field tw-field-small">
              <label><Users size={14} /> Travelers</label>
              <input
                type="number"
                min="1"
                max="20"
                value={travelers}
                onChange={(e) => setTravelers(e.target.value)}
              />
            </div>
          </div>
          <div className="tw-actions">
            <button type="submit" className="tw-btn-search" disabled={disabled || !destination.trim()}>
              <Search size={16} /> Search Trip
            </button>
            <button type="button" className="tw-btn-cancel" onClick={() => setExpanded(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
