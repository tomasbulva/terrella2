## Sun/moon, sky, fog, weather particles and the global shader values (night, snow, autumn, wetness).
class_name Atmosphere
extends Node3D

enum Weather { CLEAR, CLOUDY, RAIN, SNOW }
const WEATHER_NAMES := ["clear", "cloudy", "rain", "snow"]
const SEASON_NAMES := ["spring", "summer", "autumn", "winter"]

var hour := 12.0
var season := 1
var weather := Weather.CLEAR

var sun: DirectionalLight3D
var env: Environment
var sky_mat: ProceduralSkyMaterial
var lamp_lights: Array[OmniLight3D] = []
var rain: GPUParticles3D
var snowfall: GPUParticles3D
var leaves: GPUParticles3D
var life: Life

var _snow := 0.0
var _wet := 0.0
var _night := 0.0


func setup(lamps: Array, life_node: Life) -> void:
	life = life_node
	sky_mat = ProceduralSkyMaterial.new()
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env = Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.glow_enabled = true
	env.glow_intensity = 0.6
	env.glow_bloom = 0.0
	env.glow_hdr_threshold = 1.2
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.12
	env.adjustment_contrast = 1.06
	env.fog_enabled = true
	env.fog_density = 0.004
	env.fog_sky_affect = 0.0
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	sun.directional_shadow_max_distance = 30.0
	sun.shadow_bias = 0.03
	sun.shadow_normal_bias = 1.0
	sun.shadow_blur = 1.5
	add_child(sun)

	for p in lamps:
		var l := OmniLight3D.new()
		l.position = p
		l.omni_range = 2.4
		l.light_color = Color(1.0, 0.7, 0.4)
		l.shadow_enabled = false
		add_child(l)
		lamp_lights.append(l)

	rain = _particles(1400, 1.15, 7.2, Vector3(0, -11, 0), Vector3(0.012, 0.28, 0.012), Color(0.75, 0.8, 0.9, 0.55), 0.0)
	snowfall = _particles(1100, 7.0, 7.8, Vector3(0.15, -0.3, 0), Vector3(0.05, 0.05, 0.05), Color(1, 1, 1, 0.95), 0.4)
	leaves = _particles(70, 8.0, 6.6, Vector3(0.2, -0.2, 0), Vector3(0.07, 0.01, 0.05), Color(0.9, 0.48, 0.15), 0.6)


func _particles(amount: int, lifetime: float, start_y: float, gravity: Vector3, size: Vector3, col: Color, spread: float) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = lifetime
	p.preprocess = lifetime
	p.visibility_aabb = AABB(Vector3(-9, -2, -7), Vector3(18, 14, 14))
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(7.5, 0.2, 5.5)
	pm.gravity = gravity
	pm.direction = Vector3(0, -1, 0)
	pm.initial_velocity_min = 0.0
	pm.initial_velocity_max = 0.3
	pm.spread = 180.0 * spread
	if spread > 0.3:
		pm.angular_velocity_min = -180.0
		pm.angular_velocity_max = 180.0
		pm.angle_min = 0.0
		pm.angle_max = 360.0
	p.process_material = pm
	var mesh := BoxMesh.new()
	mesh.size = size
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED if spread < 0.5 else BaseMaterial3D.SHADING_MODE_PER_PIXEL
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = col
	mesh.material = mat
	p.draw_pass_1 = mesh
	p.position = Vector3(0, start_y, 0)
	p.emitting = false
	p.visible = false
	add_child(p)
	return p


