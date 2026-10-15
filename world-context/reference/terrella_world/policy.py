"""Battery policy: when to touch the network. Pure functions, no clock.

Rules (see README "Battery"):
- Nothing runs in the background. The client calls `decide` only when the wallpaper or
  app becomes visible, and at most every CHECK_INTERVAL_S while it stays visible.
- Location is coarse (ACCESS_COARSE_LOCATION, last-known/passive fix) and snapped to a
  ~5 km grid. That is both a privacy measure and a stable cache key.
- Weather is refetched when it is old, when the user moved, or when the cached forecast
  is running out. Failures back off exponentially.
"""
from __future__ import annotations

import math

GRID_DEG = 0.05                 # ~5.5 km north-south
CHECK_INTERVAL_S = 15 * 60      # while visible, re-evaluate at most this often
MAX_AGE_S = 60 * 60             # Open-Meteo models update hourly
MOVE_THRESHOLD_KM = 8.0         # refetch if the user moved further than this
MIN_HORIZON_S = 12 * 3600       # refetch early if the cached forecast ends sooner
BACKOFF_BASE_S = 15 * 60
BACKOFF_MAX_S = 4 * 3600


def coarsen(lat: float, lon: float, grid: float = GRID_DEG) -> tuple[float, float]:
    return round(round(lat / grid) * grid, 4), round(round(lon / grid) * grid, 4)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def decide(now: float, location: dict | None, weather: dict | None,
           last_attempt_at: float | None = None, consecutive_failures: int = 0,
           online: bool = True) -> dict:
    """Return {"fetch": bool, "reason": str, "next_check_at": unix_s}.

    location/weather are the corresponding blocks of world_inputs (or None).
    """
    def result(fetch, reason, wait=CHECK_INTERVAL_S):
        return {"fetch": fetch, "reason": reason, "next_check_at": int(now + wait)}

    if location is None:
        return result(False, "no_location")
    if not online:
        return result(False, "offline")
    if consecutive_failures > 0 and last_attempt_at is not None:
        backoff = min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** (consecutive_failures - 1))
        if now - last_attempt_at < backoff:
            return result(False, "backoff", last_attempt_at + backoff - now)
    if weather is None or not weather.get("samples"):
        return result(True, "empty")
    if distance_km(location["lat"], location["lon"], weather["lat"], weather["lon"]) > MOVE_THRESHOLD_KM:
        return result(True, "moved")
    if now - weather["fetched_at"] >= MAX_AGE_S:
        return result(True, "stale")
    if weather["samples"][-1]["t"] - now < MIN_HORIZON_S:
        return result(True, "horizon")
    return result(False, "fresh", min(CHECK_INTERVAL_S, weather["fetched_at"] + MAX_AGE_S - now))
