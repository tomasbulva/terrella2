// Asset-pipeline kit pieces: one 4x4 palette atlas, the UV cell names the role (see asset-pipeline README).
// Roles: 0 wall 1 wall_alt 2 trim 3 roof 4 window_frame 5 glass 6 door 7 metal 8 wood 9 stone
//        10 foliage 11 foliage_alt 12 trunk 13 flower 14 water 15 ground
shader_type spatial;
render_mode cull_back;

global uniform float night;
global uniform float snow;
global uniform float autumn;
global uniform float wetness;

uniform sampler2D palette : source_color, filter_nearest;

varying vec3 world_pos;
varying vec3 world_normal;
varying flat int role;

float hash(vec3 p) {
	return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

void vertex() {
	vec2 cell = floor(clamp(UV, 0.0, 0.999) * 4.0);
	role = int(cell.y) * 4 + int(cell.x);
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	if (role == 10 || role == 11) {
		float h = max(VERTEX.y, 0.0);
		VERTEX.x += sin(TIME * 1.6 + world_pos.x * 0.7 + world_pos.z * 0.4) * 0.015 * h;
	}
	if (role == 14) {
		VERTEX.y += sin(TIME * 0.9 + world_pos.x * 1.1) * 0.01;
	}
	world_normal = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec3 col = texture(palette, UV).rgb;
	float rough = 0.85;
	vec3 emit = vec3(0.0);
	if (role == 10 || role == 11) {
		vec3 fall = mix(vec3(0.68, 0.15, 0.02), vec3(0.52, 0.32, 0.02), hash(floor(world_pos * 2.0)));
		col = mix(col, fall, autumn);
	} else if (role == 5) {
		// Window glass: sky sheen by day, warm randomised rooms at night.
		vec3 cell = floor(world_pos * vec3(1.2, 0.8, 1.2));
		float on = step(0.3, hash(cell));
		vec3 warm = mix(vec3(1.0, 0.55, 0.22), vec3(1.0, 0.75, 0.42), hash(cell + 3.1));
		float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
		col = mix(col, vec3(0.35, 0.45, 0.55), fres * (1.0 - night));
		emit = warm * on * night * 1.6;
		rough = 0.08;
	} else if (role == 14) {
		float t = TIME;
		vec2 uv = world_pos.xz;
		float r = sin(uv.x * 3.1 + t * 0.9) * sin(uv.y * 2.7 - t * 0.7) + sin((uv.x + uv.y) * 5.3 + t * 1.3) * 0.5;
		// Perturb the normal directly: palette UVs are constant per face, so the mesh has no usable tangents for NORMAL_MAP.
		NORMAL = normalize(NORMAL + (VIEW_MATRIX * vec4(r * 0.18, 0.0, r * 0.14, 0.0)).xyz);
		col = mix(col, col * vec3(0.4, 0.5, 0.8), night * 0.7);
		rough = 0.05;
	}
	if (role != 5 && role != 14) {
		float up = clamp(world_normal.y, 0.0, 1.0);
		float s = smoothstep(0.5, 0.7, up) * snow;
		col = mix(col, vec3(0.93, 0.95, 1.0), s);
		float wet = wetness * (1.0 - s) * (0.4 + 0.6 * up);
		col *= 1.0 - wet * 0.35;
		rough = mix(mix(rough, 0.25, wet), 0.9, s);
	}
	ALBEDO = col;
	ROUGHNESS = rough;
	SPECULAR = 0.5;
	EMISSION = emit;
}
