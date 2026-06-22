import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase, API_URL } from '../lib/supabase';
import { FlightCard, TrainCard, HotelCard } from '../components/ResultCards';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Send, LogOut, Plus, Plane, Train, Hotel, Map, Bot, User,
  Loader2
} from 'lucide-react';

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

const QUICK_PROMPTS = [
  'Plan a trip to Rishikesh for 4 days',
  '7-day Goa trip under ₹30k',
  'Weekend trip to Manali from Delhi',
  'Kerala backwaters 5-day plan',
];

export default function ChatPage() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [threadId, setThreadId] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeAgent, setActiveAgent] = useState(null);
  const messagesEndRef = useRef(null);

  // Auth check
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        navigate('/auth');
      } else {
        setUser(session.user);
        setThreadId(`${session.user.id}_${Date.now().toString(36)}`);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) navigate('/auth');
      else setUser(session.user);
    });

    return () => subscription.unsubscribe();
  }, [navigate]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeAgent]);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    navigate('/');
  };

  const handleNewChat = () => {
    setMessages([]);
    setThreadId(`${user.id}_${Date.now().toString(36)}`);
    setActiveAgent(null);
  };

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return;

    const userMsg = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setActiveAgent(null);

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
          if (line.startsWith('event:')) {
            const eventType = line.replace('event:', '').trim();
            continue;
          }
          if (!line.startsWith('data:')) continue;

          const rawData = line.replace('data:', '').trim();
          if (!rawData) continue;

          try {
            const data = JSON.parse(rawData);

            // Check what type of SSE event this is based on the data shape
            if (data.agent && !data.type && !data.content) {
              // agent_start event
              setActiveAgent(data.agent);
            } else if (data.type && data.data) {
              // agent_result event — render cards
              setActiveAgent(null);
              setMessages((prev) => [...prev, {
                role: 'results',
                resultType: data.type,
                data: data.data,
              }]);
            } else if (data.content && data.agent) {
              // message event
              setActiveAgent(null);
              setMessages((prev) => [...prev, {
                role: 'assistant',
                content: data.content,
                agent: data.agent,
              }]);
            } else if (data.content && !data.agent) {
              // itinerary event
              setMessages((prev) => [...prev, {
                role: 'itinerary',
                content: data.content,
              }]);
            }
          } catch {
            // Skip malformed JSON
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
    }
  }, [isLoading, threadId, navigate]);

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  if (!user) return null;

  return (
    <div className="chat-layout">
      {/* Sidebar */}
      <aside className="chat-sidebar">
        <div className="sidebar-header">
          <span className="sidebar-logo">✈️</span>
          <h2>AI Travel Planner</h2>
        </div>

        <button className="btn-new-chat" onClick={handleNewChat}>
          <Plus size={18} /> New Trip
        </button>

        <div className="sidebar-section">
          <h3>Agent Pipeline</h3>
          <div className="sidebar-agents">
            {Object.entries(AGENT_LABELS).map(([key, val]) => (
              <div key={key} className={`sidebar-agent ${activeAgent === key ? 'active' : ''}`}>
                <span>{val.icon}</span>
                <span>{val.label}</span>
                {activeAgent === key && <Loader2 size={14} className="spin" />}
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Tech Stack</h3>
          <div className="sidebar-chips">
            {['LangGraph', 'Groq LLaMA', 'Supabase', 'Tavily', 'AviationStack'].map((t) => (
              <span key={t} className="sidebar-chip">{t}</span>
            ))}
          </div>
        </div>

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

      {/* Chat Area */}
      <main className="chat-main">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-welcome">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
              >
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

          <AnimatePresence>
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`message message-${msg.role}`}
              >
                {msg.role === 'user' && (
                  <div className="message-bubble user-bubble">
                    <User size={16} />
                    <span>{msg.content}</span>
                  </div>
                )}

                {msg.role === 'assistant' && (
                  <div className="message-bubble ai-bubble">
                    <Bot size={16} />
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {msg.role === 'itinerary' && (
                  <div className="message-bubble ai-bubble itinerary-bubble">
                    <Map size={16} />
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {msg.role === 'results' && (
                  <div className="results-container">
                    <div className="results-scroll">
                      {msg.resultType === 'flights' && msg.data.map((f, j) => (
                        <FlightCard key={j} flight={f} />
                      ))}
                      {msg.resultType === 'trains' && msg.data.map((t, j) => (
                        <TrainCard key={j} train={t} />
                      ))}
                      {msg.resultType === 'hotels' && msg.data.map((h, j) => (
                        <HotelCard key={j} hotel={h} />
                      ))}
                      {msg.resultType === 'return_transport' && (
                        <>
                          {(msg.data.flights || []).map((f, j) => (
                            <FlightCard key={`rf-${j}`} flight={f} />
                          ))}
                          {(msg.data.trains || []).map((t, j) => (
                            <TrainCard key={`rt-${j}`} train={t} />
                          ))}
                        </>
                      )}
                    </div>
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

        {/* Input */}
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
      </main>
    </div>
  );
}
