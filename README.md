# TripPilot

TripPilot is a full-stack AI travel planner that turns a natural-language trip request into transport options, hotel suggestions, and a personalised itinerary. It combines a React chat interface with a FastAPI and LangGraph backend that coordinates specialised travel agents.

> Example: “Plan a 5-day trip from Delhi to Goa in September for two people.”

## Features

- AI trip planning from a single natural-language prompt.
- Flight search powered by AviationStack.
- Live Indian Railways schedules via RailRadar.
- Hotel recommendations from Booking.com, with Tavily fallback search.
- Personalised itineraries and AI-generated trip summaries.
- Real-time agent progress with rich flight, train, and hotel cards.
- Secure Supabase authentication and persistent chat memory.
- Direct booking links for IRCTC, MakeMyTrip, Booking.com, Goibibo, and Skyscanner.

## Architecture

```text
React + Vite frontend
        |
        | authenticated SSE chat requests
        v
FastAPI backend
        |
        v
LangGraph router
   |        |        |
Flights   Trains   Hotels
   |        |        |
Aviation  RailRadar Booking.com / Tavily
   |
   +--> Itinerary and final-response agents (Groq)
        |
        v
Conversation memory
```

### LangGraph flow

The router determines whether it needs more trip details, should run a full search, find return transport, create an itinerary, or answer directly. A full search runs the flight, train, and hotel agents in sequence, then streams structured results to the frontend.

## Tech stack

- Frontend: React 19, Vite, React Router, Supabase JS, Framer Motion
- Backend: Python, FastAPI, Uvicorn, LangGraph, LangChain
- AI: Groq (`llama-3.3-70b-versatile`)
- Data services: AviationStack, RailRadar, RapidAPI Booking.com, Tavily
- Authentication and memory: Supabase

## Project structure

```text
TripPilot/
├── backend/
│   ├── agents/
│   ├── tools/
│   ├── app.py
│   ├── auth.py
│   ├── config.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   └── lib/
│   └── package.json
└── README.md
```

## Contact

Abhishek Rastogi — [abhishekrastogi151@gmail.com](mailto:abhishekrastogi151@gmail.com)
