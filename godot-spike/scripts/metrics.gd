## Autoload. Talks to the Android host (TerrellaSpike plugin) when present; on desktop it keeps settings locally.
## Every second it pushes fps / frame time / draw calls / memory to the host, which writes the CSV row.
extends Node

signal settings_changed

var plugin: Object = null
var mode := "desktop"
var fps := 0.0
var frame_ms := 0.0
var frame_ms_max := 0.0
var draw_calls := 0.0

var _local := {}
var _acc := 0.0
var _frames := 0
var _sum_ms := 0.0
var _max_ms := 0.0
var _frame_count := 0
var _first_sent := false
var _poll := 0.0
var _last_settings := ""


func _ready() -> void:
	process_priority = 1000
	if Engine.has_singleton("TerrellaSpike"):
		plugin = Engine.get_singleton("TerrellaSpike")
		mode = plugin.getMode()
	apply_fps_cap()


func is_wallpaper() -> bool:
	return mode == "wallpaper" or mode == "preview"


func setting(key: String, def: String) -> String:
	if plugin:
		return plugin.getSetting(key, def)
	return _local.get(key, def)


func set_setting(key: String, value: String) -> void:
	if plugin:
		plugin.setSetting(key, value)
	else:
		_local[key] = value
	settings_changed.emit()


func renderer() -> String:
	return setting("renderer", "vulkan")


func fps_cap() -> int:
	return int(setting("wp_fps" if is_wallpaper() else "app_fps", "30" if is_wallpaper() else "60"))


func apply_fps_cap() -> void:
	var cap := fps_cap()
	Engine.max_fps = cap
	if plugin:
		plugin.setFpsCap(cap)


func log_event(name: String) -> void:
	if plugin:
		plugin.logEvent(name)
	else:
		print("[event] ", name)


func summary() -> String:
	if plugin:
		return plugin.getSummary()
	return "%s | %.0f fps %.1f ms (max %.1f) | %.0f draw calls | static %.0f MB" % [mode, fps, frame_ms, frame_ms_max, draw_calls, Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0]


func _process(delta: float) -> void:
	_frame_count += 1
	if not _first_sent and _frame_count >= 3:
		_first_sent = true
		if plugin:
			plugin.firstFrame()
	var ms := delta * 1000.0
	_sum_ms += ms
	_max_ms = maxf(_max_ms, ms)
	_frames += 1
	_acc += delta
	if _acc >= 1.0:
		fps = _frames / _acc
		frame_ms = _sum_ms / _frames
		frame_ms_max = _max_ms
		draw_calls = Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
		if plugin:
			plugin.reportFrame(fps, frame_ms, frame_ms_max, draw_calls,
				Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
				Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0,
				Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0)
		_acc = 0.0
		_frames = 0
		_sum_ms = 0.0
		_max_ms = 0.0
	# The wallpaper process picks up changes made in the app (separate process) by polling the settings file.
	if plugin and is_wallpaper():
		_poll += delta
		if _poll > 3.0:
			_poll = 0.0
			mode = plugin.getMode()
			var snapshot := "%s|%s|%s|%s|%s" % [setting("wp_fps", "30"), setting("hour", "live"), setting("season", "auto"), setting("weather", "clear"), setting("quality", "high")]
			if snapshot != _last_settings:
				_last_settings = snapshot
				apply_fps_cap()
				settings_changed.emit()
