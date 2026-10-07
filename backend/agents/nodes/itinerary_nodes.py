"""
Itinerary agent nodes:
  - itinerary_agent — generates day-by-day JSON itinerary
  - final_agent     — produces the final trip summary with packing checklist
"""

import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.state import TravelState
from backend.agents.nodes.utils import extract_text, clean_llm_json
from backend.tools.flight_tool import format_flights_text
from backend.tools.train_tool import format_trains_text
from backend.tools.hotel_tool import format_hotels_text
from backend.tools.tavily_tool import search_attractions
from backend.tools.weather_tool import get_weather_forecast
from backend.llm_factory import get_llm

log = logging.getLogger(__name__)
llm = get_llm()


# ─────────────────────────────────────────────────────────────────────────────
# Itinerary agent
# ─────────────────────────────────────────────────────────────────────────────

def itinerary_agent(state: TravelState) -> dict:
    """Generate a day-by-day itinerary using the LLM."""
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    num_days = state.get("num_days", 0) or 3
    start_date = state.get("start_date", "")
    end_date = state.get("end_date", "")

    flights_text = format_flights_text(json.loads(state.get("flight_results", "[]") or "[]"))
    trains_text = format_trains_text(json.loads(state.get("train_results", "[]") or "[]"))
    hotels_text = format_hotels_text(json.loads(state.get("hotel_results", "[]") or "[]"))

    attractions = search_attractions(destination)
    weather_data = get_weather_forecast(destination, start_date, end_date)
    weather_text = weather_data.get("summary", "Weather data unavailable.")

    prompt = f"""You are the Expert Itinerary Planner.
You have the following confirmed details for a trip to {destination}:
- Dates: {start_date} to {end_date} ({num_days} days)
- Flights: {flights_text}
- Trains: {trains_text}
- Hotels: {hotels_text}

The user's Travel Twin Profile (learned from past behavior) is:
{json.dumps(state.get("travel_twin_profile", {}), indent=2)}

7-Day Weather Forecast for {destination}:
{weather_text}

Instructions:
1. Generate a detailed day-by-day itinerary.
2. Tailor activities to match the user's Travel Twin (e.g., if 'early_mornings' is 'low', start later).
3. If weather indicates rain on a specific day, suggest indoor activities.
4. For each place, provide a realistic description, cost estimate, and timing.
5. Provide a search query for an Unsplash image of the place.
6. Return EXACTLY this JSON structure and absolutely nothing else:
{{
  "days": [
    {{
      "day_number": 1,
      "theme": "Brief Theme (e.g., ARRIVAL & SPIRITUAL SERENITY)",
      "places": [
        {{
          "name": "Place Name",
          "address": "Brief Address or Area",
          "rating": 4.8,
          "timing": "6:00 AM - 9:00 PM",
          "cost": "Free or 500 INR",
          "description": "Short engaging description of the activity.",
          "image_search_query": "high quality search query for unsplash"
        }}
      ]
    }}
  ]
}}"""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner who creates detailed, practical itineraries and returns ONLY valid JSON."),
        HumanMessage(content=prompt),
    ])

    content = clean_llm_json(extract_text(response.content))

    return {
        "itinerary": content.strip(),
        "messages": [AIMessage(content="Your custom trip plan is ready!")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Final agent
# ─────────────────────────────────────────────────────────────────────────────

def final_agent(state: TravelState) -> dict:
    """Generate the complete final trip summary with packing checklist."""
    itinerary = state.get("itinerary", "")
    destination = state.get("destination", "")
    origin = state.get("origin", "")
    num_days = state.get("num_days", 0)
    start_date = state.get("start_date", "")
    end_date = state.get("end_date", "")

    weather_data = get_weather_forecast(destination, start_date, end_date)
    weather_text = weather_data.get("summary", "Weather data unavailable.")

    prompt = f"""Create a final, comprehensive travel plan summary for a {num_days}-day trip
from {origin} to {destination}.

Itinerary:
{itinerary}

User's Travel Twin Profile (learned from past behavior):
{json.dumps(state.get("travel_twin_profile", {}), indent=2)}

Weather Forecast:
{weather_text}

Please provide:
1. A brief trip overview
2. The complete itinerary (reformatted neatly)
3. Compact Packing Checklist — A very short, weather-appropriate packing list.
   Only include the most essential 5-10 items. DO NOT provide long detailed categories.
4. Important travel tips
5. Emergency contacts / useful info for {destination}
6. Travel Twin Personalization — Briefly explain (2-3 sentences) how this itinerary was
   tailored to the user's learned habits (e.g., budget sensitivity, walking tolerance, early mornings).

Keep it well-organized with clear headings and bullet points."""

    response = llm.invoke([
        SystemMessage(content="You are an expert travel planner creating a final trip document with weather-aware packing suggestions."),
        HumanMessage(content=prompt),
    ])

    msg_content = extract_text(response.content)
    return {
        "messages": [AIMessage(content=msg_content)],
        "phase": "complete",
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
