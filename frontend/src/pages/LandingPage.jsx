import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Map, Sparkles, ArrowRight, ShieldCheck, CreditCard, MessageSquare, Heart } from 'lucide-react';

const FEATURES = [
  { icon: <Map size={24} />, title: 'Multi-Agent Routing', desc: 'Our AI dynamically coordinates flight, train, and hotel agents to build your perfect trip.' },
  { icon: <CreditCard size={24} />, title: 'Automated Expenses', desc: 'Track all booking costs instantly. Export beautiful PDF expense reports in one click.' },
  { icon: <MessageSquare size={24} />, title: 'Telegram Companion', desc: 'Manage your entire itinerary from Telegram. Ask questions and get real-time updates.' },
  { icon: <ShieldCheck size={24} />, title: 'SOS Emergency Alerts', desc: 'Travel safely with one-tap Twilio SMS and Voice alerts sent directly to your family.' },
];

const DESTINATIONS = [
  { name: 'Rishikesh', tag: 'Adventure', img: 'https://images.unsplash.com/photo-1587474260584-136574528ed5?auto=format&fit=crop&w=600&q=80' },
  { name: 'Goa', tag: 'Beaches', img: 'https://images.unsplash.com/photo-1512343879784-a960bf40e7f2?auto=format&fit=crop&w=600&q=80' },
  { name: 'Manali', tag: 'Mountains', img: 'https://images.unsplash.com/photo-1626621341517-bbf3d9990a23?auto=format&fit=crop&w=600&q=80' },
];

