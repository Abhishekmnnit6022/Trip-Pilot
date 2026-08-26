/**
 * FinalPlanCard.jsx — Premium visual renderer for the AI's final trip summary.
 *
 * Parses the plain markdown text from final_agent and renders it as
 * structured, beautiful sections: Overview, Itinerary Timeline, 
 * Packing Checklist, Tips, and Emergency Contacts.
 */
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Map, Luggage, Lightbulb, Phone, Brain, ChevronDown, ChevronUp,
  Plane, Train, Hotel, Clock, Wallet, CheckCircle2, AlertCircle
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// ── Section config ─────────────────────────────────────────────
const SECTIONS = [
  { key: 'overview',   icon: Map,          label: 'Trip Overview',          color: '#3b82f6' },
  { key: 'itinerary', icon: Clock,         label: 'Complete Itinerary',     color: '#06b6d4' },
  { key: 'packing',   icon: Luggage,       label: 'Packing Checklist',      color: '#8b5cf6' },
  { key: 'tips',      icon: Lightbulb,     label: 'Travel Tips',            color: '#f59e0b' },
  { key: 'emergency', icon: Phone,         label: 'Emergency Contacts',     color: '#ef4444' },
  { key: 'twin',      icon: Brain,         label: 'Travel Twin Insight',    color: '#10b981' },
];

// ── Parse the markdown text into labelled sections ─────────────
function parseSections(text) {
  const sections = {};
  let current = 'overview';
  const lines = text.split('\n');

  lines.forEach(line => {
    const lc = line.toLowerCase();
    
    // Only switch sections if the line looks like a header (starts with # or **)
    if (line.match(/^(#+|\*\*)/)) {
      if (lc.includes('packing') || lc.includes('checklist')) { current = 'packing'; }
      else if (lc.includes('emergency') || lc.includes('useful info')) { current = 'emergency'; }
      else if (lc.includes('travel tip') || lc.includes('important tip')) { current = 'tips'; }
      else if (lc.includes('itinerary')) { current = 'itinerary'; }
      else if (lc.includes('twin') || lc.includes('personaliz')) { current = 'twin'; }
      else if (lc.includes('overview') || lc.includes('trip plan')) { current = 'overview'; }
    }

    sections[current] = (sections[current] || '') + line + '\n';
  });

  return sections;
}

// ── Collapsible section ────────────────────────────────────────
function Section({ icon: Icon, label, color, content, defaultOpen = false, delay = 0 }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <motion.div
      className="fp-section"
      style={{ borderLeftColor: color }}
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
    >
      <button className="fp-section-header" onClick={() => setOpen(o => !o)}>
        <div className="fp-section-title">
          <span className="fp-icon" style={{ background: `${color}18`, border: `1px solid ${color}30` }}>
            <Icon size={15} color={color} />
          </span>
          <span style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '0.95rem' }}>{label}</span>
        </div>
        {open ? <ChevronUp size={16} color="var(--text-muted)" /> : <ChevronDown size={16} color="var(--text-muted)" />}
      </button>

      {open && (
        <motion.div
          className="fp-section-body"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25 }}
        >
          <div className="fp-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}

// ── Extract the title from first heading ──────────────────────
function extractTitle(text) {
  const match = text.match(/^#+\s*(.+)/m);
  return match ? match[1].replace(/^🚆\s*/, '').trim() : 'Your Trip Plan';
}

// ── Main component ─────────────────────────────────────────────
export default function FinalPlanCard({ content }) {
  if (!content) return null;
  const sections = parseSections(content);
  const title = extractTitle(content);

  return (
    <motion.div
      className="fp-card"
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      {/* ── Header ── */}
      <div className="fp-header">
        <div className="fp-header-icon">🗺️</div>
        <div>
          <h3 className="fp-title">{title}</h3>
          <p className="fp-subtitle">Your personalized AI trip plan</p>
        </div>
      </div>

      {/* ── Sections ── */}
      <div className="fp-sections">
        {SECTIONS.map((s, i) => {
          const text = sections[s.key];
          if (!text?.trim()) return null;
          return (
            <Section
              key={s.key}
              icon={s.icon}
              label={s.label}
              color={s.color}
              content={text}
              defaultOpen={i === 0}
              delay={i * 0.06}
            />
          );
        })}
      </div>
    </motion.div>
  );
}
