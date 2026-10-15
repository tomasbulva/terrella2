class_name TerrellaPolicy
## Battery policy: when to touch the network. Port of reference/terrella_world/policy.py.

const GRID_DEG := 0.05
const CHECK_INTERVAL_S := 15 * 60
const MAX_AGE_S := 60 * 60
const MOVE_THRESHOLD_KM := 8.0
const MIN_HORIZON_S := 12 * 3600
const BACKOFF_BASE_S := 15 * 60
const BACKOFF_MAX_S := 4 * 3600


## Snap to a ~5 km grid: privacy, and a stable cache key. Returns [lat, lon] (doubles, not Vector2/float32).
static func coarsen(lat: float, lon: float, grid: float = GRID_DEG) -> Array:
	return [snappedf(roundf(lat / grid) * grid, 0.0001), snappedf(roundf(lon / grid) * grid, 0.0001)]


static func distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	var p1 := deg_to_rad(lat1)
	var p2 := deg_to_rad(lat2)
	var dp := p2 - p1
	var dl := deg_to_rad(lon2 - lon1)
	var a := pow(sin(dp / 2.0), 2) + cos(p1) * cos(p2) * pow(sin(dl / 2.0), 2)
	return 6371.0 * 2.0 * asin(sqrt(a))


## Returns {fetch: bool, reason: String, next_check_at: int}.
static func decide(now: float, location: Variant, weather: Variant, last_attempt_at: Variant = null,
		consecutive_failures: int = 0, online: bool = true) -> Dictionary:
	var result := func(fetch: bool, reason: String, wait: float = CHECK_INTERVAL_S) -> Dictionary:
		return {"fetch": fetch, "reason": reason, "next_check_at": int(now + wait)}
	if location == null:
		return result.call(false, "no_location")
	if not online:
		return result.call(false, "offline")
	if consecutive_failures > 0 and last_attempt_at != null:
		var backoff: float = min(BACKOFF_MAX_S, BACKOFF_BASE_S * pow(2, consecutive_failures - 1))
		if now - last_attempt_at < backoff:
			return result.call(false, "backoff", last_attempt_at + backoff - now)
	if weather == null or weather.get("samples", []).is_empty():
		return result.call(true, "empty")
	if distance_km(location["lat"], location["lon"], weather["lat"], weather["lon"]) > MOVE_THRESHOLD_KM:
		return result.call(true, "moved")
	if now - weather["fetched_at"] >= MAX_AGE_S:
		return result.call(true, "stale")
	if weather["samples"][-1]["t"] - now < MIN_HORIZON_S:
		return result.call(true, "horizon")
	return result.call(false, "fresh", min(CHECK_INTERVAL_S, weather["fetched_at"] + MAX_AGE_S - now))
