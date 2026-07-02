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

export default function ProfileModal({ isOpen, onClose }) {
  /* ── State ──────────────────────────────────────────────────────────────── */
  const [profile, setProfile] = useState({
    full_name: '',
    phone_number: '',
    birth_date: '',
    travel_preferences: {},
    emergency_contact_name: '',
    emergency_contact_phone: '',
  });
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content profile-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>My Profile</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {loading ? (
          <div className="modal-loading">
            <Loader2 size={28} className="spin" />
            <span>Loading profile…</span>
          </div>
        ) : (
          <div className="modal-body">
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
                  <p className="telegram-help">
                    {botUsername ? (
                      <>1. Open <a href={`https://t.me/${botUsername}`} target="_blank" rel="noopener noreferrer">@{botUsername}</a> on Telegram and send <code>/start</code><br/>
                      2. The bot will reply with your Chat ID — paste it below:</>
                    ) : (
                      <>Telegram bot not configured yet. Add TELEGRAM_BOT_TOKEN to your .env file.</>
                    )}
                  </p>
                  <div className="telegram-link-row">
                    <input
                      type="text"
                      placeholder="Your Telegram Chat ID"
                      value={telegramChatId}
                      onChange={(e) => setTelegramChatId(e.target.value)}
                    />
                    <button
                      type="button"
                      className="tw-btn-search"
                      style={{ flex: '0 0 auto', padding: '8px 16px' }}
                      onClick={async () => {
                        if (!telegramChatId.trim()) return;
                        try {
                          const { data: { session } } = await supabase.auth.getSession();
                          if (!session) return;
                          const resp = await fetch(`${API_URL}/api/telegram/link`, {
                            method: 'POST',
                            headers: {
                              'Content-Type': 'application/json',
                              Authorization: `Bearer ${session.access_token}`,
                            },
                            body: JSON.stringify({ telegram_chat_id: telegramChatId }),
                          });
                          if (resp.ok) setTelegramLinked(true);
                        } catch (err) {
                          console.error('Telegram link failed:', err);
                        }
                      }}
                      disabled={!telegramChatId.trim()}
                    >
                      Link
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Save Button */}
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
        )}
      </div>
    </div>
  );
}
