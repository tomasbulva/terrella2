class_name TerrellaWorldContext
extends Node
## Runtime glue (use as an autoload). Owns the world_inputs cache, applies the battery
## policy, fetches Open-Meteo, and emits a fresh scene state once a minute while active.
##
## The host tells it two things:
##   set_location(lat, lon)  - from the Android plugin (coarse, last-known fix), or a manual pick
##   set_active(bool)        - wallpaper visible / app in foreground
## Nothing runs while inactive: no timer, no network, no location.

signal scene_state_changed(state: Dictionary)

const DEFAULT_PALETTE := "res://addons/terrella_world/default_palette.json"
const CACHE_PATH := "user://world_inputs.json"
const RECOMPUTE_INTERVAL_S := 60.0
const HTTP_TIMEOUT_S := 10.0

var inputs: Dictionary = {}
var state: Dictionary = {}
var palette: Dictionary = {}
## Explore mode: shift the clock (seconds) and/or force weather, e.g. {"code": 73, "temp_c": -2}.
var time_offset_s := 0.0
var weather_override: Dictionary = {}

var _active := false
var _timer := Timer.new()
var _http := HTTPRequest.new()
var _fetching := false
var _last_attempt_at: Variant = null
var _failures := 0
var _next_check_at := 0.0


func _ready() -> void:
	palette = JSON.parse_string(FileAccess.get_file_as_string(DEFAULT_PALETTE))
	_load_cache()
	_timer.wait_time = RECOMPUTE_INTERVAL_S
	_timer.timeout.connect(_tick)
	add_child(_timer)
	_http.timeout = HTTP_TIMEOUT_S
	_http.request_completed.connect(_on_request_completed)
	add_child(_http)


## Coarse location from the device (or a manual pick). Precise fixes are snapped to the grid here.
func set_location(lat: float, lon: float, source := "device") -> void:
	var c := TerrellaPolicy.coarsen(lat, lon)
	inputs["location"] = {"lat": c[0], "lon": c[1], "source": source,
		"utc_offset_s": _device_utc_offset_s(), "updated_at": int(_now())}
	_save_cache()
	if _active:
		_tick()


func set_active(active: bool) -> void:
	if active == _active:
		return
	_active = active
	if active:
		_next_check_at = 0.0  # re-evaluate the policy on every wake
		_tick()
		_timer.start()
	else:
		_timer.stop()


## Recompute now (e.g. after changing time_offset_s or weather_override).
func refresh_state() -> void:
	var ov := {"weather": weather_override} if not weather_override.is_empty() else {}
	state = TerrellaSceneState.derive(inputs, _now() + time_offset_s, palette, ov)
	scene_state_changed.emit(state)


func _tick() -> void:
	refresh_state()
	var now := _now()
	if _fetching or now < _next_check_at:
		return
	var loc: Variant = inputs["location"]
	if loc.get("source") == "timezone":
		loc = null  # a guessed location is not worth a network call
	var d := TerrellaPolicy.decide(now, loc, inputs.get("weather"), _last_attempt_at, _failures)
	_next_check_at = d["next_check_at"]
	if d["fetch"]:
		_fetch()


func _fetch() -> void:
	var loc: Dictionary = inputs["location"]
	_fetching = true
	_last_attempt_at = _now()
	var err := _http.request(TerrellaOpenMeteo.request_url(loc["lat"], loc["lon"]),
		PackedStringArray(["User-Agent: Terrella/2 (github.com/tomasbulva/terrella2)"]))
	if err != OK:
		_fetching = false
		_failures += 1


func _on_request_completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_fetching = false
	var resp: Variant = JSON.parse_string(body.get_string_from_utf8()) if result == HTTPRequest.RESULT_SUCCESS and code == 200 else null
	if not resp is Dictionary or not resp.has("hourly"):
		_failures += 1
		_next_check_at = 0.0  # let the policy compute the backoff on the next tick
		return
	_failures = 0
	inputs["weather"] = TerrellaOpenMeteo.parse_response(resp, int(_now()))
	_save_cache()
	refresh_state()


func _now() -> float:
	return Time.get_unix_time_from_system()


func _device_utc_offset_s() -> int:
	return int(Time.get_time_zone_from_system().get("bias", 0)) * 60


func _load_cache() -> void:
	var data: Variant = null
	if FileAccess.file_exists(CACHE_PATH):
		data = JSON.parse_string(FileAccess.get_file_as_string(CACHE_PATH))
	if data is Dictionary and data.get("schema") == "terrella.world_inputs" and int(data.get("version", 0)) == 1:
		inputs = data
		inputs["location"]["utc_offset_s"] = _device_utc_offset_s()  # the user may have travelled
	else:
		# First run, no permission yet: guess longitude from the timezone so the sun is roughly right.
		var offset := _device_utc_offset_s()
		inputs = {"schema": "terrella.world_inputs", "version": 1, "weather": null,
			"location": {"lat": 45.0, "lon": clampf(offset / 240.0, -180.0, 180.0), "source": "timezone",
				"utc_offset_s": offset, "updated_at": int(_now())}}


func _save_cache() -> void:
	var f := FileAccess.open(CACHE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(inputs))
