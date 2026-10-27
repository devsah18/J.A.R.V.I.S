"""Weather tool.

Queries the free Open-Meteo API (no API key required) to provide live weather
conditions, temperature, humidity, wind speed, and forecasts for any location.
"""

from __future__ import annotations

import logging
from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# WMO Weather interpretation codes (WW)
_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherTool(Tool):
    name = "weather"
    description = "Get current weather conditions or forecast for any city or location worldwide."
    risk = Risk.LOW
    params = (
        ParamSpec("location", "City or location name (e.g. 'London', 'New York', 'Mumbai')"),
        ParamSpec("forecast", "Whether to return daily forecast (True/False)", required=False),
    )

    def run(self, location: str = "", forecast: bool = False, **kwargs) -> ToolResult:
        location = (location or "").strip()
        if not location:
            return ToolResult.failure("Please specify a location to get the weather for.")

        if requests is None:
            return ToolResult.failure("The requests library is required for weather lookup.")

        try:
            # 1. Geocode location name into latitude/longitude
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1&language=en&format=json"
            geo_resp = requests.get(geo_url, timeout=6, headers={"User-Agent": "VARSHA/1.0"})
            geo_data = geo_resp.json()

            results = geo_data.get("results")
            if not results:
                return ToolResult.failure(f"I couldn't find coordinates for '{location}'. Please check the city name.")

            place = results[0]
            lat = place["latitude"]
            lon = place["longitude"]
            city_name = place.get("name", location)
            country = place.get("country", "")
            location_label = f"{city_name}, {country}" if country else city_name

            # 2. Query Open-Meteo for current weather and forecast
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                f"&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
            )
            w_resp = requests.get(weather_url, timeout=6, headers={"User-Agent": "VARSHA/1.0"})
            w_data = w_resp.json()

            current = w_data.get("current_weather", {})
            temp = current.get("temperature")
            wind = current.get("windspeed")
            wcode = current.get("weathercode", 0)
            condition = _WEATHER_CODES.get(wcode, "Clear")

            if forecast and "daily" in w_data:
                daily = w_data["daily"]
                max_temp = daily.get("temperature_2m_max", [temp])[0]
                min_temp = daily.get("temperature_2m_min", [temp])[0]
                msg = (
                    f"In {location_label}, it's currently {temp} degrees Celsius and {condition}. "
                    f"Today's forecast is a high of {max_temp} degrees and a low of {min_temp} degrees with wind at {wind} km/h."
                )
            else:
                msg = f"In {location_label}, it is currently {temp} degrees Celsius and {condition}, with wind at {wind} km/h."

            return ToolResult.success(
                msg,
                location=location_label,
                temperature=temp,
                condition=condition,
                windspeed=wind,
            )

        except Exception as e:
            logger.warning("Weather error: %s", e)
            return ToolResult.failure(f"Could not retrieve weather for {location}: {e}")
