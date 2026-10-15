class_name TerrellaSceneAdapter
## Minimal mapping from a scene state onto stock Godot nodes. A starting point for the real
## look (water, wet roofs, snow, foliage live in shaders that read the same fields), not the look itself.

const FOG_MAX_DENSITY := 0.03


static func apply(state: Dictionary, key_light: DirectionalLight3D, env: Environment) -> void:
	var key: Dictionary = state["light"]["key"]
	var dir := TerrellaSceneState.to_vec3(key["direction"])
	# A directional light shines along its -Z; point -Z away from the sun/moon.
	var up := Vector3.UP if absf(dir.y) < 0.999 else Vector3.FORWARD
	key_light.basis = Basis.looking_at(-dir, up)
	key_light.light_color = TerrellaSceneState.to_color(key["color"])
	key_light.light_energy = key["intensity"]
	key_light.shadow_enabled = key["shadow_strength"] > 0.05
	key_light.shadow_opacity = key["shadow_strength"]

	var amb: Dictionary = state["light"]["ambient"]
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = TerrellaSceneState.to_color(amb["color"])
	env.ambient_light_energy = amb["intensity"]

	if env.sky and env.sky.sky_material is ProceduralSkyMaterial:
		var sky: ProceduralSkyMaterial = env.sky.sky_material
		sky.sky_top_color = TerrellaSceneState.to_color(state["sky"]["zenith"])
		sky.sky_horizon_color = TerrellaSceneState.to_color(state["sky"]["horizon"])
		sky.ground_horizon_color = sky.sky_horizon_color

	var fog: float = state["weather"]["fog_density"]
	env.fog_enabled = fog > 0.02
	env.fog_density = fog * FOG_MAX_DENSITY
	env.fog_light_color = TerrellaSceneState.to_color(state["sky"]["horizon"])
