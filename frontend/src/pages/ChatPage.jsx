/**
 * ChatPage.jsx — Main AI Chat Interface
 *
 * This is the primary page users interact with after authentication.
 * It handles:
 *   - SSE streaming of AI agent responses
 *   - Rendering of flight/train/hotel result cards
 *   - Opening the BookingModal for in-app booking
 *   - Sidebar with profile, bookings, and agent status
 *   - Mandatory profile completion for new users
 *
 * State Management:
 *   - messages[]       → Chat history (user, assistant, results, itinerary)
 *   - bookingModal     → Controls the BookingModal visibility and data
 *   - activeAgent      → Currently executing AI agent name
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase, API_URL } from '../lib/supabase';
import { FlightCard, TrainCard, HotelCard } from '../components/ResultCards';
import ProfileModal from '../components/ProfileModal';
import BookingModal from '../components/BookingModal';
import TravelWidget from '../components/TravelWidget';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, LogOut, Plus, Map, Bot, User,
  Loader2, UserCircle, Ticket, ChevronDown, MessageSquare
} from 'lucide-react';

/* ── Agent metadata for the sidebar & inline status indicators ────────────── */
const AGENT_LABELS = {
  router: { icon: '🧭', label: 'Routing…' },
  flight_agent: { icon: '✈️', label: 'Searching Flights' },
  train_agent: { icon: '🚂', label: 'Searching Trains' },
  hotel_agent: { icon: '🏨', label: 'Searching Hotels' },
  return_agent: { icon: '🔄', label: 'Searching Return Transport' },
  itinerary_agent: { icon: '📋', label: 'Generating Itinerary' },
  final_agent: { icon: '🧠', label: 'Finalizing Plan' },
  present_results: { icon: '📊', label: 'Preparing Results' },
};

/* ── Quick prompt suggestions for new conversations ───────────────────────── */
const QUICK_PROMPTS = [
  'Plan a trip to Rishikesh for 4 days',
  '7-day Goa trip under ₹30k',
  'Weekend trip to Manali from Delhi',
  'Kerala backwaters 5-day plan',
];

