## Shared materials, one instance per key so merged meshes and props batch together.
class_name Mats
extends RefCounted

static var _cache := {}


static func get_mat(key: String) -> Material:
	if _cache.has(key):
		return _cache[key]
	var m: Material
	match key:
		"brick":
			m = _base(1, 0.85, 1.0)
		"plaster":
			m = _base(0, 0.9, 1.0)
		"trim":
			m = _base(0, 0.6, 1.0)
		"roof":
			m = _base(2, 0.75, 1.0)
		"cobble":
			m = _base(3, 0.9, 1.0)
		"quay":
			m = _base(1, 0.9, 0.6)
		"wood":
			m = _base(4, 0.8, 1.0)
		"props":
			m = _base(0, 0.5, 0.5)
		"plinth":
			m = _base(4, 0.6, 0.0)
		"window":
			m = _shader("res://shaders/window.gdshader")
		"foliage":
			m = _shader("res://shaders/foliage.gdshader")
		"water":
			m = _shader("res://shaders/water.gdshader")
		"glow":
			m = _shader("res://shaders/glow.gdshader")
		"resin":
			var s := StandardMaterial3D.new()
			s.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			s.albedo_color = Color(0.1, 0.32, 0.33, 0.55)
			s.roughness = 0.1
			m = s
		"gold":
			var g := StandardMaterial3D.new()
			g.albedo_color = Color(1.0, 0.78, 0.25)
			g.metallic = 1.0
			g.roughness = 0.25
			g.emission_enabled = true
			g.emission = Color(1.0, 0.7, 0.2)
			g.emission_energy_multiplier = 0.6
			m = g
		_:
			m = _base(0, 0.8, 1.0)
	_cache[key] = m
	return m


static func _shader(path: String) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.shader = load(path)
	return sm


static func _base(pattern: int, rough: float, snow_cap: float) -> ShaderMaterial:
	var sm := _shader("res://shaders/base.gdshader")
	sm.set_shader_parameter("pattern", pattern)
	sm.set_shader_parameter("roughness_base", rough)
	sm.set_shader_parameter("snow_cap", snow_cap)
	return sm


static func builder() -> MeshBuilder:
	var b := MeshBuilder.new()
	for k in ["brick", "plaster", "trim", "roof", "cobble", "quay", "wood", "props", "plinth", "window", "foliage", "water", "glow", "resin", "gold"]:
		b.set_material(k, get_mat(k))
	return b
