class_name TerrellaOpenMeteo
## Open-Meteo request + normalisation. Port of reference/terrella_world/weather.py.

const ENDPOINT := "https://api.open-meteo.com/v1/forecast"
const PAST_HOURS := 6
const FORECAST_HOURS := 48
const _CURRENT := ["temperature_2m", "relative_humidity_2m", "weather_code", "cloud_cover",
	"wind_speed_10m", "wind_direction_10m", "precipitation", "snowfall", "visibility"]

# hourly column -> sample key
const _COLUMNS := {
	"temperature_2m": "temp_c", "relative_humidity_2m": "rh", "cloud_cover": "cloud",
	"precipitation": "precip_mm_h", "snowfall": "snowfall_cm_h", "snow_depth": "snow_depth_m",
	"wind_speed_10m": "wind_ms", "wind_direction_10m": "wind_dir_deg", "visibility": "visibility_m",
}

# WMO 4677 -> [condition, precip_type, code_intensity]
const _WMO := {
	0: ["clear", "none", 0.0], 1: ["clear", "none", 0.0], 2: ["partly_cloudy", "none", 0.0], 3: ["overcast", "none", 0.0],
	45: ["fog", "none", 0.0], 48: ["fog", "none", 0.0],
	51: ["drizzle", "rain", 0.15], 53: ["drizzle", "rain", 0.25], 55: ["drizzle", "rain", 0.35],
	56: ["drizzle", "sleet", 0.2], 57: ["drizzle", "sleet", 0.35],
	61: ["rain", "rain", 0.3], 63: ["rain", "rain", 0.55], 65: ["rain", "rain", 0.85],
	66: ["rain", "sleet", 0.35], 67: ["rain", "sleet", 0.7],
	71: ["snow", "snow", 0.3], 73: ["snow", "snow", 0.55], 75: ["snow", "snow", 0.85], 77: ["snow", "snow", 0.2],
	80: ["rain", "rain", 0.35], 81: ["rain", "rain", 0.6], 82: ["rain", "rain", 0.95],
	85: ["snow", "snow", 0.4], 86: ["snow", "snow", 0.8],
	95: ["thunderstorm", "rain", 0.7], 96: ["thunderstorm", "rain", 0.8], 99: ["thunderstorm", "rain", 0.95],
}


static func classify(code: int) -> Array:
	return _WMO.get(code, ["overcast", "none", 0.0])


## lat/lon should already be coarsened (TerrellaPolicy.coarsen).
static func request_url(lat: float, lon: float) -> String:
	var hourly: Array = _CURRENT.duplicate()
	hourly.append("snow_depth")
	return ENDPOINT + "?latitude=%.2f&longitude=%.2f&current=%s&hourly=%s&past_hours=%d&forecast_hours=%d&wind_speed_unit=ms&timeformat=unixtime&timezone=auto" % [
		lat, lon, ",".join(_CURRENT), ",".join(hourly), PAST_HOURS, FORECAST_HOURS]


static func _f(v: Variant) -> Variant:
	return null if v == null else float(v)


## Normalise a parsed Open-Meteo JSON response into a world_inputs `weather` block.
static func parse_response(resp: Dictionary, fetched_at: int) -> Dictionary:
	var samples: Array = []
	var h: Dictionary = resp.get("hourly", {})
	var times: Array = h.get("time", [])
	for i in times.size():
		var s := {"t": int(times[i]), "code": 0}
		var code_col: Array = h.get("weather_code", [])
		if i < code_col.size() and code_col[i] != null:
			s["code"] = int(code_col[i])
		for col in _COLUMNS:
			var arr: Array = h.get(col, [])
			s[_COLUMNS[col]] = _f(arr[i]) if i < arr.size() else null
		samples.append(s)
	var cur: Dictionary = resp.get("current", {})
	if cur.get("time") != null:
		var interval_h := float(cur.get("interval", 900)) / 3600.0
		var ct := int(cur["time"])
		var prev_depth: Variant = null
		for s in samples:
			if s["t"] <= ct:
				prev_depth = s["snow_depth_m"]
		var sample := {
			"t": ct,
			"temp_c": _f(cur.get("temperature_2m")),
			"rh": _f(cur.get("relative_humidity_2m")),
			"code": int(cur.get("weather_code", 0)),
			"cloud": _f(cur.get("cloud_cover")),
			"precip_mm_h": null if cur.get("precipitation") == null else float(cur["precipitation"]) / interval_h,
			"snowfall_cm_h": null if cur.get("snowfall") == null else float(cur["snowfall"]) / interval_h,
			"snow_depth_m": prev_depth,
			"wind_ms": _f(cur.get("wind_speed_10m")),
			"wind_dir_deg": _f(cur.get("wind_direction_10m")),
			"visibility_m": _f(cur.get("visibility")),
			"current": true,
		}
		samples = samples.filter(func(x): return x["t"] != ct)
		samples.append(sample)
	samples.sort_custom(func(a, b): return a["t"] < b["t"])
	return {
		"provider": "open-meteo",
		"fetched_at": fetched_at,
		"lat": float(resp.get("latitude", 0.0)),
		"lon": float(resp.get("longitude", 0.0)),
		"elevation_m": _f(resp.get("elevation")),
		"utc_offset_s": int(resp.get("utc_offset_seconds", 0)),
		"samples": samples,
	}