export default function LandingPage() {
  const navigate = useNavigate();

  return (
    <div className="landing" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      
      {/* Navbar */}
      <nav style={{ padding: '1.25rem 4rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--border)', background: 'var(--bg-card)', position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Added brightness(0) invert(1) for the dark theme to make the logo pure white */}
          <img src="/logo.png" alt="TripPilot" style={{ height: '56px', filter: 'brightness(0) invert(1)' }} />
        </div>
        <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'center' }}>
          <button style={{ background: 'transparent', border: 'none', fontWeight: 600, color: 'var(--text-secondary)', cursor: 'pointer', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'} onClick={() => navigate('/auth')}>Log in</button>
          <button className="btn-primary" style={{ padding: '0.6rem 1.5rem', fontSize: '0.9rem' }} onClick={() => navigate('/auth')}>Start for free</button>
        </div>
      </nav>

      {/* Hero Section */}
      <section style={{ padding: '6rem 4rem 4rem', display: 'flex', gap: '4rem', alignItems: 'center', maxWidth: '1400px', margin: '0 auto' }}>
        <motion.div style={{ flex: 1 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          
          <div className="hero-badge" style={{ 
            display: 'inline-flex', padding: '8px 16px', borderRadius: '99px', 
            fontSize: '0.85rem', fontWeight: 600, alignItems: 'center', gap: '8px', 
            marginBottom: '2rem'
          }}>
            <Sparkles size={16} /> Meet the all-new TripPilot
          </div>

          <h1 style={{ fontSize: '4.5rem', lineHeight: 1.1, marginBottom: '1.5rem', letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>
            Plan your next <br/><span style={{ color: 'var(--text-secondary)' }}>masterpiece.</span>
          </h1>
          
          <p style={{ fontSize: '1.2rem', color: 'var(--text-secondary)', marginBottom: '2.5rem', maxWidth: '520px', lineHeight: 1.6 }}>
            The AI-powered travel concierge that handles flights, trains, hotels, and itineraries. Fully synced with your Telegram for on-the-go access.
          </p>
          
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '2rem' }}>
            <button className="btn-primary" style={{ padding: '1rem 2rem', fontSize: '1.05rem', display: 'inline-flex', alignItems: 'center', gap: '8px', width: 'auto' }} onClick={() => navigate('/auth')}>
              Start Planning <ArrowRight size={18} />
            </button>
            <button style={{ 
              padding: '1rem 2rem', fontSize: '1.05rem', display: 'inline-flex', alignItems: 'center', gap: '8px',
              background: 'transparent', border: '1px solid var(--border)', borderRadius: '99px',
              color: 'var(--text-primary)', fontWeight: 600, cursor: 'pointer',
              transition: 'all 0.2s', width: 'auto'
            }} onMouseOver={e => e.target.style.background='var(--bg-card)'} onMouseOut={e => e.target.style.background='transparent'} onClick={() => document.getElementById('features').scrollIntoView({ behavior: 'smooth' })}>
              See how it works
            </button>
          </div>

        </motion.div>

        {/* Hero Image Masonry Grid */}
        <motion.div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.8, delay: 0.2 }}>
          <img src={DESTINATIONS[0].img} alt="Travel" style={{ width: '100%', height: '400px', objectFit: 'cover', borderRadius: '24px', marginTop: '40px', border: '1px solid var(--border)' }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <img src={DESTINATIONS[1].img} alt="Travel" style={{ width: '100%', height: '220px', objectFit: 'cover', borderRadius: '24px', border: '1px solid var(--border)' }} />
            <img src={DESTINATIONS[2].img} alt="Travel" style={{ width: '100%', height: '300px', objectFit: 'cover', borderRadius: '24px', border: '1px solid var(--border)' }} />
          </div>
        </motion.div>
      </section>

      {/* Features Grid */}
      <section id="features" style={{ padding: '8rem 4rem', maxWidth: '1200px', margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '5rem' }}>
          <h2 style={{ fontSize: '3.5rem', marginBottom: '1.5rem', letterSpacing: '-0.02em' }}>Everything you need.</h2>
          <p style={{ fontSize: '1.2rem', color: 'var(--text-secondary)', maxWidth: '600px', margin: '0 auto', lineHeight: 1.6 }}>From booking to expenses to emergency alerts, TripPilot is your complete travel operating system.</p>
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '2rem' }}>
          {FEATURES.map((f, i) => (
            <motion.div key={f.title} className="feature-card" style={{ padding: '2.5rem', borderRadius: '24px', background: 'var(--bg-card)', border: '1px solid var(--border)', transition: 'transform 0.3s' }} whileHover={{ y: -5 }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }}>
              <div style={{ width: '56px', height: '56px', borderRadius: '16px', background: '#27272A', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '2rem' }}>
                {f.icon}
              </div>
              <h3 style={{ fontSize: '1.4rem', marginBottom: '1rem', fontWeight: 700 }}>{f.title}</h3>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.6, fontSize: '1rem' }}>{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Footer CTA */}
      <section style={{ background: '#18181B', color: 'white', padding: '8rem 4rem', textAlign: 'center', marginTop: 'auto', borderTop: '1px solid var(--border)' }}>
        <h2 style={{ fontSize: '4rem', color: 'white', marginBottom: '1.5rem', letterSpacing: '-0.02em' }}>Ready to travel?</h2>
        <p style={{ fontSize: '1.3rem', color: '#A1A1AA', marginBottom: '3rem', maxWidth: '500px', margin: '0 auto', lineHeight: 1.6 }}>Join thousands of travelers planning their trips effortlessly with our AI.</p>
        <button className="btn-primary" style={{ margin: '0 auto', width: 'auto', display: 'inline-flex', padding: '1.2rem 3rem', fontSize: '1.1rem', transition: 'transform 0.2s' }} onMouseOver={e => e.target.style.transform='scale(1.05)'} onMouseOut={e => e.target.style.transform='scale(1)'} onClick={() => navigate('/auth')}>
          Create Free Account
        </button>
      </section>

      {/* Footer */}
      <footer style={{ background: 'var(--bg-primary)', borderTop: '1px solid var(--border)', padding: '4rem' }}>
        <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: '3rem' }}>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <img src="/logo.png" alt="TripPilot" style={{ height: '48px', width: 'fit-content', filter: 'brightness(0) invert(1)' }} />
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', lineHeight: 1.6, maxWidth: '300px' }}>
              The premium AI travel concierge. We handle the routing, booking, and expenses so you can focus on the journey.
            </p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Product</h4>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Features</a>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Pricing</a>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Telegram Bot</a>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Legal</h4>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Privacy Policy</a>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Terms of Service</a>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Cookie Policy</a>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h4 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>Support</h4>
            <a href="mailto:abhishekrastogi151@gmail.com" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '8px', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>
              abhishekrastogi151@gmail.com
            </a>
            <a href="#" style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '0.95rem', transition: 'color 0.2s' }} onMouseOver={e => e.target.style.color='var(--text-primary)'} onMouseOut={e => e.target.style.color='var(--text-secondary)'}>Help Center</a>
          </div>

        </div>

        <div style={{ maxWidth: '1200px', margin: '3rem auto 0', paddingTop: '2rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>© 2026 TripPilot Inc. All rights reserved.</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            Made with <Heart size={14} color="var(--red)" fill="var(--red)" /> by Abhishek
          </div>
        </div>
      </footer>

    </div>
  );
}
