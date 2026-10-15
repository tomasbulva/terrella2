class_name TerrellaSceneState
## derive(inputs, now, palette) -> scene_state v1 Dictionary (same shape as the JSON schema).
## Port of reference/terrella_world/derive.py; testdata/golden/*.json keeps the two honest.
## Pure: no clock, no network, no nodes. Cheap enough to call every frame, but once a
## minute while visible is plenty (the sun moves 0.25 deg/min); tween between results.

const SCHEMA := "terrella.scene_state"
const VERSION := 1
const LIVE_MAX_AGE_S := 90 * 60
const HORIZON_GRACE_S := 3 * 3600
const WET_DECAY_S := 2.5 * 3600

const _SEASONS_NORTH := {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
	6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}
const _FLIP := {"winter": "summer", "summer": "winter", "spring": "autumn", "autumn": "spring"}


# --- helpers for renderers ---

static func to_color(rgb: Array) -> Color:
	return Color(rgb[0], rgb[1], rgb[2])


static func to_vec3(v: Array) -> Vector3:
	return Vector3(v[0], v[1], v[2])


# --- small helpers ---

static func _smoothstep(e0: float, e1: float, x: float) -> float:
	var t := clampf((x - e0) / (e1 - e0), 0.0, 1.0)
	return t * t * (3.0 - 2.0 * t)


static func _lerp3(a: Array, b: Array, t: float) -> Array:
	return [lerpf(a[0], b[0], t), lerpf(a[1], b[1], t), lerpf(a[2], b[2], t)]


static func _luma(c: Array) -> float:
	return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


static func _desaturate(c: Array, amount: float) -> Array:
	var y := _luma(c)
	return [lerpf(c[0], y, amount), lerpf(c[1], y, amount), lerpf(c[2], y, amount)]


static func _r(x: float, n: int = 4) -> float:
	return snappedf(x, pow(10.0, -n))


static func _r3(v: Variant, n: int = 4) -> Array:
	return [_r(v[0], n), _r(v[1], n), _r(v[2], n)]


static func _num(s: Dictionary, key: String, dflt: float) -> float:
	var v: Variant = s.get(key)
	return dflt if v == null else float(v)


static func _iso(unix_s: Variant, offset_s: int = 0) -> Variant:
	if unix_s == null:
		return null
	var t := int(roundf(unix_s))
	var off := absi(offset_s)
	var tz := "%s%02d:%02d" % ["-" if offset_s < 0 else "+", off / 3600, (off % 3600) / 60]
	return Time.get_datetime_string_from_unix_time(t + offset_s) + tz


static func _vec_arr(v: Vector3) -> Array:
	return [v.x, v.y, v.z]


# --- palette ---

static func _palette_at(palette: Dictionary, el: float) -> Dictionary:
	var keys: Array = palette["sun_keys"]
	var lo: Dictionary = keys[0]
	var hi: Dictionary = keys[0]
	var t := 0.0
	if el >= keys[-1]["el"]:
		lo = keys[-1]
		hi = keys[-1]
	elif el > keys[0]["el"]:
		for i in range(1, keys.size()):
			if el < keys[i]["el"]:
				lo = keys[i - 1]
				hi = keys[i]
				t = (el - lo["el"]) / (hi["el"] - lo["el"])
				break
	var out := {}
	for k in ["sun_color", "ambient_color", "sky_zenith", "sky_horizon"]:
		out[k] = _lerp3(lo[k], hi[k], t)
	for k in ["sun_intensity", "ambient_intensity"]:
		out[k] = lerpf(lo[k], hi[k], t)
	return out


# --- weather timeline ---

