/**
 * ProfileModal.jsx — User Profile Editor
 *
 * A modal that allows users to view and edit their profile:
 *   - Full Name, Phone Number, Date of Birth
 *   - Travel Preferences (chips)
 *   - Emergency Contact (name + phone)
 *   - Telegram Linking
 *
 * Props:
 *   @param {boolean}  isOpen  - Controls modal visibility
 *   @param {Function} onClose - Callback to close the modal
 */

import { useState, useEffect } from 'react';
import { supabase, API_URL } from '../lib/supabase';
import { X, User, Phone, Calendar, Heart, Save, Loader2, Shield, AlertTriangle } from 'lucide-react';

export default function ProfileModal({ isOpen, onClose, mandatory, onProfileComplete, userId }) {
  /* ── State ──────────────────────────────────────────────────────────────── */
  const [profile, setProfile] = useState({
    full_name: '',
    phone_number: '',
    birth_date: '',
    travel_preferences: {},
    emergency_contact_name: '',
    emergency_contact_phone: '',
    travel_twin_profile: null,
  });
  const [activeTab, setActiveTab] = useState('basic'); // 'basic' | 'twin'
  const [telegramChatId, setTelegramChatId] = useState('');
  const [telegramLinked, setTelegramLinked] = useState(false);
  const [botUsername, setBotUsername] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  /* ── Fetch profile when modal opens ─────────────────────────────────────── */
  useEffect(() => {
    if (isOpen) {
      fetchProfile();
      setSaved(false);
    }
  }, [isOpen]);

  /**
   * Fetch the authenticated user's profile from the backend API.
   * Also fetches bot info for the Telegram linking section.
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
        setProfile({
          full_name: data.full_name || '',
          phone_number: data.phone_number || '',
          birth_date: data.birth_date || '',
          travel_preferences: data.travel_preferences || {},
          emergency_contact_name: data.emergency_contact_name || '',
          emergency_contact_phone: data.emergency_contact_phone || '',
          travel_twin_profile: data.travel_twin_profile || null,
        });
        if (data.telegram_chat_id) {
          setTelegramChatId(data.telegram_chat_id);
          setTelegramLinked(true);
        }
      }
      // Fetch bot info for the Telegram linking section
      const botResp = await fetch(`${API_URL}/api/telegram/bot-info`);
      if (botResp.ok) {
        const botData = await botResp.json();
        if (botData.username) setBotUsername(botData.username);
      }
    } catch (err) {
      console.error('Failed to fetch profile:', err);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Save the profile data to the backend via PUT /api/profile.
   * Shows a success indicator for 2.5 seconds after saving.
   */
  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      const resp = await fetch(`${API_URL}/api/profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(profile),
      });
      if (resp.ok) {
        setSaved(true);
        if (mandatory && profile.full_name && profile.phone_number && profile.birth_date) {
            onProfileComplete();
        }
        setTimeout(() => setSaved(false), 2500);
      }
    } catch (err) {
      console.error('Failed to save profile:', err);
    } finally {
      setSaving(false);
    }
  };

  /* ── Travel preference chip options ─────────────────────────────────────── */
  const PREFERENCE_OPTIONS = [
    { key: 'budget', label: 'Budget Traveler', emoji: '💰' },
    { key: 'luxury', label: 'Luxury', emoji: '✨' },
    { key: 'adventure', label: 'Adventure', emoji: '🏔️' },
    { key: 'beach', label: 'Beach & Relax', emoji: '🏖️' },
    { key: 'culture', label: 'Culture & History', emoji: '🏛️' },
    { key: 'food', label: 'Food & Culinary', emoji: '🍜' },
    { key: 'nature', label: 'Nature & Wildlife', emoji: '🌿' },
    { key: 'spiritual', label: 'Spiritual & Pilgrimage', emoji: '🙏' },
  ];

  /** Toggle a travel preference chip on/off. */
  const togglePreference = (key) => {
    setProfile((prev) => ({
      ...prev,
      travel_preferences: {
        ...prev.travel_preferences,
        [key]: !prev.travel_preferences[key],
      },
    }));
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={mandatory ? null : onClose}>
      <div className="auth-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '480px', padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', maxHeight: '90vh' }}>
        <div className="auth-header" style={{ margin: 0, padding: '2rem 2.5rem 1rem', borderBottom: '1px solid var(--border)' }}>
          <h2 style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>Edit Profile</span>
            {!mandatory && <button className="close-btn" onClick={onClose}><X size={20} /></button>}
          </h2>
          
          {mandatory && <div style={{background: "var(--orange)", padding: "10px", borderRadius: "8px", marginBottom: "1rem", color: "#fff", fontSize: "0.9rem"}}>⚠️ Please complete your basic info to start planning trips!</div>}
          <div className="profile-tabs">
            <button className={`tab-btn ${activeTab === 'basic' ? 'active' : ''}`} onClick={() => setActiveTab('basic')}>Basic Info</button>
            <button className={`tab-btn ${activeTab === 'twin' ? 'active' : ''}`} onClick={() => setActiveTab('twin')}>🧠 My Travel Twin</button>
          </div>
        </div>

        {loading ? (
          <div className="modal-loading">
            <Loader2 size={28} className="spin" />
            <span>Loading profile…</span>
          </div>
        ) : (
          <div className="modal-body" style={{ padding: '2rem 2.5rem', overflowY: 'auto' }}>
            
            {activeTab === 'basic' && (
              <>
                {/* Full Name */}
            <div className="profile-field">
              <label><User size={16} /> Full Name</label>
              <input
                type="text"
                placeholder="Your full name"
                value={profile.full_name}
                onChange={(e) => setProfile({ ...profile, full_name: e.target.value })}
              />
            </div>

            {/* Phone Number */}
            <div className="profile-field">
              <label><Phone size={16} /> Phone Number</label>
              <input
                type="tel"
                placeholder="+91 98765 43210"
                value={profile.phone_number}
                onChange={(e) => setProfile({ ...profile, phone_number: e.target.value })}
              />
            </div>

            {/* Date of Birth */}
            <div className="profile-field">
              <label><Calendar size={16} /> Date of Birth</label>
              <input
                type="date"
                value={profile.birth_date}
                onChange={(e) => setProfile({ ...profile, birth_date: e.target.value })}
              />
            </div>

            {/* Travel Preferences */}
            <div className="profile-field">
              <label><Heart size={16} /> Travel Preferences</label>
              <div className="preference-chips">
                {PREFERENCE_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    className={`pref-chip ${profile.travel_preferences[opt.key] ? 'active' : ''}`}
                    onClick={() => togglePreference(opt.key)}
                    type="button"
                  >
                    <span>{opt.emoji}</span> {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Emergency Contact */}
            <div className="profile-field emergency-section">
              <label><AlertTriangle size={16} /> Emergency Contact (SOS)</label>
              <p className="field-help">
                This contact will be auto-called via our Telegram SOS feature if you trigger an emergency.
              </p>
              <div className="emergency-fields">
                <input
                  type="text"
                  placeholder="Contact Name (e.g., Mom)"
                  value={profile.emergency_contact_name}
                  onChange={(e) => setProfile({ ...profile, emergency_contact_name: e.target.value })}
                />
                <input
                  type="tel"
                  placeholder="+91 98765 43210"
                  value={profile.emergency_contact_phone}
                  onChange={(e) => setProfile({ ...profile, emergency_contact_phone: e.target.value })}
                />
              </div>
            </div>

            {/* Telegram Linking */}
            <div className="profile-field">
              <label>📱 Telegram Notifications</label>
              {telegramLinked ? (
                <div className="telegram-linked">
                  ✅ Linked (Chat ID: {telegramChatId})
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    {botUsername && userId ? (
                      <>
                        <img 
                          src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent('https://t.me/' + botUsername + '?start=' + userId)}`} 
                          alt="Telegram QR Code" 
                          style={{ borderRadius: '8px', border: '1px solid var(--border)' }}
                        />
                        <p className="telegram-help" style={{ flex: 1, margin: 0 }}>
                          <b>Scan this QR code</b> with your phone's camera to instantly link your Telegram account.<br/><br/>
                          No manual entry required! The bot will securely read your unique ID.
                        </p>
                      </>
                    ) : (
                      <p className="telegram-help">
                        Telegram bot not configured yet or User ID missing.
                      </p>
                    )}
                  </div>
                </>
              )}
            </div>
            </>
            )}

            {activeTab === 'twin' && (
              <div className="travel-twin-dashboard">
                <p className="twin-intro">
                  TripPilot autonomously learns your travel habits from your bookings to build a highly personalized profile.
                </p>
                
                {profile.travel_twin_profile ? (
                  <>
                    <div className="twin-metrics">
                      <div className="twin-metric">
                        <div className="metric-header">
                          <span>Budget Sensitivity</span>
                          <span>{profile.travel_twin_profile.budget_sensitivity}/100</span>
                        </div>
                        <div className="metric-bar-bg">
                          <div className="metric-bar-fill" style={{ width: `${profile.travel_twin_profile.budget_sensitivity}%` }}></div>
                        </div>
                      </div>

                      <div className="twin-metric">
                        <div className="metric-header">
                          <span>Hotel Preference</span>
                          <span>{profile.travel_twin_profile.hotel_preference_stars} ⭐</span>
                        </div>
                        <div className="metric-bar-bg">
                          <div className="metric-bar-fill" style={{ width: `${(profile.travel_twin_profile.hotel_preference_stars / 5) * 100}%`, background: 'var(--orange)' }}></div>
                        </div>
                      </div>
                      
                      <div className="twin-grid">
                        <div className="twin-stat-box">
                          <span className="stat-label">Walking</span>
                          <span className="stat-value" style={{textTransform:'capitalize'}}>{profile.travel_twin_profile.walking_tolerance}</span>
                        </div>
                        <div className="twin-stat-box">
                          <span className="stat-label">Adventure</span>
                          <span className="stat-value" style={{textTransform:'capitalize'}}>{profile.travel_twin_profile.adventure_preference}</span>
                        </div>
                        <div className="twin-stat-box">
                          <span className="stat-label">Early Mornings</span>
                          <span className="stat-value" style={{textTransform:'capitalize'}}>{profile.travel_twin_profile.early_mornings}</span>
                        </div>
                        <div className="twin-stat-box">
                          <span className="stat-label">Food</span>
                          <span className="stat-value" style={{textTransform:'capitalize'}}>{profile.travel_twin_profile.food_preference}</span>
                        </div>
                      </div>
                    </div>

                    <div className="twin-insights">
                      <h4>✨ AI Insights</h4>
                      {profile.travel_twin_profile.insights?.length > 0 ? (
                        <ul>
                          {profile.travel_twin_profile.insights.map((ins, i) => (
                            <li key={i}>{ins}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="no-insights">No insights yet. Make some bookings to teach the AI!</p>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="twin-empty">
                    <Loader2 size={24} className="spin" style={{margin:'0 auto 10px'}}/>
                    <p>Generating your Travel Twin...</p>
                  </div>
                )}
              </div>
            )}

            {/* Save Button */}
            <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'center', width: '100%' }}>
              <button className="btn-primary" onClick={handleSave} disabled={saving}>
              {saving ? (
                <><Loader2 size={18} className="spin" /> Saving…</>
              ) : saved ? (
                '✅ Saved!'
              ) : (
                <><Save size={18} /> Save Profile</>
              )}
            </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
