"""Maps tool.

Provides directions, place search, and travel-time estimates by linking out to
Google Maps (no API key needed). On desktop it opens the map in the browser;
in the web UI it returns a maps URL the front-end can render as a link or
iframe. Uses the free Nominatim geocoder so location names resolve without
credentials.
"""

from __future__ import annotations

import logging
import urllib.parse

from tools.base import ParamSpec, Risk, Tool, ToolResult

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

MAPS_BASE = "https://www.google.com/maps"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class MapsTool(Tool):
    name = "maps"
    description = (
        "Find places, get directions, or estimate travel time between two "
        "locations using Google Maps."
    )
    risk = Risk.LOW
    params = (
        ParamSpec("action", "One of: directions, search, distance"),
        ParamSpec("origin", "Starting location for directions/distance", required=False),
        ParamSpec("destination", "Ending location for directions/distance", required=False),
        ParamSpec("query", "Place search query (used by 'search')", required=False),
    )

    def run(self, action: str = "", origin: str = "", destination: str = "",
            query: str = "", **kwargs) -> ToolResult:
        action = (action or "").strip().lower()
        if action == "search":
            return self._search(query or origin or destination)
        if action == "distance":
            return self._distance(origin, destination)
        # default: directions
        return self._directions(origin, destination)

    # ------------------------------------------------------------------ #
    def _geocode(self, place: str) -> dict | None:
        place = (place or "").strip()
        if not place:
            return None
        if requests is None:
            return None
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": place, "format": "json", "limit": 1},
                timeout=6,
                headers={"User-Agent": "VARSHA/1.0"},
            )
            results = resp.json()
            if results:
                r = results[0]
                return {"lat": r.get("lat"), "lon": r.get("lon"),
                        "display": r.get("display_name", place)}
        except Exception as e:
            logger.warning("Geocode failed for %s: %s", place, e)
        return None

    def _search(self, query: str) -> ToolResult:
        query = (query or "").strip()
        if not query:
            return ToolResult.failure("Tell me what place to search for.")
        maps_url = f"{MAPS_BASE}/search/?q={urllib.parse.quote(query)}"
        data = {"url": maps_url, "query": query}
        try:
            g = self._geocode(query)
            if g and g.get("lat"):
                data["lat"] = g["lat"]
                data["lon"] = g["lon"]
                data["display"] = g["display"]
        except Exception:
            pass
        return ToolResult.success(
            f"Here's what I found for '{query}'. Opening Google Maps.",
            **data,
        )

    def _directions(self, origin: str, destination: str) -> ToolResult:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        if not origin or not destination:
            return ToolResult.failure("I need both a starting point and a destination.")
        maps_url = (
            f"{MAPS_BASE}/dir/?api=1"
            f"&origin={urllib.parse.quote(origin)}"
            f"&destination={urllib.parse.quote(destination)}"
        )
        return ToolResult.success(
            f"Directions from {origin} to {destination}. Opening Google Maps.",
            url=maps_url, origin=origin, destination=destination,
        )

    def _distance(self, origin: str, destination: str) -> ToolResult:
        origin = (origin or "").strip()
        destination = (destination or "").strip()
        if not origin or not destination:
            return ToolResult.failure("I need both points to estimate distance.")
        a = self._geocode(origin)
        b = self._geocode(destination)
        if not a or not b or not a.get("lat") or not b.get("lat"):
            # Fall back to a maps link with a note.
            maps_url = (
                f"{MAPS_BASE}/dir/?api=1"
                f"&origin={urllib.parse.quote(origin)}"
                f"&destination={urllib.parse.quote(destination)}"
            )
            return ToolResult.success(
                f"I couldn't calculate the exact distance between {origin} and {destination}, "
                f"but here's the route on Google Maps.",
                url=maps_url, origin=origin, destination=destination,
            )
        import math
        lat1, lon1 = float(a["lat"]), float(a["lon"])
        lat2, lon2 = float(b["lat"]), float(b["lon"])
        # Haversine distance in km
        r = 6371.0
        p1 = math.radians(lat1); p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
        h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        km = 2 * r * math.asin(math.sqrt(h))
        mins = max(1, int(km / 30))  # rough estimate at 30 km/h city average
        maps_url = (
            f"{MAPS_BASE}/dir/?api=1"
            f"&origin={urllib.parse.quote(origin)}"
            f"&destination={urllib.parse.quote(destination)}"
        )
        return ToolResult.success(
            f"The distance between {origin} and {destination} is about {km:.1f} km "
            f"(~{mins} minutes by road). Opening Google Maps.",
            url=maps_url, origin=origin, destination=destination,
            distance_km=round(km, 1), est_minutes=mins,
        )