# TripPilot

**An omnichannel, AI-driven travel planning platform that plans, books, and manages entire trips through natural conversation — on the web and on Telegram.**

<p>
  <img src="https://img.shields.io/badge/frontend-React%20%2B%20Vite-61DAFB" alt="frontend" />
  <img src="https://img.shields.io/badge/backend-FastAPI-009688" alt="backend" />
  <img src="https://img.shields.io/badge/AI-LangGraph%20%2B%20LangChain-6E56CF" alt="ai" />
  <img src="https://img.shields.io/badge/database-Supabase-3ECF8E" alt="database" />
</p>

**[Live Demo →](https://trip-pilot-twin.vercel.app)**

---

## Overview

TripPilot is a multi-agent AI travel assistant that turns a single conversational prompt into a complete, bookable trip — flights, trains, hotels, a day-by-day itinerary, a weather-aware packing list, and live expense tracking, all coordinated by a graph of specialized AI agents.

Unlike a typical chatbot wrapper, TripPilot is built as a full product: it has persistent user profiles, a real payment flow, a Telegram companion bot for on-the-go trip management, an emergency SOS system, and a personalization engine that learns each traveler's preferences over time.

---

## Highlights

### Core Capabilities

- **Conversational trip planning.** A single natural-language prompt is decomposed by a router agent and handed off to specialized flight, train, and hotel agents, which return live, structured data that is assembled into a coherent, day-by-day itinerary rather than a generic text response.
- **Weather-aware itineraries.** Live forecasts inform both the pacing of the day-by-day plan and an automatically generated packing checklist tailored to predicted temperature and rainfall.
- **End-to-end booking flow.** A guided, three-step wizard — review, payment, confirmation — is backed by real Stripe test-mode transactions, generating a genuine PNR rather than a simulated placeholder.
- **On-trip expense companion.** An interactive itinerary checklist inside Telegram logs expenses automatically as activities are completed, culminating in a dynamically generated PDF trip report at the end of the journey.
- **Polished, app-like interface.** A glassmorphism-based dark UI with a fully responsive, drawer-style mobile experience, built to feel native rather than templated.

### What Sets TripPilot Apart

Most AI travel-planning projects stop at "prompt in, itinerary text out." TripPilot goes further:

- **Adaptive personalization.** A background Travel Twin observer learns each user's budget sensitivity, hotel preference, and travel pace from past bookings, and feeds it straight back into future recommendations — a continuous-learning loop most similar projects skip entirely.
- **True omnichannel continuity.** Web and Telegram share one account, one booking history, and one AI context, with secure multi-device linking — not a bot bolted on as an afterthought.
- **A budget optimizer that negotiates.** If a trip goes over budget, the pipeline automatically swaps transport and hotel tiers instead of simply failing.
- **Safety as a first-class feature.** A one-tap SOS system shares live location and auto-alerts an emergency contact if the traveler doesn't check in — a real-world safety net rarely found in travel-planning demos.

---

## System Architecture

![System Architecture](https://mermaid.ink/svg/JSV7aW5pdDogeyJmbG93Y2hhcnQiOiB7ImN1cnZlIjogImxpbmVhciJ9fX0lJQpmbG93Y2hhcnQgVEIKICAgIHN1YmdyYXBoIENsaWVudHNbIkNsaWVudCBMYXllciJdCiAgICAgICAgV0VCWyJXZWIgQXBwOiBSZWFjdCArIFZpdGUiXQogICAgICAgIFRHWyJUZWxlZ3JhbSBCb3QiXQogICAgZW5kCgogICAgc3ViZ3JhcGggQmFja2VuZFsiQXBwbGljYXRpb24gTGF5ZXI6IEZhc3RBUEkiXQogICAgICAgIEFQSVsiUkVTVCBBUEkiXQogICAgICAgIFNTRVsiU3RyZWFtaW5nIEVuZ2luZSJdCiAgICAgICAgQk9UWyJCb3QgU2VydmljZSJdCiAgICAgICAgU09TWyJTT1MgU2VydmljZSJdCiAgICBlbmQKCiAgICBzdWJncmFwaCBBSVsiQUkgT3JjaGVzdHJhdGlvbjogTGFuZ0dyYXBoIl0KICAgICAgICBST1VURVJbIlJvdXRlciBBZ2VudCJdIC0tPiBBR0VOVFNbIkZsaWdodCwgVHJhaW4sIEhvdGVsIEFnZW50cyJdCiAgICAgICAgQUdFTlRTIC0tPiBCVURHRVRbIkJ1ZGdldCBPcHRpbWl6ZXIiXQogICAgICAgIEJVREdFVCAtLT4gSVRJTlsiSXRpbmVyYXJ5IEFnZW50Il0KICAgICAgICBJVElOIC0tPiBGSU5BTFsiRmluYWwgU3VtbWFyeSBBZ2VudCJdCiAgICAgICAgVFdJTlsiVHJhdmVsIFR3aW4gT2JzZXJ2ZXIiXSAtLi0-IEFHRU5UUwogICAgICAgIFRXSU4gLS4tPiBJVElOCiAgICBlbmQKCiAgICBzdWJncmFwaCBEYXRhTGF5ZXJbIkRhdGEgYW5kIEludGVncmF0aW9ucyJdCiAgICAgICAgREJbIlN1cGFiYXNlIl0KICAgICAgICBFWFRbIkV4dGVybmFsIFByb3ZpZGVycyJdCiAgICAgICAgUEFZWyJTdHJpcGUiXQogICAgICAgIFNNU1siRmFzdDJTTVMiXQogICAgZW5kCgogICAgQ2xpZW50cyAtLT4gQmFja2VuZAogICAgQmFja2VuZCAtLT4gQUkKICAgIEFJIC0tPiBEYXRhTGF5ZXIKICAgIEJhY2tlbmQgLS0-IERhdGFMYXllcgo=?theme=dark&bgColor=1a1a1a)

---

## Multi-Agent Planning Pipeline

Every trip request flows through a graph of purpose-built agents rather than a single monolithic prompt:

![Multi-Agent Planning Pipeline](https://mermaid.ink/svg/JSV7aW5pdDogeyJmbG93Y2hhcnQiOiB7ImN1cnZlIjogImxpbmVhciJ9fX0lJQpmbG93Y2hhcnQgTFIKICAgIEFbIlVzZXIgUHJvbXB0Il0gLS0-IEJbIlJvdXRlciBBZ2VudCJdCiAgICBCIC0tPiBDWyJEYXRhIEFnZW50cyJdCiAgICBDIC0tPnxubyByZXN1bHRzfCBEWyJXZWIgU2VhcmNoIEZhbGxiYWNrIl0KICAgIEQgLS0-IEVbIlJldHVybiBBZ2VudCJdCiAgICBDIC0tPiBFCiAgICBFIC0tPiBGWyJCdWRnZXQgT3B0aW1pemVyIl0KICAgIEYgLS0-fG92ZXIgYnVkZ2V0fCBDCiAgICBGIC0tPiBHWyJJdGluZXJhcnkgQWdlbnQiXQogICAgRyAtLT4gSFsiRmluYWwgQWdlbnQiXQogICAgSCAtLT4gSVsiUmVzcG9uc2UgdG8gVXNlciJdCg==?theme=dark&bgColor=1a1a1a)

The pipeline is cyclic rather than linear: if a proposed trip exceeds the user's budget, the **Budget Optimizer** loops back through the data agents — swapping flights for trains, adjusting hotel tier, and recalculating — before ever presenting a plan to the user.

---

## The Travel Twin

TripPilot's standout feature is its personalization layer. Every time a user completes a booking, a background AI observer analyzes the transaction and quietly updates a persistent behavioral profile — without interrupting the user's session.

![Travel Twin Sequence](https://mermaid.ink/svg/c2VxdWVuY2VEaWFncmFtCiAgICBwYXJ0aWNpcGFudCBVIGFzIFVzZXIKICAgIHBhcnRpY2lwYW50IEFwcCBhcyBUcmlwUGlsb3QKICAgIHBhcnRpY2lwYW50IE9icyBhcyBUcmF2ZWwgVHdpbiBPYnNlcnZlcgogICAgcGFydGljaXBhbnQgREIgYXMgU3VwYWJhc2UKCiAgICBVLT4-QXBwOiBDb25maXJtcyBhIGJvb2tpbmcKICAgIEFwcC0tPj5VOiBCb29raW5nIGNvbmZpcm1lZCBpbnN0YW50bHkKICAgIEFwcC0-Pk9iczogU2VuZHMgYm9va2luZyBldmVudCAoYXN5bmMsIG5vbi1ibG9ja2luZykKICAgIE9icy0-Pk9iczogQW5hbHl6ZXMgc3BlbmRpbmcsIHRpZXIsIGFuZCBwcmVmZXJlbmNlcwogICAgT2JzLT4-REI6IFVwZGF0ZXMgVHJhdmVsIFR3aW4gcHJvZmlsZQogICAgTm90ZSBvdmVyIERCOiBCdWRnZXQgc2Vuc2l0aXZpdHksIGhvdGVsIHRpZXIsIHdhbGtpbmcgdG9sZXJhbmNlLCBhZHZlbnR1cmUgbGV2ZWwKCiAgICBVLT4-QXBwOiBQbGFucyBuZXh0IHRyaXAKICAgIEFwcC0-PkRCOiBGZXRjaGVzIFRyYXZlbCBUd2luIHByb2ZpbGUKICAgIERCLS0-PkFwcDogQmVoYXZpb3JhbCBwcmVmZXJlbmNlcwogICAgQXBwLT4-QXBwOiBQZXJzb25hbGl6ZXMgaG90ZWwgc2VsZWN0aW9uIGFuZCBpdGluZXJhcnkgcGFjaW5nCiAgICBBcHAtLT4-VTogVHJpcCBwbGFuIHRhaWxvcmVkIHRvIHBhc3QgYmVoYXZpb3IK?theme=dark&bgColor=1a1a1a)

This lets TripPilot get measurably better at predicting a user's preferences with every trip planned, rather than treating each conversation as a blank slate.

---

## Safety: Emergency SOS

A dedicated safety flow is built directly into the Telegram companion, designed for travelers in unfamiliar or remote locations:

1. The traveler taps a single SOS button.
2. TripPilot asks for a check-in within a short countdown window and offers a one-tap live location share.
3. If the check-in isn't received in time, the system automatically notifies the traveler's saved emergency contact by SMS with their live location and current trip details.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite |
| Backend | FastAPI (Python), asynchronous streaming |
| AI Orchestration | LangChain, LangGraph (multi-agent, cyclic pipeline) |
| Database & Auth | Supabase (PostgreSQL, Row-Level Security) |
| Payments | Stripe |
| Messaging | Telegram Bot API |
| Language Model | Groq-hosted Llama 3 |

---

## Setup & Installation

### Prerequisites

- Node.js 18+
- Python 3.10+
- A Supabase project (PostgreSQL + Auth)
- API keys for: Groq, AviationStack, RailRadar, Tavily, Booking.com (RapidAPI), Open-Meteo (no key needed), Telegram Bot, Fast2SMS, and Stripe (test mode)

### 1. Clone the repository

```bash
git clone https://github.com/Abhishekmnnit6022/Trip-Pilot.git
cd Trip-Pilot
```

### 2. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file inside `backend/` with your own credentials:

```
GROQ_API_KEY=your_key_here
AVIATIONSTACK_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here
RAPIDAPI=your_key_here
RAILRADAR_API_KEY=your_key_here
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_DB_URL=your_supabase_db_url
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
FAST2SMSAPIKEY=your_key_here
STRIPE_SECRET_KEY=your_stripe_test_key
```

Apply the database schema by running `supabase_migrations.sql` against your Supabase project (via the Supabase SQL editor or CLI).

Start the backend:

```bash
uvicorn app:app --reload
```

### 3. Frontend setup

```bash
cd ../frontend
npm install
```

Create a `.env` file inside `frontend/` pointing to your backend and Supabase project:

```
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

Start the frontend:

```bash
npm run dev
```

### 4. Telegram Bot (optional, for omnichannel features)

- Create a bot via [@BotFather](https://t.me/BotFather) and set `TELEGRAM_BOT_TOKEN` in the backend `.env`.
- The bot's polling loop starts automatically with the backend — no separate process required.

### Swapping in your own APIs

Every external integration is isolated inside `backend/tools/`, one file per provider (flights, trains, hotels, weather). To switch providers, replace the request logic in the relevant tool file and update the corresponding key in `.env` — the rest of the LangGraph pipeline is provider-agnostic and requires no changes.

---

## Design Philosophy

TripPilot was built with a production mindset rather than a prototype mindset:

- **Resilience over fragility** — circuit breakers and graceful fallbacks around every third-party integration mean a single failing API never breaks the user experience.
- **Asynchronous by default** — the streaming and background-task architecture was deliberately engineered to avoid blocking calls and event-loop deadlocks under concurrent load.
- **Security-conscious data access** — sensitive operations performed by the Telegram bot use tightly scoped, security-definer database functions rather than broad access, keeping Row-Level Security intact everywhere else.
- **Consistency across channels** — the web app and Telegram bot are treated as two faces of one product, sharing the same account, booking history, and AI personalization.

---

## Author

**Abhishek Rastogi**
abhishekrastogi151@gmail.com
