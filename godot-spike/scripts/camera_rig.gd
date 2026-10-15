## Orbit camera: drag to rotate, pinch or wheel to zoom, gentle idle drift. In wallpaper mode it follows the home-screen page offset.
class_name CameraRig
extends Node3D

var cam: Camera3D
var yaw := deg_to_rad(62.0)
var pitch := deg_to_rad(-34.0)
var distance := 17.0
var target := Vector3(0, 1.0, 0)
var wallpaper := false
var page_offset := 0.5

var _touches := {}
var _pinch_start := 0.0
var _dist_start := 0.0
var _vel_yaw := 0.0
var _idle := 0.0
var _drag_moved := 0.0
signal tapped(screen_pos: Vector2)


func _ready() -> void:
	cam = Camera3D.new()
	cam.fov = 52.0
	cam.keep_aspect = Camera3D.KEEP_WIDTH
	cam.near = 0.1
	cam.far = 120.0
	add_child(cam)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventScreenTouch:
		if event.pressed:
			_touches[event.index] = event.position
			_drag_moved = 0.0
			if _touches.size() == 2:
				var pts := _touches.values()
				_pinch_start = pts[0].distance_to(pts[1])
				_dist_start = distance
		else:
			if _touches.size() == 1 and _drag_moved < 12.0:
				tapped.emit(event.position)
			_touches.erase(event.index)
		_idle = 0.0
	elif event is InputEventScreenDrag:
		_touches[event.index] = event.position
		_drag_moved += event.relative.length()
		if _touches.size() == 1 and not wallpaper:
			yaw -= event.relative.x * 0.006
			pitch = clampf(pitch - event.relative.y * 0.004, deg_to_rad(-75.0), deg_to_rad(-6.0))
			_vel_yaw = -event.relative.x * 0.006 / maxf(get_process_delta_time(), 0.001)
		elif _touches.size() == 2 and not wallpaper:
			var pts := _touches.values()
			var d: float = pts[0].distance_to(pts[1])
			if _pinch_start > 0.0:
				distance = clampf(_dist_start * _pinch_start / d, 4.0, 28.0)
		_idle = 0.0
	elif event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			distance = maxf(distance * 0.9, 4.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			distance = minf(distance * 1.1, 28.0)


func _process(delta: float) -> void:
	_idle += delta
	if wallpaper:
		# Parallax with the launcher pages plus a slow breathing drift.
		var t := Time.get_ticks_msec() / 1000.0
		var goal_yaw := deg_to_rad(62.0 + (page_offset - 0.5) * 50.0 + sin(t * 0.05) * 6.0)
		yaw = lerp_angle(yaw, goal_yaw, 1.0 - exp(-delta * 3.0))
		pitch = deg_to_rad(-34.0 + sin(t * 0.07) * 2.0)
		distance = 18.0
	else:
		if _touches.is_empty():
			yaw += _vel_yaw * delta
			_vel_yaw = lerpf(_vel_yaw, 0.0, 1.0 - exp(-delta * 4.0))
			if _idle > 8.0:
				yaw += delta * 0.03
	var off := Vector3(0, 0, distance).rotated(Vector3.RIGHT, pitch).rotated(Vector3.UP, yaw)
	cam.global_position = target + off
	cam.look_at(target, Vector3.UP)
