// Lamp glass / lit props: emissive only at night.
shader_type spatial;
render_mode cull_back;

global uniform float night;
uniform vec3 color = vec3(1.0, 0.72, 0.38);
uniform float strength = 3.0;

void fragment() {
	ALBEDO = mix(vec3(0.6, 0.58, 0.5), color * 0.3, night);
	EMISSION = color * strength * night;
	ROUGHNESS = 0.4;
}