export default function ChatPage() {
  const navigate = useNavigate();

  /* ── Core state ─────────────────────────────────────────────────────────── */
  const [user, setUser] = useState(null);
  const [threadId, setThreadId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);

  /* ── Modal state ────────────────────────────────────────────────────────── */
  const [showProfile, setShowProfile] = useState(false);
  const [bookingModal, setBookingModal] = useState({ open: false, data: null });

  /* ── Sidebar state ──────────────────────────────────────────────────────── */
  const [bookings, setBookings] = useState([]);
  const [showBookings, setShowBookings] = useState(false);
  const [chatSessions, setChatSessions] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [botUsername, setBotUsername] = useState('');
  const [activeTripId, setActiveTripId] = useState(null);

  /* ── Refs ────────────────────────────────────────────────────────────────── */
  const messagesEndRef = useRef(null);

  /* ── Auth check & mandatory profile completion on mount ──────────────────── */
  useEffect(() => {
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) {
        navigate('/auth');
      } else {
        setUser(session.user);
        setThreadId(`${session.user.id}_${Date.now().toString(36)}`);

        // Ensure profile is complete (phone + DOB required)
        try {
          const resp = await fetch(`${API_URL}/api/profile`, {
            headers: { Authorization: `Bearer ${session.access_token}` },
          });
          if (resp.ok) {
            const data = await resp.json();
            if (!data.phone_number || !data.birth_date) {
              setShowProfile(true);
            }
          }
        } catch (err) {
          console.error('Failed to check profile status:', err);
        }
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) navigate('/auth');
      else setUser(session.user);
    });

    return () => subscription.unsubscribe();
  }, [navigate]);

  /* ── Auto-scroll chat to bottom on new messages ─────────────────────────── */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeAgent]);

  /* ── Fetch user bookings from backend ───────────────────────────────────── */
  const fetchBookings = useCallback(async () => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) return;
      const resp = await fetch(`${API_URL}/api/bookings`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (resp.ok) {
        const data = await resp.json();
        setBookings(data);
      }
    } catch (err) {
      console.error('Failed to fetch bookings:', err);
    }
  }, []);

  /* ── Fetch user chat sessions from Supabase ─────────────────────────────── */
  const fetchChatSessions = useCallback(async () => {
    try {
      const { data, error } = await supabase
        .from('chat_sessions')
        .select('*')
        .order('updated_at', { ascending: false });
      if (!error && data) {
        setChatSessions(data);
      }
    } catch (err) {
      console.error('Failed to fetch chat sessions:', err);
    }
  }, []);

  useEffect(() => {
    if (user) {
      fetchBookings();
      fetchChatSessions();
      
      // Fetch bot username for the QR code
      fetch(`${API_URL}/api/telegram/bot-info`)
        .then(res => res.json())
        .then(data => {
          if (data.username) setBotUsername(data.username);
        })
        .catch(err => console.error('Failed to fetch bot info:', err));
    }
  }, [user, fetchBookings, fetchChatSessions]);

  /* ── Sign out handler ───────────────────────────────────────────────────── */
  const handleLogout = async () => {
    await supabase.auth.signOut();
    navigate('/');
  };

  /* ── Start a new chat thread ────────────────────────────────────────────── */
  const handleNewChat = () => {
    setMessages([]);
    setThreadId(`${user.id}_${Date.now().toString(36)}`);
    setActiveAgent(null);
    setActiveTripId(null); // Reset trip for new conversation
  };

  /* ── Load past chat thread ──────────────────────────────────────────────── */
  const loadChatSession = async (sessionId) => {
    setIsLoading(true);
    setThreadId(sessionId);
    setActiveAgent(null);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { navigate('/auth'); return; }

      const resp = await fetch(`${API_URL}/api/chat/history/${sessionId}`, {
        headers: { Authorization: `Bearer ${session.access_token}` }
      });
      
      if (resp.ok) {
        const data = await resp.json();
        
        let loadedMessages = [...data.messages];
        
        // Append result cards if present
        if (data.results && Object.keys(data.results).length > 0) {
          for (const [type, payload] of Object.entries(data.results)) {
            loadedMessages.push({ role: 'results', resultType: type, data: payload });
          }
        }
        
        // Append itinerary if present
        if (data.itinerary) {
          loadedMessages.push({ role: 'itinerary', content: data.itinerary });
        }
        
        setMessages(loadedMessages);
      }
    } catch (err) {
      console.error('Failed to load chat session:', err);
      setMessages([{ role: 'assistant', content: '❌ Failed to load chat history.' }]);
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Open the BookingModal with the selected item's data.
   * Called by FlightCard / TrainCard / HotelCard via their onBook prop.
   *
   * @param {Object} data - { bookingType, providerName, travelDate, details }
   */
  const handleOpenBooking = (data) => {
    setBookingModal({ open: true, data });
  };

  /**
   * Send a user message and stream the SSE response from the backend.
   * Parses agent_start, agent_result, message, itinerary, and done events.
   *
   * @param {string} text - The user's message to send
   */
  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return;

    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setActiveAgent(null);

    let activeTripIdRef = activeTripId;

    // Auto-create a trip on first message if none exists
    if (!activeTripId) {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          // Generate smart trip name from the user's first message
          const words = text.trim().split(/\s+/).slice(0, 5).join(' ');
          const tripName = words.length > 3 ? words : `Trip — ${new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`;

          const tripResp = await fetch(`${API_URL}/api/trips`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${session.access_token}`,
            },
            body: JSON.stringify({ name: tripName }),
          });
          if (tripResp.ok) {
            const tripData = await tripResp.json();
            setActiveTripId(tripData.id);
            activeTripIdRef = tripData.id;
          }
        }
      } catch (err) {
        console.error('Failed to create trip:', err);
      }
    }

    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { navigate('/auth'); return; }

      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ message: text, thread_id: threadId }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      /* ── Parse SSE stream ────────────────────────────────────────────── */
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event:')) continue;
          if (!line.startsWith('data:')) continue;

          const rawData = line.replace('data:', '').trim();
          if (!rawData) continue;

          try {
            const data = JSON.parse(rawData);

            if (data.agent && !data.type && !data.content) {
              // Agent started executing
              setActiveAgent(data.agent);
            } else if (data.type && data.data) {
              // Structured results (flights / trains / hotels)
              setActiveAgent(null);
              setMessages((prev) => [...prev, {
                role: 'results',
                resultType: data.type,
                data: data.data,
              }]);
            } else if (data.content && data.agent) {
              // AI text message
              setActiveAgent(null);
              setMessages((prev) => [...prev, {
                role: 'assistant',
                content: data.content,
                agent: data.agent,
              }]);
            } else if (data.content && !data.agent) {
              // Itinerary content
              setMessages((prev) => [...prev, {
                role: 'itinerary',
                content: data.content,
              }]);
            } else if (data.thread_id !== undefined && data.destination) {
              // State snapshot
              if (activeTripIdRef || activeTripId) {
                const tId = activeTripIdRef || activeTripId;
                const dest = data.destination.charAt(0).toUpperCase() + data.destination.slice(1);
                const orig = data.origin ? data.origin.charAt(0).toUpperCase() + data.origin.slice(1) : '';
                const cleanName = orig ? `Trip: ${orig} to ${dest}` : `Trip to ${dest}`;
                
                fetch(`${API_URL}/api/trips/${tId}`, {
                  method: 'PUT',
                  headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${session.access_token}`,
                  },
                  body: JSON.stringify({ name: cleanName }),
                }).catch(() => {});
              }
            }
          } catch {
            // Skip malformed JSON chunks
          }
        }
      }
    } catch (err) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: `❌ Error: ${err.message}. Please try again.`,
      }]);
    } finally {
      setIsLoading(false);
      setActiveAgent(null);
      fetchBookings(); // Refresh bookings sidebar after chat completes
      fetchChatSessions(); // Refresh chat history sidebar
    }
  }, [isLoading, threadId, navigate, fetchBookings, fetchChatSessions]);

  /** Handle form submission for the chat input. */
  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  /* ── Don't render until auth is resolved ────────────────────────────────── */
  if (!user) return null;

  return (
    <div className="chat-layout">

      {/* ═══════════════════ SIDEBAR ═══════════════════════════════════════ */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <img src="/logo.png" alt="TripPilot" className="sidebar-logo-img" />
          <h2>TripPilot</h2>
        </div>

        <button className="btn-new-chat" onClick={handleNewChat}>
          <Plus size={18} /> New Trip
        </button>

        {/* Profile Button */}
        <div className="sidebar-section">
          <button className="sidebar-action-btn" onClick={() => setShowProfile(true)}>
            <UserCircle size={18} />
            <span>My Profile</span>
          </button>
        </div>

        {/* Bookings Accordion */}
        <div className="sidebar-section">
          <button
            className="sidebar-action-btn"
            onClick={() => { setShowBookings(!showBookings); fetchBookings(); }}
          >
            <Ticket size={18} />
            <span>My Bookings ({bookings.length})</span>
            <ChevronDown size={14} className={`chevron ${showBookings ? 'rotated' : ''}`} />
          </button>

          {showBookings && (
            <div className="bookings-list">
              {bookings.length === 0 ? (
                <p className="no-bookings">No bookings yet</p>
              ) : (
                bookings.map((b) => (
                  <div key={b.id} className={`booking-sidebar-card ${b.status === 'completed' ? 'completed' : ''}`}>
                    <strong>
                      {b.provider_name || b.booking_type}
                      {b.status === 'completed' && <span style={{fontSize: '10px', color: '#10b981', marginLeft: '5px'}}> (Completed)</span>}
                    </strong>
                    <span className="pnr">{b.pnr_or_confirmation_number}</span>
                    <span className="date">{b.travel_date}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Chat History Accordion */}
        <div className="sidebar-section">
          <button
            className="sidebar-action-btn"
            onClick={() => setShowHistory(!showHistory)}
          >
            <MessageSquare size={18} />
            <span>Chat History</span>
            <ChevronDown size={14} className={`chevron ${showHistory ? 'rotated' : ''}`} />
          </button>

          {showHistory && (
            <div className="chat-history-list">
              {chatSessions.length === 0 ? (
                <p className="no-bookings">No past trips</p>
              ) : (
                chatSessions.map((session) => (
                  <button
                    key={session.id}
                    className={`history-item ${session.thread_id === threadId ? 'active' : ''}`}
                    onClick={() => loadChatSession(session.thread_id)}
                  >
                    <span className="history-title">{session.title}</span>
                    <span className="history-date">
                      {new Date(session.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Active Agent Indicator */}
        {activeAgent && (
          <div className="sidebar-section">
            <h3>Working</h3>
            <div className="sidebar-agent active">
              <span>{AGENT_LABELS[activeAgent]?.icon}</span>
              <span>{AGENT_LABELS[activeAgent]?.label || activeAgent}</span>
              <Loader2 size={14} className="spin" />
            </div>
          </div>
        )}

        {/* Telegram QR Code */}
        {botUsername && (
          <div className="sidebar-section telegram-qr-section">
            <h3>📱 Connect on Telegram</h3>
            <div className="telegram-qr-card">
              <img 
                src={`https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=https://t.me/${botUsername}`} 
                alt="Telegram Bot QR" 
                className="qr-code-img"
              />
              <p className="qr-scan-text">Scan to start chatting with your AI assistant on the go!</p>
              <a 
                href={`https://t.me/${botUsername}`} 
                target="_blank" 
                rel="noopener noreferrer"
                className="telegram-link-btn"
              >
                @{botUsername}
              </a>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="sidebar-footer">
          <div className="user-info">
            <User size={16} />
            <span>{user.email}</span>
          </div>
          <button onClick={handleLogout} className="btn-logout">
            <LogOut size={16} /> Sign Out
          </button>
        </div>
      </aside>

      {/* ═══════════════════ CHAT AREA ═════════════════════════════════════ */}
      <main className="chat-main">
        <div className="chat-messages">

          {/* Welcome Screen (shown when no messages) */}
          {messages.length === 0 && (
            <div className="chat-welcome">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
              >
                <div className="welcome-logo">
                  <img src="/logo.png" alt="TripPilot" style={{ width: '220px', height: 'auto' }} />
                </div>
                <h2>Where would you like to go? 🌍</h2>
                <p>Describe your dream trip and I'll handle the rest — flights, trains, hotels, and a complete itinerary.</p>
                <div className="quick-prompts">
                  {QUICK_PROMPTS.map((q) => (
                    <button key={q} onClick={() => sendMessage(q)} className="quick-prompt">
                      {q}
                    </button>
                  ))}
                </div>
              </motion.div>
            </div>
          )}

          {/* Message List */}
          <AnimatePresence>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`message message-${msg.role}`}
              >
                {/* User bubble */}
                {msg.role === 'user' && (
                  <div className="message-bubble user-bubble">
                    <User size={16} />
                    <span>{msg.content}</span>
                  </div>
                )}

                {/* AI text bubble */}
                {msg.role === 'assistant' && (
                  <div className="message-bubble ai-bubble">
                    <Bot size={16} />
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* Itinerary bubble */}
                {msg.role === 'itinerary' && (
                  <div className="message-bubble ai-bubble itinerary-bubble">
                    <Map size={16} />
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* Result cards */}
                {msg.role === 'results' && (
                  <div className="results-container">
                    {msg.resultType !== 'return_transport' ? (
                      <div className="results-scroll">
                        {msg.resultType === 'flights' && msg.data.map((f, j) => (
                          <FlightCard key={j} flight={f} onBook={handleOpenBooking} />
                        ))}
                        {msg.resultType === 'trains' && msg.data.map((t, j) => (
                          <TrainCard key={j} train={t} onBook={handleOpenBooking} />
                        ))}
                        {msg.resultType === 'hotels' && msg.data.map((h, j) => (
                          <HotelCard key={j} hotel={h} onBook={handleOpenBooking} />
                        ))}
                      </div>
                    ) : (
                      <div className="return-transport-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                        {msg.data.flights && msg.data.flights.length > 0 && (
                          <div className="return-section">
                            <h4 style={{ margin: '0 0 10px 0', color: '#94a3b8', fontSize: '0.95rem' }}>✈️ Return Flights</h4>
                            <div className="results-scroll">
                              {msg.data.flights.map((f, j) => (
                                <FlightCard key={`rf-${j}`} flight={f} onBook={handleOpenBooking} />
                              ))}
                            </div>
                          </div>
                        )}
                        {msg.data.trains && msg.data.trains.length > 0 && (
                          <div className="return-section">
                            <h4 style={{ margin: '0 0 10px 0', color: '#94a3b8', fontSize: '0.95rem' }}>🚂 Return Trains</h4>
                            <div className="results-scroll">
                              {msg.data.trains.map((t, j) => (
                                <TrainCard key={`rt-${j}`} train={t} onBook={handleOpenBooking} />
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Active agent indicator */}
          {activeAgent && (
            <motion.div
              className="agent-working"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <Loader2 size={18} className="spin" />
              <span>
                {AGENT_LABELS[activeAgent]?.icon} {AGENT_LABELS[activeAgent]?.label || activeAgent}
              </span>
            </motion.div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Travel Widget + Chat Input */}
        <div className="chat-input-area">
          <TravelWidget onSubmit={sendMessage} disabled={isLoading} />
          <form className="chat-input-form" onSubmit={handleSubmit}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your travel request…"
              disabled={isLoading}
            />
            <button type="submit" disabled={isLoading || !input.trim()}>
              {isLoading ? <Loader2 size={20} className="spin" /> : <Send size={20} />}
            </button>
          </form>
        </div>
      </main>

      {/* ═══════════════════ MODALS ════════════════════════════════════════ */}
      <ProfileModal isOpen={showProfile} onClose={() => setShowProfile(false)} />
      <BookingModal
        isOpen={bookingModal.open}
        onClose={() => setBookingModal({ open: false, data: null })}
        bookingData={bookingModal.data}
        onBooked={() => fetchBookings()}
        tripId={activeTripId}
      />
    </div>
  );
}
