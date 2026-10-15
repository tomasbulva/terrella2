## In-app overlay: live metrics line, puzzle progress and the test controls. Not created in wallpaper mode.
class_name Hud
extends CanvasLayer

var main: Node
var metrics_label: Label
var puzzle_label: Label
var panel: PanelContainer
var toast: Label
var _t := 0.0


func setup(main_node: Node) -> void:
	main = main_node
	var theme := Theme.new()
	theme.default_font_size = 22
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.theme = theme
	add_child(root)

	var top := VBoxContainer.new()
	top.set_anchors_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 16
	top.offset_right = -16
	top.offset_top = 48
	top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(top)
	metrics_label = _label(18)
	metrics_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	top.add_child(metrics_label)
	puzzle_label = _label(26)
	top.add_child(puzzle_label)

	toast = _label(30)
	toast.set_anchors_preset(Control.PRESET_CENTER)
	toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast.offset_left = -330
	toast.offset_right = 330
	toast.offset_top = -260
	toast.modulate.a = 0.0
	root.add_child(toast)

	var gear := Button.new()
	gear.text = "Controls"
	gear.custom_minimum_size = Vector2(150, 60)
	gear.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	gear.offset_left = -170
	gear.offset_top = -84
	gear.offset_right = -16
	gear.offset_bottom = -24
	root.add_child(gear)

	panel = PanelContainer.new()
	panel.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	panel.offset_left = 12
	panel.offset_right = -12
	panel.offset_bottom = -96
	panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	panel.visible = false
	root.add_child(panel)
	gear.pressed.connect(func(): panel.visible = not panel.visible)

	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)
	_row(box, "Time", "hour", [["Live", "live"], ["Cycle", "cycle"], ["7:00", "7"], ["12:00", "12"], ["19:30", "19.6"], ["23:00", "23"]], "live")
	_row(box, "Season", "season", [["Auto", "auto"], ["Spring", "0"], ["Summer", "1"], ["Autumn", "2"], ["Winter", "3"]], "auto")
	_row(box, "Weather", "weather", [["Clear", "clear"], ["Cloudy", "cloudy"], ["Rain", "rain"], ["Snow", "snow"]], "clear")
	_row(box, "Scene", "scene", [["Stand-in canal", "standin"], ["Pipeline kit", "kit"]], "standin")
	_row(box, "Quality", "quality", [["High", "high"], ["Low", "low"]], "high")
	_row(box, "App fps", "app_fps", [["30", "30"], ["60", "60"], ["120", "120"]], "60")
	_row(box, "Wallpaper fps", "wp_fps", [["1 (near static)", "1"], ["15", "15"], ["30", "30"], ["60", "60"]], "30")
	_row(box, "Renderer", "renderer", [["Vulkan (Mobile)", "vulkan"], ["GL (Compat)", "gl"]], "vulkan", true)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	box.add_child(actions)
	_action(actions, "Set wallpaper", func(): if Metrics.plugin: Metrics.plugin.setAsWallpaper())
	_action(actions, "Share CSVs", func(): if Metrics.plugin: Metrics.plugin.shareMetrics())
	_action(actions, "Clear CSVs", func():
		if Metrics.plugin:
			Metrics.plugin.clearMetrics()
		show_toast("Old metric files deleted"))


func _label(size: int) -> Label:
	var l := Label.new()
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", Color(1, 1, 1))
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	l.add_theme_constant_override("outline_size", 6)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _row(parent: Container, title: String, key: String, options: Array, def: String, restart := false) -> void:
	var l := _label(18)
	l.text = title + (" (restarts app + wallpaper)" if restart else "")
	parent.add_child(l)
	var flow := HFlowContainer.new()
	flow.add_theme_constant_override("h_separation", 8)
	flow.add_theme_constant_override("v_separation", 8)
	parent.add_child(flow)
	var group := ButtonGroup.new()
	var current := Metrics.setting(key, def)
	for o in options:
		var btn := Button.new()
		btn.text = o[0]
		btn.toggle_mode = true
		btn.button_group = group
		btn.custom_minimum_size = Vector2(0, 54)
		btn.button_pressed = (o[1] == current)
		var value: String = o[1]
		btn.pressed.connect(func():
			if Metrics.setting(key, def) == value:
				return
			Metrics.set_setting(key, value)
			Metrics.log_event("set_%s_%s" % [key, value])
			if restart and Metrics.plugin:
				Metrics.plugin.restartApp()
			elif key == "wp_fps" and Metrics.plugin:
				show_toast("Wallpaper picks this up within a few seconds")
		)
		flow.add_child(btn)


func _action(parent: Container, text: String, cb: Callable) -> void:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size = Vector2(0, 58)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.pressed.connect(cb)
	parent.add_child(b)


func show_toast(text: String) -> void:
	toast.text = text
	var tw := create_tween()
	tw.tween_property(toast, "modulate:a", 1.0, 0.25)
	tw.tween_interval(2.8)
	tw.tween_property(toast, "modulate:a", 0.0, 0.6)


func set_puzzle(found: int, total: int, collected: int) -> void:
	puzzle_label.text = "Golden tulips %d/%d    Windmills collected: %d" % [found, total, collected]


func _process(delta: float) -> void:
	_t += delta
	if _t > 1.0:
		_t = 0.0
		metrics_label.text = Metrics.summary()
