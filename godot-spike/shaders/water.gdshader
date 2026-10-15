// Canal water: depth-tinted colour, two scrolling procedural ripple normals, fresnel sky, rain rings.
shader_type spatial;
render_mode cull_back, blend_mix, depth_draw_opaque;

global uniform float night;
global uniform float wetness;
global uniform float snow;

uniform vec3 shallow = vec3(0.16, 0.36, 0.36);
uniform vec3 deep = vec3(0.03, 0.12, 0.14);
uniform float edge_half_width = 2.1;

varying vec3 world_pos;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX.y += sin(TIME * 0.9 + world_pos.x * 1.3) * 0.012;
}

void fragment() {
	vec2 uv = world_pos.xz;
	float t = TIME;
	float n1 = noise(uv * 2.2 + vec2(t * 0.12, t * 0.05));
	float n2 = noise(uv * 4.7 - vec2(t * 0.07, -t * 0.11));
	vec2 grad = vec2(n1 - noise(uv * 2.2 + vec2(t * 0.12 + 0.05, t * 0.05)), n2 - noise(uv * 4.7 - vec2(t * 0.07, -t * 0.11 - 0.05)));
	// Rain rings.
	float rings = 0.0;
	if (wetness > 0.05) {
		vec2 cell = floor(uv * 3.0);
		vec2 c = (cell + vec2(hash(cell), hash(cell + 7.0))) / 3.0;
		float ph = fract(t * 0.9 + hash(cell + 3.0));
		float d = length(uv - c);
		rings = smoothstep(0.03, 0.0, abs(d - ph * 0.3)) * (1.0 - ph) * wetness;
	}
	NORMAL_MAP = normalize(vec3(grad * 6.0 + rings * 0.8, 1.0)) * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.0;
	// Deeper towards the canal centre; shallower near the quay walls.
	float edge = clamp(abs(world_pos.z) / edge_half_width, 0.0, 1.0);
	vec3 col = mix(deep, shallow, edge * edge);
	col = mix(col, col * vec3(0.4, 0.5, 0.8), night * 0.7);
	col = mix(col, vec3(0.75, 0.8, 0.85), snow * 0.15);
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	ALBEDO = col;
	ROUGHNESS = 0.04;
	METALLIC = 0.0;
	SPECULAR = 0.6;
	ALPHA = mix(0.82, 0.96, fres);
	// Soft foam band where water meets the quay.
	EMISSION = vec3(0.6, 0.7, 0.7) * smoothstep(0.88, 1.0, edge) * 0.08 * (1.0 - night);
}
