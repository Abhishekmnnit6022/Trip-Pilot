import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plane, Train, Hotel, Map, Sparkles, ArrowRight } from 'lucide-react';

const FEATURES = [
  { icon: <Plane size={24} />, title: 'Flight Search', desc: 'Real-time flight data with booking links to MakeMyTrip & Skyscanner' },
  { icon: <Train size={24} />, title: 'Train Search', desc: 'Find Indian Railways trains with direct IRCTC booking access' },
  { icon: <Hotel size={24} />, title: 'Hotel Discovery', desc: 'Hotels from Booking.com with prices, ratings & photos' },
  { icon: <Map size={24} />, title: 'Smart Itinerary', desc: 'AI-generated day-by-day travel plans with local tips' },
];

const DESTINATIONS = [
  { name: 'Rishikesh', emoji: '🏔️', img: 'https://images.unsplash.com/photo-1587474260584-136574528ed5?w=400&q=70' },
  { name: 'Goa', emoji: '🏖️', img: 'https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?w=400&q=70' },
  { name: 'Manali', emoji: '⛰️', img: 'https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?w=400&q=70' },
  { name: 'Jaipur', emoji: '🏰', img: 'https://images.unsplash.com/photo-1477587458883-47145ed94245?w=400&q=70' },
  { name: 'Kerala', emoji: '🌴', img: 'https://images.unsplash.com/photo-1602216056096-3b40cc0c9944?w=400&q=70' },
];

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="landing">
      {/* Hero */}
      <section className="hero">
        <motion.div
          className="hero-content"
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <div className="hero-badge">
            <Sparkles size={14} />
            <span>AI-Powered Multi-Agent System</span>
          </div>
          <h1>Plan Your Dream Trip<br />in Seconds</h1>
          <p className="hero-sub">
            Tell our AI where you want to go — it searches flights, trains, hotels,
            and builds a complete itinerary for you. Powered by LangGraph.
          </p>
          <button className="btn-hero" onClick={() => navigate('/auth')}>
            Start Planning <ArrowRight size={20} />
          </button>
        </motion.div>
        <div className="hero-glow" />
      </section>

      {/* Destinations */}
      <section className="destinations">
        <h2>Popular Destinations</h2>
        <div className="dest-grid">
          {DESTINATIONS.map((d, i) => (
            <motion.div
              key={d.name}
              className="dest-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
              onClick={() => navigate('/auth')}
            >
              <img src={d.img} alt={d.name} />
              <div className="dest-overlay">
                <span className="dest-emoji">{d.emoji}</span>
                <span className="dest-name">{d.name}</span>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="features">
        <h2>How It Works</h2>
        <div className="features-grid">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              className="feature-card"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 + i * 0.1 }}
            >
              <div className="feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <p>Built with LangGraph · Groq · Tavily · AviationStack · Supabase</p>
      </footer>
    </div>
  );
}