## Returns [sample: Dictionary, status: "ok" | "clamped" | "beyond"].
static func _sample_at(samples: Array, t: float) -> Array:
	if samples.is_empty():
		return [{}, "beyond"]
	if t <= samples[0]["t"]:
		return [samples[0].duplicate(), "clamped" if t < samples[0]["t"] else "ok"]
	var last: Dictionary = samples[-1]
	if t >= last["t"]:
		if t == last["t"]:
			return [last.duplicate(), "ok"]
		return [last.duplicate(), "clamped" if t - last["t"] <= HORIZON_GRACE_S else "beyond"]
	var i := 1
	while t >= samples[i]["t"]:
		i += 1
	var a: Dictionary = samples[i - 1]
	var b: Dictionary = samples[i]
	var f: float = (t - a["t"]) / float(b["t"] - a["t"])
	var out := {"t": t}
	var defaults := {"temp_c": 10.0, "rh": 70.0, "cloud": 30.0, "precip_mm_h": 0.0,
		"snowfall_cm_h": 0.0, "snow_depth_m": 0.0, "wind_ms": 2.0}
	for key in defaults:
		var va: Variant = a.get(key)
		var vb: Variant = b.get(key)
		if va == null and vb == null:
			out[key] = null
		else:
			out[key] = lerpf(defaults[key] if va == null else va, defaults[key] if vb == null else vb, f)
	var visa: Variant = a.get("visibility_m")
	var visb: Variant = b.get("visibility_m")
	out["visibility_m"] = null if visa == null or visb == null else lerpf(visa, visb, f)
	var da := deg_to_rad(_num(a, "wind_dir_deg", 0.0))
	var db := deg_to_rad(_num(b, "wind_dir_deg", 0.0))
	var x := lerpf(sin(da), sin(db), f)
	var y := lerpf(cos(da), cos(db), f)
	out["wind_dir_deg"] = fposmod(rad_to_deg(atan2(x, y)), 360.0)
	out["code"] = (a if f < 0.5 else b)["code"]
	return [out, "ok"]


static func _recent_rain_mm(samples: Array, t: float) -> float:
	var acc := 0.0
	for s in samples:
		if s["t"] > t or s.get("current", false):
			continue
		var rain := maxf(0.0, _num(s, "precip_mm_h", 0.0) - 10.0 * _num(s, "snowfall_cm_h", 0.0) / 7.0)
		acc += rain * exp(-(t - s["t"]) / WET_DECAY_S)
	return acc


static func _fallback_sample(t: float, lat: float, year_phase: float) -> Dictionary:
	var temperate := _smoothstep(15.0, 30.0, absf(lat))
	var summer := 0.5 - 0.5 * cos(TAU * year_phase)
	return {"t": t, "temp_c": lerpf(27.0, lerpf(1.0, 21.0, summer), temperate), "rh": 70.0, "code": 2,
		"cloud": 35.0, "precip_mm_h": 0.0, "snowfall_cm_h": 0.0, "snow_depth_m": 0.0, "wind_ms": 2.0,
		"wind_dir_deg": 240.0, "visibility_m": null}


# --- season / day phase ---

static func _season(local: Dictionary, local_unix: int, lat: float) -> Dictionary:
	var jan1 := Time.get_unix_time_from_datetime_dict({"year": local["year"], "month": 1, "day": 1, "hour": 0, "minute": 0, "second": 0})
	var doy: float = float((local_unix - jan1) / 86400 + 1) + (local["hour"] + local["minute"] / 60.0) / 24.0
	if lat < 0.0:
		doy += 182.625
	var year_phase := fposmod((doy - 355.0) / 365.25, 1.0)
	var name: String = _SEASONS_NORTH[local["month"]]
	if lat < 0.0:
		name = _FLIP[name]
	var temperate := _smoothstep(15.0, 30.0, absf(lat))
	var leaf_out := _smoothstep(0.30, 0.40, year_phase)
	var leaf_drop := 1.0 - _smoothstep(0.80, 0.88, year_phase)
	var foliage := lerpf(1.0, leaf_out * leaf_drop, temperate)
	var autumn := _smoothstep(0.70, 0.78, year_phase) * (1.0 - _smoothstep(0.84, 0.90, year_phase)) * temperate
	return {"name": name if temperate > 0.5 else "tropical", "year_phase": year_phase, "foliage": foliage, "autumn_tint": autumn}


static func _day_phase(el: float) -> String:
	if el < -18.0:
		return "night"
	if el < -12.0:
		return "astronomical_twilight"
	if el < -6.0:
		return "nautical_twilight"
	if el < TerrellaAstro.SUNRISE_ELEVATION:
		return "civil_twilight"
	if el < 6.0:
		return "golden_hour"
	return "day"


# --- main ---

