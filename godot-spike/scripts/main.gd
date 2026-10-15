## Terrella engine spike: one Godot project that runs both as the explorable app and as the live wallpaper.
extends Node3D

const GLB_PATH := "res://diorama/diorama.glb"

var atmos: Atmosphere
var life: Life
var rig: CameraRig
var puzzle: Puzzle
var hud: Hud
var _clock_t := 0.0
var _collected := 0
var _hour_mode := "live"
var _scene_kind := "standin"
var kit: KitDiorama


func _ready() -> void:
	var t0 := Time.get_ticks_msec()
	var street := CanalStreet.new()
	var diorama: Node3D
	_scene_kind = Metrics.setting("scene", "standin")
	if _scene_kind == "kit":
		kit = KitDiorama.new()
		diorama = kit.build()
	elif ResourceLoader.exists(GLB_PATH):
		diorama = _load_glb()
	if diorama == null:
		_scene_kind = "standin"
		kit = null
		diorama = street.build(7)
	add_child(diorama)

	life = Life.new()
	life.name = "Life"
	add_child(life)
	life.setup(11, kit != null)

	atmos = Atmosphere.new()
	atmos.name = "Atmosphere"
	add_child(atmos)
	atmos.setup((kit.anchors if kit else street.anchors).get("lamps", []), life)

	rig = CameraRig.new()
	rig.name = "CameraRig"
	rig.wallpaper = Metrics.is_wallpaper()
	add_child(rig)
	rig.tapped.connect(_on_tap)

	_collected = int(Metrics.setting("collected", "0"))
	puzzle = Puzzle.new()
	puzzle.name = "Puzzle"
	add_child(puzzle)

	if not Metrics.is_wallpaper():
		hud = Hud.new()
		add_child(hud)
		hud.setup(self)
	puzzle.progress.connect(_on_progress)
	puzzle.rewarded.connect(_on_reward)
	puzzle.setup(_puzzle_spots(street, diorama), _collected)

	_desktop_overrides()
	Metrics.settings_changed.connect(_apply_settings)
	_apply_settings()
	Metrics.log_event("scene_built_ms_%d" % (Time.get_ticks_msec() - t0))


## Tomas's Blender export drops in here; materials are matched by name to the spike shaders.
func _load_glb() -> Node3D:
	var scene: PackedScene = load(GLB_PATH)
	if scene == null:
		return null
	var node: Node3D = scene.instantiate()
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		var m: MeshInstance3D = mi
		for s in m.mesh.get_surface_count():
			var mat := m.mesh.surface_get_material(s)
			var n := (mat.resource_name if mat else "").to_lower()
			if "water" in n:
				m.set_surface_override_material(s, Mats.get_mat("water"))
			elif "window" in n or "glass" in n:
				m.set_surface_override_material(s, Mats.get_mat("window"))
			elif "leaf" in n or "foliage" in n or "ivy" in n or "tree" in n:
				m.set_surface_override_material(s, Mats.get_mat("foliage"))
	return node


func _puzzle_spots(street: CanalStreet, diorama: Node3D) -> Array:
	var spots := []
	if kit:
		for p in kit.anchors["puzzle"]:
			spots.append([diorama, p])
		return spots
	for p in street.anchors.get("trees", []):
		spots.append([diorama, p + Vector3(0.22, 0.02, 0.15 * signf(p.z))])
	if street.anchors.has("bridge"):
		spots.append([diorama, street.anchors["bridge"] + Vector3(0.35, 0, 0.5)])
	for p in street.anchors.get("lamps", []):
		spots.append([diorama, Vector3(p.x + 0.15, 0.02, p.z)])
	var boat := life.get_node_or_null("Boat")
	if boat:
		spots.append([boat, Vector3(0.45, 0.16, 0)])
	if spots.is_empty():
		for i in 6:
			spots.append([diorama, Vector3(randf_range(-5, 5), 0.1, randf_range(-3, 3))])
	return spots


func _apply_settings() -> void:
	_hour_mode = Metrics.setting("hour", "live")
	if _hour_mode == "live":
		atmos.set_from_clock(false)
	elif _hour_mode != "cycle":
		atmos.hour = float(_hour_mode)
	var season := Metrics.setting("season", "auto")
	if season == "auto":
		atmos.season = Atmosphere.season_from_clock()
	else:
		atmos.season = int(season)
	atmos.weather = Atmosphere.WEATHER_NAMES.find(Metrics.setting("weather", "clear"))
	var high := Metrics.setting("quality", "high") == "high"
	atmos.sun.shadow_enabled = high
	atmos.env.glow_enabled = high
	get_viewport().msaa_3d = Viewport.MSAA_2X if high else Viewport.MSAA_DISABLED
	get_viewport().scaling_3d_scale = 1.0 if high else 0.75
	Metrics.apply_fps_cap()
	if Metrics.setting("scene", "standin") != _scene_kind:
		# Scene switch: rebuild everything (both the app and the wallpaper pick this up).
		get_tree().call_deferred("reload_current_scene")
		return
	if Metrics.plugin:
		Metrics.plugin.setVariant("%s/%s/%dfps/%s" % [Metrics.renderer(), Metrics.setting("quality", "high"), Metrics.fps_cap(), _scene_kind])


func _on_tap(pos: Vector2) -> void:
	if puzzle.try_tap(rig.cam, pos):
		Metrics.log_event("tulip_found")


func _on_progress(found: int, total: int) -> void:
	if hud:
		hud.set_puzzle(found, total, _collected)


func _on_reward(collected: int) -> void:
	_collected = collected
	Metrics.set_setting("collected", str(collected))
	Metrics.log_event("reward")
	if hud:
		hud.show_toast("You found the Golden Windmill!")
		hud.set_puzzle(3, 3, collected)


func _process(delta: float) -> void:
	_clock_t += delta
	if _clock_t > 5.0:
		_clock_t = 0.0
		if _hour_mode == "live":
			atmos.set_from_clock(false)
	if _hour_mode == "cycle":
		atmos.hour = fmod(atmos.hour + delta * 0.1, 24.0)   # one day per 4 minutes
	atmos.update(delta)
	if rig.wallpaper and Metrics.plugin:
		rig.page_offset = Metrics.plugin.getXOffset()


## Desktop-only test hooks: `-- hour=19.6 weather=rain season=3 quality=low yaw=40 dist=8 shot=/tmp/a.png`.
var _shot_path := ""
var _shot_t := 0.0


func _desktop_overrides() -> void:
	if Metrics.plugin:
		return
	for a in OS.get_cmdline_user_args():
		var kv := a.split("=", true, 1)
		if kv.size() != 2:
			continue
		match kv[0]:
			"hour", "weather", "season", "quality", "scene":
				Metrics._local[kv[0]] = kv[1]
			"yaw":
				rig.yaw = deg_to_rad(float(kv[1]))
				rig._idle = -1e9
			"pitch":
				rig.pitch = deg_to_rad(float(kv[1]))
			"dist":
				rig.distance = float(kv[1])
			"target":
				var v := kv[1].split(",")
				rig.target = Vector3(float(v[0]), float(v[1]), float(v[2]))
			"shot":
				_shot_path = kv[1]
			"wallpaper":
				rig.wallpaper = true


func _physics_process(delta: float) -> void:
	if _shot_path == "":
		return
	_shot_t += delta
	if _shot_t > 3.0:
		get_viewport().get_texture().get_image().save_png(_shot_path)
		print("saved ", _shot_path)
		get_tree().quit()