## Called every frame; eases the global shader values toward the target state.
func update(delta: float) -> void:
	# Sun path: rises 6:30, sets 19:30 (spike: no latitude/season maths yet).
	var day_t := (hour - 6.5) / 13.0
	var elev := sin(clampf(day_t, -0.25, 1.25) * PI)
	var target_night := clampf(1.0 - smoothstep(-0.12, 0.18, elev), 0.0, 1.0)
	_night = move_toward(_night, target_night, delta * 0.5)
	var sun_az := lerpf(-70.0, 250.0, clampf(day_t, 0.0, 1.0))
	if _night > 0.5:
		# Moon: high, cool, dim.
		sun.rotation_degrees = Vector3(-55.0, 160.0, 0.0)
	else:
		sun.rotation_degrees = Vector3(-maxf(elev, 0.06) * 70.0, sun_az, 0.0)

	var overcast := 0.0
	match weather:
		Weather.CLOUDY:
			overcast = 0.55
		Weather.RAIN:
			overcast = 0.85
		Weather.SNOW:
			overcast = 0.7
	var golden := clampf(1.0 - absf(elev) * 2.5, 0.0, 1.0) * (1.0 - _night)
	var day_col := Color(1.0, 0.96, 0.88).lerp(Color(1.0, 0.62, 0.35), golden)
	var night_col := Color(0.55, 0.65, 1.0)
	sun.light_color = day_col.lerp(night_col, _night)
	sun.light_energy = lerpf(lerpf(1.6, 0.45, overcast), 0.15, _night)
	sun.shadow_opacity = lerpf(1.0, 0.35, overcast)

	var top_day := Color(0.32, 0.55, 0.86).lerp(Color(0.55, 0.6, 0.66), overcast)
	var hor_day := Color(0.72, 0.82, 0.92).lerp(Color(0.75, 0.77, 0.8), overcast).lerp(Color(1.0, 0.7, 0.5), golden * 0.7)
	sky_mat.sky_top_color = top_day.lerp(Color(0.02, 0.03, 0.08), _night)
	sky_mat.sky_horizon_color = hor_day.lerp(Color(0.08, 0.1, 0.18), _night)
	# Below the horizon: a soft studio backdrop instead of a dark "ground", so the diorama floats.
	sky_mat.ground_horizon_color = sky_mat.sky_horizon_color
	sky_mat.ground_bottom_color = sky_mat.sky_horizon_color.lerp(Color(0.85, 0.78, 0.7), 0.35 * (1.0 - _night)).darkened(0.1)
	sky_mat.ground_curve = 0.3
	sky_mat.sun_angle_max = 20.0
	env.ambient_light_energy = lerpf(lerpf(0.35, 0.7, overcast), 0.3, _night)
	env.fog_light_color = sky_mat.sky_horizon_color
	env.fog_density = lerpf(0.004, 0.02, overcast * 0.8)

	for l in lamp_lights:
		l.light_energy = 1.6 * _night
		l.visible = _night > 0.05

	var target_snow := 1.0 if (weather == Weather.SNOW or season == 3) else 0.0
	if season == 3 and weather != Weather.SNOW:
		target_snow = 0.6
	_snow = move_toward(_snow, target_snow, delta * 0.15)
	var target_wet := 1.0 if weather == Weather.RAIN else 0.0
	_wet = move_toward(_wet, target_wet, delta * 0.2)
	RenderingServer.global_shader_parameter_set("night", _night)
	RenderingServer.global_shader_parameter_set("snow", _snow)
	RenderingServer.global_shader_parameter_set("wetness", _wet)
	RenderingServer.global_shader_parameter_set("autumn", 1.0 if season == 2 else 0.0)

	_set_emit(rain, weather == Weather.RAIN)
	_set_emit(snowfall, weather == Weather.SNOW)
	_set_emit(leaves, season == 2 and weather != Weather.SNOW)
	if life:
		life.cloud_cover = [0.35, 0.85, 1.01, 1.01][weather]


func _set_emit(p: GPUParticles3D, on: bool) -> void:
	if p.emitting != on:
		p.emitting = on
		if on:
			p.visible = true
	if not on and p.visible and not p.emitting:
		# Let the last particles finish falling before hiding (saves the draw call).
		p.set_meta("off_t", p.get_meta("off_t", 0.0) + get_process_delta_time())
		if p.get_meta("off_t") > p.lifetime:
			p.visible = false
			p.set_meta("off_t", 0.0)
	elif on:
		p.set_meta("off_t", 0.0)


func set_from_clock(with_season := true) -> void:
	var t := Time.get_datetime_dict_from_system()
	hour = t.hour + t.minute / 60.0
	if with_season:
		season = season_from_clock()


static func season_from_clock() -> int:
	var m: int = Time.get_datetime_dict_from_system().month
	return [3, 3, 0, 0, 0, 1, 1, 1, 2, 2, 2, 3][m - 1]