## overrides: {"weather": {partial sample}} to force weather (explore mode, puzzles, debug).
static func derive(inputs: Dictionary, now: float, palette: Dictionary, overrides: Dictionary = {}) -> Dictionary:
	var loc: Dictionary = inputs["location"]
	var lat := float(loc["lat"])
	var lon := float(loc["lon"])
	var wx: Variant = inputs.get("weather")
	var offset: int
	if loc.get("utc_offset_s") != null:
		offset = int(loc["utc_offset_s"])
	elif wx != null:
		offset = int(wx["utc_offset_s"])
	else:
		offset = int(roundf(lon / 15.0)) * 3600
	var local_unix := int(floorf(now)) + offset
	var local := Time.get_datetime_dict_from_unix_time(local_unix)

	var sun := TerrellaAstro.sun_position(now, lat, lon)
	var moon := TerrellaAstro.moon_position(now, lat, lon)
	var mph := TerrellaAstro.moon_phase(now)
	var m_illum := mph.y
	var ev := TerrellaAstro.sun_events(now, lat, lon, offset)
	var season := _season(local, local_unix, lat)

	var sample: Dictionary
	var status := "beyond"
	if wx != null:
		var r := _sample_at(wx["samples"], now)
		sample = r[0]
		status = r[1]
	var source: String
	if status == "beyond":
		sample = _fallback_sample(now, lat, season["year_phase"])
		source = "fallback"
	elif now - wx["fetched_at"] <= LIVE_MAX_AGE_S:
		source = "live"
	else:
		source = "forecast"
	if not overrides.get("weather", {}).is_empty():
		sample.merge(overrides["weather"], true)
		source = "override"

	var cls := TerrellaOpenMeteo.classify(int(sample["code"]))
	var condition: String = cls[0]
	var ptype: String = cls[1]
	var code_int: float = cls[2]
	var temp := _num(sample, "temp_c", 10.0)
	var cloud := clampf(_num(sample, "cloud", 30.0) / 100.0, 0.0, 1.0)
	var rain_rate := maxf(0.0, _num(sample, "precip_mm_h", 0.0))
	var snow_rate := maxf(0.0, _num(sample, "snowfall_cm_h", 0.0))
	if ptype == "none" and (rain_rate >= 0.2 or snow_rate >= 0.1):
		ptype = "snow" if snow_rate * 7.0 >= rain_rate * 0.5 else "rain"
	if ptype == "rain" and temp <= 0.5:
		ptype = "sleet"
	if ptype == "snow" and temp >= 3.0 and snow_rate < 0.05:
		ptype = "rain"
	var p_int := 0.0
	if ptype != "none":
		var measured := sqrt(snow_rate / 3.0) if ptype == "snow" else sqrt(rain_rate / 10.0)
		p_int = clampf(maxf(code_int, measured), 0.0, 1.0)
	var thunder := condition == "thunderstorm"

	var vis: Variant = sample.get("visibility_m")
	var fog := 0.75 if condition == "fog" else 0.0
	if vis != null:
		fog = maxf(fog, clampf(1.0 - log(maxf(vis, 1.0) / 1000.0) / log(20.0), 0.0, 1.0))
	fog = clampf(maxf(fog, 0.25 * p_int), 0.0, 1.0)

	var wind_ms := maxf(0.0, _num(sample, "wind_ms", 2.0))
	var wind_from := fposmod(_num(sample, "wind_dir_deg", 0.0), 360.0)
	var to := deg_to_rad(wind_from + 180.0)

	var recent := _recent_rain_mm(wx["samples"], now) if wx != null and source != "fallback" else 0.0
	var wetness := clampf(maxf(1.0 - exp(-recent / 1.5), p_int if ptype in ["rain", "sleet"] else 0.0), 0.0, 1.0)
	var snow_cover := clampf(maxf(_num(sample, "snow_depth_m", 0.0) / 0.03, 0.4 * p_int if ptype == "snow" else 0.0), 0.0, 1.0)
	if temp > 0.0:
		wetness = maxf(wetness, 0.5 * snow_cover)

	var pal := _palette_at(palette, sun.y)
	var ov: Dictionary = palette["overcast"]
	var gloom := clampf(pow(cloud, 1.5) + palette["precipitation_darken"] * p_int + (palette["thunder_darken"] if thunder else 0.0), 0.0, 1.0)
	var sun_int: float = pal["sun_intensity"] * (1.0 - ov["sun_dim"] * gloom)
	var sun_col := _desaturate(pal["sun_color"], ov["desaturate"] * cloud)
	var amb_col := _desaturate(pal["ambient_color"], ov["desaturate"] * cloud)
	var amb_int: float = pal["ambient_intensity"] * (1.0 + ov["ambient_gain"] * cloud) * (1.0 - 0.35 * clampf(gloom - cloud, 0.0, 1.0))
	var gray: Array = ov["sky_gray"]
	var gray_l := maxf(_luma(gray), 1e-3)
	var zl := _luma(pal["sky_zenith"]) / gray_l
	var hl := _luma(pal["sky_horizon"]) / gray_l
	var zen := _lerp3(pal["sky_zenith"], [gray[0] * zl, gray[1] * zl, gray[2] * zl], cloud * 0.85)
	var hor := _lerp3(pal["sky_horizon"], [gray[0] * hl, gray[1] * hl, gray[2] * hl], cloud * 0.85)

	var moon_up := _smoothstep(-2.0, 4.0, moon.y)
	var night := 1.0 - _smoothstep(-8.0, -2.0, sun.y)
	var moon_int: float = palette["moon"]["max_intensity"] * m_illum * moon_up * night * (1.0 - 0.9 * cloud)
	amb_int += palette["moon"]["night_ambient_boost"] * m_illum * moon_up * night * (1.0 - cloud)

	var sun_dir := TerrellaAstro.direction(sun.x, sun.y)
	var moon_dir := TerrellaAstro.direction(moon.x, moon.y)
	var key: Dictionary
	if sun_int >= moon_int:
		key = {"source": "sun", "direction": sun_dir, "color": sun_col, "intensity": sun_int}
	else:
		key = {"source": "moon", "direction": moon_dir, "color": palette["moon"]["color"], "intensity": moon_int}
	var shadow := clampf(1.0 - cloud * 0.9, 0.0, 1.0) * _smoothstep(0.0, 0.05, key["intensity"])
	var stars := clampf((1.0 - _smoothstep(-15.0, -6.0, sun.y)) * (1.0 - cloud) * (1.0 - 0.6 * m_illum * moon_up), 0.0, 1.0)

	var samples: Array = wx["samples"] if wx != null else []
	return {
		"schema": SCHEMA,
		"version": VERSION,
		"time": {
			"utc": _iso(now),
			"local": _iso(now, offset),
			"utc_offset_s": offset,
			"local_hours": _r(local["hour"] + local["minute"] / 60.0 + local["second"] / 3600.0),
			"day_phase": _day_phase(sun.y),
			"sunrise": _iso(ev["sunrise"], offset),
			"solar_noon": _iso(ev["solar_noon"], offset),
			"sunset": _iso(ev["sunset"], offset),
			"polar": ev["polar"],
		},
		"location": {"lat": _r(lat, 2), "lon": _r(lon, 2), "source": loc.get("source", "device")},
		"sun": {"azimuth_deg": _r(sun.x, 2), "elevation_deg": _r(sun.y, 2), "direction": _r3(_vec_arr(sun_dir))},
		"moon": {"azimuth_deg": _r(moon.x, 2), "elevation_deg": _r(moon.y, 2), "direction": _r3(_vec_arr(moon_dir)),
			"phase": _r(mph.x), "illumination": _r(m_illum)},
		"light": {
			"key": {"source": key["source"], "direction": _r3(_vec_arr(key["direction"])), "color": _r3(key["color"]),
				"intensity": _r(key["intensity"]), "shadow_strength": _r(shadow)},
			"ambient": {"color": _r3(amb_col), "intensity": _r(amb_int)},
		},
		"sky": {"zenith": _r3(zen), "horizon": _r3(hor), "star_visibility": _r(stars)},
		"weather": {
			"condition": condition,
			"wmo_code": int(sample["code"]),
			"cloud_cover": _r(cloud),
			"precipitation": {"type": ptype, "intensity": _r(p_int), "rate_mm_h": _r(rain_rate, 2)},
			"thunder": thunder,
			"fog_density": _r(fog),
			"visibility_m": null if vis == null else int(roundf(vis)),
			"wind": {"speed_ms": _r(wind_ms, 2), "from_deg": _r(wind_from, 1),
				"vector_xz": [_r(sin(to) * wind_ms, 3), _r(-cos(to) * wind_ms, 3)],
				"strength": _r(clampf(wind_ms / 15.0, 0.0, 1.0))},
			"temperature_c": _r(temp, 1),
			"humidity": null if sample.get("rh") == null else _r(sample["rh"] / 100.0, 3),
		},
		"surface": {"wetness": _r(wetness), "snow_cover": _r(snow_cover)},
		"season": {"name": season["name"], "year_phase": _r(season["year_phase"]),
			"foliage": _r(season["foliage"]), "autumn_tint": _r(season["autumn_tint"])},
		"meta": {
			"source": source,
			"weather_age_min": null if wx == null else maxi(0, int(now - wx["fetched_at"]) / 60),
			"weather_valid_until": _iso(samples[-1]["t"] + HORIZON_GRACE_S) if not samples.is_empty() else null,
		},
	}
