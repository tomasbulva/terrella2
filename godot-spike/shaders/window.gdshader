// Window glass: sky reflection by day, warm randomised interiors at night (some rooms dark).
shader_type spatial;
render_mode cull_back;

global uniform float night;

varying vec3 world_pos;

float hash(vec3 p) {
	return fract(sin(dot(p, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 cell = floor(world_pos * vec3(2.2, 1.35, 2.2));
	float r = hash(cell);
	float on = step(0.32, r);
	// Warm, varied interiors; lower part dimmer to fake a sill / curtain.
	vec3 warm = mix(vec3(1.0, 0.55, 0.22), vec3(1.0, 0.75, 0.42), hash(cell + 3.1));
	float curtain = mix(0.55, 1.0, smoothstep(0.35, 0.55, fract(world_pos.y * 1.35)));
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	ALBEDO = mix(vec3(0.05, 0.07, 0.1), vec3(0.35, 0.45, 0.55), fres * (1.0 - night));
	ROUGHNESS = 0.08;
	METALLIC = 0.0;
	SPECULAR = 0.8;
	EMISSION = warm * on * curtain * night * 1.6;
}
