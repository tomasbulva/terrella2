// Tree canopies and hedges: wind sway, autumn tint, snow.
shader_type spatial;
render_mode cull_back;

global uniform float autumn;
global uniform float snow;

varying vec3 world_pos;
varying vec3 world_normal;

void vertex() {
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float h = max(VERTEX.y, 0.0);
	float sway = sin(TIME * 1.7 + wp.x * 0.8 + wp.z * 0.5) * 0.04 * h;
	VERTEX.x += sway;
	VERTEX.z += sway * 0.6;
	world_pos = wp;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 summer = pow(COLOR.rgb, vec3(2.2)); // vertex colours are authored in sRGB
	vec3 fall = mix(vec3(0.68, 0.15, 0.02), vec3(0.52, 0.32, 0.02), fract(sin(dot(floor(world_pos.xz * 3.0), vec2(12.9, 78.2))) * 437.5));
	vec3 col = mix(summer, fall, autumn);
	float s = smoothstep(0.35, 0.8, world_normal.y) * snow;
	col = mix(col, vec3(0.92, 0.94, 0.98), s);
	ALBEDO = col;
	ROUGHNESS = 0.9;
	// Soft fake subsurface: brighten where the canopy faces the sun-side sky.
	BACKLIGHT = col * 0.35;
}
