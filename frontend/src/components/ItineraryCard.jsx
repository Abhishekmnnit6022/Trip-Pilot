/**
 * ItineraryCard.jsx — Premium Day-by-Day Itinerary Card
 *
 * Features a glassmorphism "Day Badge", full-bleed hero image with overlay,
 * horizontally scrollable place cards with staggered entrance animations,
 * and a consistent dark-teal theme.
 */
import React, { useState, useEffect, useRef } from 'react';
import { MapPin, Clock, Wallet, Star, ChevronLeft, ChevronRight, Compass } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// High-quality Unsplash fallback IDs
const FALLBACK_IDS = [
  '1587474260584-136574528ed5',
  '1512343879784-a960bf40e7f2',
  '1626621341517-bbf3d9990a23',
  '1476514525535-07fb3b4ae5f1',
  '1524492412937-b6154bb39ed9',
  '1548013146-563604f3bf12',
  '1501785888041-af3ef285b470',
  '1499856871958-5b9627545d1a',
];

// Map day_number to a gradient accent for variety
const DAY_ACCENTS = [
  'linear-gradient(135deg, #3b82f6, #06b6d4)',
  'linear-gradient(135deg, #8b5cf6, #3b82f6)',
  'linear-gradient(135deg, #10b981, #3b82f6)',
  'linear-gradient(135deg, #f59e0b, #ef4444)',
  'linear-gradient(135deg, #06b6d4, #10b981)',
  'linear-gradient(135deg, #ec4899, #8b5cf6)',
  'linear-gradient(135deg, #f59e0b, #3b82f6)',
];

export default function ItineraryCard({ day, dayIndex = 0 }) {
  const [images, setImages] = useState({});
  const [loadedImages, setLoadedImages] = useState({});
  const scrollRef = useRef(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(true);

  // Fetch Wikipedia images for each place
  useEffect(() => {
    if (!day?.places) return;
    day.places.forEach(async (place) => {
      try {
        const url = `https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=${encodeURIComponent(place.name)}&gsrlimit=1&prop=pageimages&format=json&pithumbsize=800&origin=*`;
        const res = await fetch(url);
        const data = await res.json();
        if (data.query?.pages) {
          const pages = Object.values(data.query.pages);
          if (pages[0]?.thumbnail?.source) {
            setImages(prev => ({ ...prev, [place.name]: pages[0].thumbnail.source }));
          }
        }
      } catch { /* silent fail */ }
    });
  }, [day]);

  const getImage = (place) => {
    if (images[place.name]) return images[place.name];
    const hash = (place.image_search_query || place.name)
      .split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    const id = FALLBACK_IDS[hash % FALLBACK_IDS.length];
    return `https://images.unsplash.com/photo-${id}?auto=format&fit=crop&w=800&q=80`;
  };

  const accent = DAY_ACCENTS[(day.day_number - 1) % DAY_ACCENTS.length];

  const checkScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 10);
    setCanScrollRight(el.scrollLeft < el.scrollWidth - el.clientWidth - 10);
  };

  const scroll = (dir) => {
    scrollRef.current?.scrollBy({ left: dir * 320, behavior: 'smooth' });
  };

  if (!day?.places) return null;

  return (
    <motion.div
      className="itin-day-wrap"
      initial={{ opacity: 0, y: 32 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: dayIndex * 0.12, ease: [0.22, 1, 0.36, 1] }}
    >
      {/* ── Day Header ─────────────────────────────────────────── */}
      <div className="itin-day-header">
        <div className="itin-day-badge" style={{ background: accent }}>
          <Compass size={14} />
          <span>Day {day.day_number}</span>
        </div>
        <div className="itin-day-title-block">
          <h3 className="itin-day-title">Day {day.day_number}</h3>
          <p className="itin-day-theme">{day.theme}</p>
        </div>
        <div className="itin-day-count">{day.places.length} stops</div>
      </div>

      {/* ── Scroll Controls ─────────────────────────────────────── */}
      <div className="itin-scroll-zone">
        <AnimatePresence>
          {canScrollLeft && (
            <motion.button
              key="left"
              className="itin-scroll-btn itin-scroll-left"
              onClick={() => scroll(-1)}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
            >
              <ChevronLeft size={18} />
            </motion.button>
          )}
        </AnimatePresence>

        <div
          className="itin-cards-track"
          ref={scrollRef}
          onScroll={checkScroll}
        >
          {day.places.map((place, idx) => (
            <PlaceCard
              key={idx}
              place={place}
              idx={idx}
              dayIdx={dayIndex}
              imgSrc={getImage(place)}
              onImgLoad={() => setLoadedImages(p => ({ ...p, [place.name]: true }))}
              accent={accent}
            />
          ))}
        </div>

        <AnimatePresence>
          {canScrollRight && day.places.length > 2 && (
            <motion.button
              key="right"
              className="itin-scroll-btn itin-scroll-right"
              onClick={() => scroll(1)}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
            >
              <ChevronRight size={18} />
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

function PlaceCard({ place, idx, dayIdx, imgSrc, onImgLoad, accent }) {
  const [hovered, setHovered] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);

  const isFree = String(place.cost).toLowerCase() === 'free' || place.cost === '₹0';

  return (
    <motion.div
      className="itin-place-card"
      initial={{ opacity: 0, x: 40, scale: 0.94 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      transition={{
        duration: 0.45,
        delay: dayIdx * 0.08 + idx * 0.09,
        ease: [0.22, 1, 0.36, 1],
      }}
      whileHover={{ y: -6, scale: 1.02 }}
      onHoverStart={() => setHovered(true)}
      onHoverEnd={() => setHovered(false)}
    >
      {/* ── Image ──────────────────────────────────────────────── */}
      <div className="itin-img-wrap">
        {!imgLoaded && <div className="itin-img-skeleton" />}
        <motion.img
          src={imgSrc}
          alt={place.name}
          loading="lazy"
          onLoad={() => { setImgLoaded(true); onImgLoad?.(); }}
          animate={{ opacity: imgLoaded ? 1 : 0, scale: hovered ? 1.07 : 1 }}
          transition={{ duration: 0.5 }}
          style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', inset: 0 }}
        />

        {/* Gradient overlay */}
        <div className="itin-img-overlay" />

        {/* Rating badge */}
        <div className="itin-rating-badge">
          <Star size={10} fill="#f59e0b" color="#f59e0b" />
          <span>{place.rating || '4.5'}</span>
        </div>

        {/* Stop number */}
        <div className="itin-stop-num" style={{ background: accent }}>
          #{idx + 1}
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────── */}
      <div className="itin-card-body">
        <h4 className="itin-place-name">{place.name}</h4>

        <div className="itin-meta-row">
          <span className="itin-meta-chip">
            <MapPin size={11} /> {place.address?.split(',').slice(-2).join(',').trim() || place.address}
          </span>
        </div>

        <div className="itin-meta-row">
          <span className="itin-meta-chip">
            <Clock size={11} /> {place.timing}
          </span>
          <span className={`itin-cost-chip ${isFree ? 'itin-cost-free' : ''}`}>
            <Wallet size={11} /> {place.cost}
          </span>
        </div>

        <p className="itin-place-desc">{place.description}</p>
      </div>

      {/* Glow accent on hover */}
      <motion.div
        className="itin-card-glow"
        style={{ background: accent }}
        animate={{ opacity: hovered ? 0.12 : 0 }}
        transition={{ duration: 0.3 }}
      />
    </motion.div>
  );
}
