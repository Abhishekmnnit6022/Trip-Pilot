"""
Weather forecast tool using the free Open-Meteo API.
No API key required.

Provides weather forecasts for any destination city to enhance
itinerary generation and packing suggestions.
"""

import logging
import requests

log = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Map WMO weather codes to human-readable descriptions
WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm",
}


def _geocode(city: str) -> tuple[float, float] | None:
    """Resolve a city name to (latitude, longitude) using Open-Meteo geocoding."""
    try:
        resp = requests.get(
            GEOCODE_URL,
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["latitude"], results[0]["longitude"]
    except Exception as exc:
        log.error("Geocoding failed for %s: %s", city, exc)
    return None


def get_weather_forecast(city: str, start_date: str = "", end_date: str = "") -> dict:
    """
    Get weather forecast for a city.

    Returns a dict with:
        - city: str
        - forecast_days: list of {date, temp_max, temp_min, weather, precipitation_mm}
        - summary: str (human-readable summary)
    """
    coords = _geocode(city)
    if not coords:
        return {"city": city, "forecast_days": [], "summary": f"Weather data unavailable for {city}."}

    lat, lon = coords
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum",
        "timezone": "Asia/Kolkata",
        "forecast_days": 7,
    }
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        resp = requests.get(FORECAST_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.error("Weather API failed for %s: %s", city, exc)
        return {"city": city, "forecast_days": [], "summary": f"Weather data unavailable for {city}."}

    daily = data.get("daily", {})
    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    weather_codes = daily.get("weathercode", [])
    precipitation = daily.get("precipitation_sum", [])

    forecast_days = []
    for i in range(len(dates)):
        code = weather_codes[i] if i < len(weather_codes) else 0
        forecast_days.append({
            "date": dates[i],
            "temp_max": temp_max[i] if i < len(temp_max) else None,
            "temp_min": temp_min[i] if i < len(temp_min) else None,
            "weather": WMO_CODES.get(code, "Unknown"),
            "weather_code": code,
            "precipitation_mm": precipitation[i] if i < len(precipitation) else 0,
        })

    # Build a human-readable summary
    summary = format_weather_summary(city, forecast_days)
    return {"city": city, "forecast_days": forecast_days, "summary": summary}


def format_weather_summary(city: str, days: list[dict]) -> str:
    """Format forecast days into a readable summary for LLM context."""
    if not days:
        return f"No weather data available for {city}."

    lines = [f"🌤️ Weather Forecast for {city}:\n"]
    for day in days:
        temp_max = day.get("temp_max")
        temp_min = day.get("temp_min")
        temp_str = ""
        if temp_max is not None and temp_min is not None:
            temp_str = f" ({temp_min:.0f}°C – {temp_max:.0f}°C)"
        precip = day.get("precipitation_mm", 0)
        rain = f", Rain: {precip:.1f}mm" if precip and precip > 0 else ""
        lines.append(f"  📅 {day['date']}: {day.get('weather', '?')}{temp_str}{rain}")

    # Overall packing advice
    all_temps = [d["temp_max"] for d in days if d.get("temp_max") is not None]
    avg_temp = sum(all_temps) / len(all_temps) if all_temps else 25
    total_rain = sum(d.get("precipitation_mm", 0) for d in days)

    lines.append("")
    if avg_temp < 15:
        lines.append("🧥 Pack warm clothes — temperatures will be cool.")
    elif avg_temp < 25:
        lines.append("👕 Pack light layers — pleasant weather expected.")
    else:
        lines.append("☀️ Pack light, breathable clothes — it will be warm/hot.")

    if total_rain > 10:
        lines.append("🌧️ Rain expected — pack an umbrella and waterproof gear.")

    return "\n".join(lines)
