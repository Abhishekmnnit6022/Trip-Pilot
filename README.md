# TripPilot 🌍✈️

TripPilot is a state-of-the-art, enterprise-grade AI travel platform. Built on LangGraph, FastAPI, and React, it transforms natural-language requests into fully orchestrated trips. It doesn't just give you a list of places to visit—it operates autonomous AI agents to search live global flights, Indian train schedules, and hotel prices. It then optimizes your trip to fit your budget, generates a cohesive itinerary, processes your payment via Stripe, and syncs everything instantly to a Telegram bot.

> **Example Query:** “Plan a 5-day luxury trip from Delhi to Goa in September, but my strict budget is ₹20,000.” (Watch the AI Budget Optimizer kick in to save the day!)

---

## 🌟 Key Features

### 🧠 Agentic AI Architecture (LangGraph)
- **Multi-Agent System:** Dedicated specialized agents for routing, flights, trains, hotels, and itinerary generation (powered by `Llama-3.3-70b-versatile` via Groq).
- **Travel Twin (Continuous Learning):** A background AI observer constantly monitors user booking behavior (e.g. tracking budget limits and star-rating preferences). It dynamically constructs a "Travel Twin" profile and injects this persistent context into all future LangGraph sessions for hyper-personalized itineraries.
- **Autonomous Budget Optimization (Cyclic Graph):** If your requested trip exceeds your budget, the AI intercepts the flow, iteratively drops luxury hotels for budget ones, swaps flights for trains, and automatically recalculates until the budget is met.
- **Fallback Intelligence:** If a third-party API is down, a custom Thread-Safe Circuit Breaker kicks in, allowing the AI to seamlessly fallback to real-time Web Search (Tavily) without crashing.

### 💳 Interactive FinTech Booking
- **Stripe Integration:** An immersive booking wizard that generates realistic test payments via Stripe Virtual Cards.
- **Smart Result Cards:** Real-time fetched transport and hotel results are rendered as premium, interactive glassmorphic UI cards. Hotels are auto-sorted to give you the cheapest, highest-rated options first.
- **Dynamic Date Selection:** Users can override and explicitly lock in travel dates during checkout.

### 📱 Omnichannel & Mobile-First UX
- **Seamless Mobile Responsiveness:** The entire web dashboard is optimized for smartphones with an app-like hidden drawer sidebar, fluid glassmorphism grids, and adaptive chat layouts, allowing for flawless travel planning on the go.
- **Deep-Linked Telegram Onboarding:** Mobile users can instantly pair their Telegram accounts using the "Tap to Connect" button, which deep-links directly into the bot with their unique auth token (bypassing the need to scan QR codes on mobile).
- **Multi-Device Sync:** Once linked, any bookings made on the web app instantly push rich-text notifications to their Telegram app. The bot also provides direct links back to the deployed production app for cross-platform continuity.
- **Interactive Chat Menus:** Users can pull up their active Flight, Train, and Hotel PNRs/Booking IDs directly from Telegram via inline keyboard menus.
- **Advanced SOS Emergency System:** If a user triggers the "🚨 SOS Emergency" button on Telegram during a trip:
  - The bot instantly generates a dynamic **Google Maps Live Location** link.
  - The backend bypasses database row-level security to extract the user's emergency contact.
  - A real-time **Emergency SMS** is fired to their loved ones via the **Fast2SMS API** containing their live location, ensuring safety even in low-bandwidth travel areas.
- **On-Trip Expense & Itinerary Tracking:** The bot serves as an active companion during your trip. It turns your AI-generated itinerary into an interactive checklist containing both paid and free local activities. 
- **Smart Expense Routing:** As you tap to check off completed activities on Telegram, the bot analyzes the activity type. If it's a paid activity, it securely logs your real-world expenses on the go. If it's a free activity, it checks it off without inflating your expense report!
- **Dynamic PDF Reporting:** Clicking "End Trip" triggers a background process that compiles all your pre-trip bookings and on-trip custom expenses into a beautifully styled, final PDF Expense Report. This invoice is instantly delivered to your Telegram chat.

### 💾 Persistent Memory & Cloud Sync
- **My Travel Twin Dashboard:** A premium, glassmorphism visualizer in the frontend that dynamically renders your AI-learned habits (budget sensitivity bars, hotel star trackers, walking/adventure tolerance grids) and a live feed of AI Insights.
- **Chat History Sidebar:** Just like ChatGPT, all previous AI travel sessions are saved to Supabase and can be clicked to resume your context instantly.
- **Profile Management:** Secure user profiles managed via Supabase JWT Authentication.

---

## 🏗️ Architecture

```text
React + Vite (Frontend)
   |-- (SSE Chat Streams, Auth, Stripe Elements)
   v
FastAPI (Backend)
   |-- (Thread-Safe Circuit Breakers, Supabase RPCs, Telegram Webhooks)
   v
LangGraph (Agentic Orchestrator)
   |-- Router Agent
   |-- Flight Agent (AviationStack)
   |-- Train Agent (RailRadar)
   |-- Hotel Agent (Booking.com)
   |-- Budget Optimizer (Cyclic Feedback Loop)
   |-- Itinerary Agent
```

---

## 🚀 How to Use It

### 1. Prerequisites
- **Python 3.10+** (Backend)
- **Node.js 18+** (Frontend)
- PostgreSQL Database (via Supabase)

### 2. Environment Variables
Create `.env` files in both the root and `/frontend` directories. You will need API keys for:
`Groq` (LLM), `Supabase` (Database/Auth), `AviationStack` (Flights), `RailRadar` (Trains), `RapidAPI` (Hotels), `Tavily` (Web Search Fallback), `Stripe` (Payments), `Fast2SMS` (SOS Alerts), and a `Telegram Bot Token`.

### 3. Start the Backend
```bash
cd backend
python -m venv env
source env/bin/activate  # On Windows: .\env\Scripts\activate
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn app:app --reload
```

### 4. Start the Frontend
```bash
cd frontend
npm install

# Run the Vite Dev Server
npm run dev
```

### 5. Start Planning!
1. Open the Web App on `localhost:5173`.
2. Sign Up / Log In.
3. Chat with TripPilot to plan a trip. Try throwing impossible budgets at it to watch the autonomous optimization loop in action!
4. Click **Book Now** on any result to launch the Stripe payment wizard.
5. Link your Telegram account in the Profile tab to view your bookings and test the SOS feature on the go.

---

**Built by:** Abhishek Rastogi — [abhishekrastogi151@gmail.com](mailto:abhishekrastogi151@gmail.com)
