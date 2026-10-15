"""Open-Meteo request building and response normalisation.

One request per refresh fetches the current conditions plus 6 past and 48 future
hours. The client keeps the whole timeline, so the scene keeps evolving (and stays
correct) for two days without another network call.
"""
from __future__ import annotations

from urllib.parse import urlencode

ENDPOINT = "https://api.open-meteo.com/v1/forecast"
PAST_HOURS = 6
FORECAST_HOURS = 48

_CURRENT = ["temperature_2m", "relative_humidity_2m", "weather_code", "cloud_cover",
            "wind_speed_10m", "wind_direction_10m", "precipitation", "snowfall", "visibility"]
_HOURLY = _CURRENT + ["snow_depth"]


def request_url(lat: float, lon: float) -> str:
    """Build the single Open-Meteo request. lat/lon should already be coarsened (see policy.coarsen)."""
    q = {
        "latitude": f"{lat:.2f}",
        "longitude": f"{lon:.2f}",
        "current": ",".join(_CURRENT),
        "hourly": ",".join(_HOURLY),
        "past_hours": PAST_HOURS,
        "forecast_hours": FORECAST_HOURS,
        "wind_speed_unit": "ms",
        "timeformat": "unixtime",
        "timezone": "auto",
    }
    return ENDPOINT + "?" + urlencode(q, safe=",")


def _f(v):
    return None if v is None else float(v)


def parse_response(resp: dict, fetched_at: int) -> dict:
    """Normalise an Open-Meteo JSON response into a world_inputs `weather` block.

    Rates: hourly precipitation/snowfall are sums over the preceding hour, current ones over
    the preceding 15 minutes; both are converted to per-hour rates here.
    """
    samples = []
    h = resp.get("hourly") or {}
    times = h.get("time") or []
    for i, t in enumerate(times):
        def col(name):
            arr = h.get(name)
            return _f(arr[i]) if arr is not None and i < len(arr) else None
        samples.append({
            "t": int(t),
            "temp_c": col("temperature_2m"),
            "rh": col("relative_humidity_2m"),
            "code": int(col("weather_code") or 0),
            "cloud": col("cloud_cover"),
            "precip_mm_h": col("precipitation"),
            "snowfall_cm_h": col("snowfall"),
            "snow_depth_m": col("snow_depth"),
            "wind_ms": col("wind_speed_10m"),
            "wind_dir_deg": col("wind_direction_10m"),
            "visibility_m": col("visibility"),
        })
    cur = resp.get("current")
    if cur and cur.get("time") is not None:
        interval_h = (cur.get("interval") or 900) / 3600.0
        ct = int(cur["time"])
        prev_depth = None
        for s in samples:
            if s["t"] <= ct:
                prev_depth = s["snow_depth_m"]
        sample = {
            "t": ct,
            "temp_c": _f(cur.get("temperature_2m")),
            "rh": _f(cur.get("relative_humidity_2m")),
            "code": int(cur.get("weather_code") or 0),
            "cloud": _f(cur.get("cloud_cover")),
            "precip_mm_h": None if cur.get("precipitation") is None else float(cur["precipitation"]) / interval_h,
            "snowfall_cm_h": None if cur.get("snowfall") is None else float(cur["snowfall"]) / interval_h,
            "snow_depth_m": prev_depth,
            "wind_ms": _f(cur.get("wind_speed_10m")),
            "wind_dir_deg": _f(cur.get("wind_direction_10m")),
            "visibility_m": _f(cur.get("visibility")),
            "current": True,
        }
        samples = [s for s in samples if s["t"] != ct] + [sample]
    samples.sort(key=lambda s: s["t"])
    return {
        "provider": "open-meteo",
        "fetched_at": int(fetched_at),
        "lat": float(resp.get("latitude", 0.0)),
        "lon": float(resp.get("longitude", 0.0)),
        "elevation_m": _f(resp.get("elevation")),
        "utc_offset_s": int(resp.get("utc_offset_seconds") or 0),
        "samples": samples,
    }


# WMO 4677 codes as used by Open-Meteo -> (condition, precip_type, code_intensity 0..1)
_WMO = {
    0: ("clear", "none", 0.0),
    1: ("clear", "none", 0.0),
    2: ("partly_cloudy", "none", 0.0),
    3: ("overcast", "none", 0.0),
    45: ("fog", "none", 0.0),
    48: ("fog", "none", 0.0),
    51: ("drizzle", "rain", 0.15), 53: ("drizzle", "rain", 0.25), 55: ("drizzle", "rain", 0.35),
    56: ("drizzle", "sleet", 0.2), 57: ("drizzle", "sleet", 0.35),
    61: ("rain", "rain", 0.3), 63: ("rain", "rain", 0.55), 65: ("rain", "rain", 0.85),
    66: ("rain", "sleet", 0.35), 67: ("rain", "sleet", 0.7),
    71: ("snow", "snow", 0.3), 73: ("snow", "snow", 0.55), 75: ("snow", "snow", 0.85), 77: ("snow", "snow", 0.2),
    80: ("rain", "rain", 0.35), 81: ("rain", "rain", 0.6), 82: ("rain", "rain", 0.95),
    85: ("snow", "snow", 0.4), 86: ("snow", "snow", 0.8),
    95: ("thunderstorm", "rain", 0.7), 96: ("thunderstorm", "rain", 0.8), 99: ("thunderstorm", "rain", 0.95),
}


def classify(code: int) -> tuple[str, str, float]:
    return _WMO.get(int(code), ("overcast", "none", 0.0))
