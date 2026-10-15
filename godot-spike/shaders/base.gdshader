// Shared opaque surface: albedo from vertex colour, cheap procedural detail, snow on up-facing faces.
shader_type spatial;
render_mode cull_back;

global uniform float snow;
global uniform float wetness;

uniform int pattern = 0; // 0 plain, 1 brick, 2 roof tiles, 3 cobbles, 4 planks
uniform float roughness_base = 0.85;
uniform float snow_cap = 1.0; // how much this surface accepts snow

varying vec3 world_pos;
varying vec3 world_normal;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 col = pow(COLOR.rgb, vec3(2.2)); // vertex colours are authored in sRGB
	float rough = roughness_base;
	float shade = 1.0;
	if (pattern == 1) {
		// Brick courses with mortar lines; works on any vertical face.
		float u = abs(world_normal.x) > 0.5 ? world_pos.z : world_pos.x;
		float row = floor(world_pos.y * 13.0);
		float bu = u * 6.5 + mod(row, 2.0) * 0.5;
		float mortar = step(fract(world_pos.y * 13.0), 0.12) + step(fract(bu), 0.06);
		float jitter = hash(vec2(floor(bu), row)) * 0.18 - 0.09;
		col *= 1.0 + jitter;
		// Fade the mortar out when bricks get smaller than a few pixels (avoids a pale shimmering wall).
		float fade = clamp(1.6 - fwidth(world_pos.y * 13.0) * 4.0, 0.0, 1.0);
		col = mix(col, vec3(0.45, 0.4, 0.34), clamp(mortar, 0.0, 1.0) * 0.45 * fade);
	} else if (pattern == 2) {
		float t = fract((world_pos.y + world_pos.x * 0.02) * 9.0);
		shade = mix(0.78, 1.0, smoothstep(0.0, 0.35, t));
		col *= shade * (0.94 + hash(floor(world_pos.xz * vec2(7.0, 9.0))) * 0.12);
	} else if (pattern == 3) {
		vec2 c = world_pos.xz * 5.0;
		c.x += mod(floor(c.y), 2.0) * 0.5;
		vec2 f = abs(fract(c) - 0.5);
		float gap = smoothstep(0.42, 0.48, max(f.x, f.y));
		col *= (0.88 + hash(floor(c)) * 0.24) * (1.0 - gap * 0.45);
	} else if (pattern == 4) {
		float line = step(fract(world_pos.z * 6.0), 0.07);
		col *= (1.0 - line * 0.35) * (0.92 + hash(vec2(floor(world_pos.z * 6.0), 1.0)) * 0.16);
	}
	// Snow settles where faces point up; slight noise so it is not a perfect cut.
	float up = clamp(world_normal.y, 0.0, 1.0);
	float n = hash(floor(world_pos.xz * 23.0)) * 0.08;
	float s = smoothstep(0.5 - n, 0.7, up) * snow * snow_cap;
	col = mix(col, vec3(0.93, 0.95, 1.0), s);
	// Wet surfaces get darker and shinier.
	float wet = wetness * (1.0 - s) * (0.4 + 0.6 * up);
	col *= 1.0 - wet * 0.35;
	ALBEDO = col;
	ROUGHNESS = mix(mix(rough, 0.25, wet), 0.9, s);
	SPECULAR = 0.4;
}
