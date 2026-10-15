# World context

Turns **where the user is, what time it is, and what the weather is doing** into one small,
versioned **scene state** that any renderer can consume: key light, ambient, sky colours,
precipitation, fog, wind, wet ground, snow cover, season and foliage.

It is engine-agnostic by construction: the scene state is plain JSON
([`schema/scene-state.v1.schema.json`](schema/scene-state.v1.schema.json)), the derivation is a pure
function, and golden vectors pin the behaviour so ports can't drift.

```
 device (coarse, last-known fix) ──► world_inputs (cached JSON, ~10 KB)  ──► derive(inputs, now, palette) ──► scene_state
 Open-Meteo, 1 request / ≥ 1 h  ──┘     location + 54 h weather timeline        pure, no I/O, ~0.1 ms               v1 JSON
```

## What's here

| Path | What |
|---|---|
| `schema/scene-state.v1.schema.json` | The contract renderers read. Scene space is **+Y up, +X east, −Z north** (Godot's forward = north). Colours are sRGB 0..1. |
| `schema/world-inputs.v1.schema.json` | The cache the client persists (location + weather timeline). |
| `palette/default.json` | Art-tunable light ramp keyed by sun elevation, plus overcast/moon/storm modifiers. Artists edit this, not code. |
| `reference/terrella_world/` | Python reference implementation (the spec in executable form). No runtime dependencies. |
| `godot/addons/terrella_world/` | GDScript port: `TerrellaSceneState.derive()`, `TerrellaWorldContext` autoload (cache, policy, fetch), `TerrellaSceneAdapter` (maps onto `DirectionalLight3D` + `Environment`). |
| `testdata/golden/` | 8 cases (Amsterdam snow/fog/summer, Sydney dusk rain, Tromsø polar night, Singapore storm, stale cache, offline). Each file carries its own inputs and expected output. |

## Design decisions

**Split slow inputs from fast state.** The only things that cost battery or network are the
location fix and the weather fetch. Those live in `world_inputs`. Everything else (sun and moon
position, light colour, wetness decay, season) is recomputed locally from that cache and the clock.
The renderer can ask for a new state every minute, or every frame, for free.

**Fetch a timeline, not a snapshot.** One Open-Meteo call returns current conditions plus 6 past
and 48 future hours. The scene keeps evolving correctly (rain arriving at 15:00, clearing at 18:00)
for two days with no further requests. Past hours drive surface wetness, `snow_depth` drives snow cover.

**One key light.** `light.key` is whichever of sun or moon is brighter, with a suggested shadow
strength. One shadow-casting directional light is what a phone can afford in a wallpaper.

**Graceful degradation, made visible.** `meta.source` is `live` (fetched < 90 min ago), `forecast`
(from the cached timeline), `fallback` (no usable weather: seasonal, partly cloudy defaults) or
`override`. Without location permission the app still renders a correct-ish sky from the device
timezone (longitude guessed, latitude 45°) and never calls the network.

**Overrides for play.** `derive(..., overrides={"weather": {...}})` and the autoload's
`time_offset_s` let the explorable app scrub time or force snow for a puzzle without touching the
real cache.

## Battery

| Rule | Value | Why |
|---|---|---|
| Background work | **none** | No WorkManager, no alarms. The policy runs only when the wallpaper becomes visible or the app resumes, and at most every 15 min while visible. A wallpaper nobody sees costs nothing. |
| Location | `ACCESS_COARSE_LOCATION`, last-known / passive fix only | Never request an active fix from the wallpaper. Snapped to a 0.05° (~5 km) grid: privacy plus a stable cache key. |
| Weather refetch | age ≥ 60 min, or moved > 8 km, or < 12 h of forecast left | Open-Meteo models update hourly; more often buys nothing. |
| Failures | 15 min → 30 → 60 … capped at 4 h | No retry storms in a tunnel. |
| Payload | ~4–8 KB JSON per fetch | 54 hourly rows × 10 variables. |
| State recompute | 60 s timer while active | The sun moves 0.25°/min; tween between states for smoothness. |

Worst realistic case is ~16 small HTTPS requests a day for someone who looks at their phone all
day. The radio wake-ups matter more than the bytes, which is why everything piggybacks on
"became visible" instead of a schedule.

## Accuracy (checked in tests)

- Sun position: NOAA equations, within 0.1° of PyEphem; sunrise/sunset/noon within 30 s of `astral`, polar night and midnight sun handled.
- Moon: suncalc-style low-precision series with topocentric parallax, within 2.5° of PyEphem, phase within 3%. Good enough to light by, not to navigate by.
- Python and GDScript agree on all golden vectors within 2e-3 (1,423 checks).

## Running

All commands run from this folder.

```sh
# Python reference + golden vectors + schema validation (43 tests)
pip install -r reference/requirements-dev.txt
python -m pytest reference/tests

# Regenerate fixtures/golden after an intentional change (then re-run the Godot tests)
python testdata/make_testdata.py

# GDScript port against the same golden vectors (Godot 4.5)
godot --headless --path godot --import
godot --headless --path godot --script res://tests/run_tests.gd
```

## Using it from Godot

```gdscript
# project.godot autoload: WorldContext="*res://addons/terrella_world/world_context.gd"
func _ready():
    WorldContext.scene_state_changed.connect(func(s): TerrellaSceneAdapter.apply(s, $Sun, $WorldEnvironment.environment))
    WorldContext.set_location(lat, lon)        # from the Android plugin, see below
    WorldContext.set_active(true)              # wallpaper visible / app foreground

func _notification(what):
    if what == NOTIFICATION_APPLICATION_PAUSED: WorldContext.set_active(false)
    if what == NOTIFICATION_APPLICATION_RESUMED: WorldContext.set_active(true)
```

Shaders should read the rest directly: `surface.wetness` (roughness/puddles), `surface.snow_cover`
(roof/ground snow mask), `season.foliage` / `season.autumn_tint` (tree material),
`weather.wind.vector_xz` (sway, particle drift), `weather.precipitation` (GPUParticles3D amount),
`sky.star_visibility`, `weather.thunder` (occasional flash).

### Android location (not built yet)

Godot has no location API, so the wallpaper needs a ~30-line Android plugin method. Sketch:

```kotlin
// Requires ACCESS_COARSE_LOCATION. No active request: battery cost is zero.
@UsedByGodot
fun lastKnownCoarseLocation(): Dictionary {
    val lm = activity!!.getSystemService(LocationManager::class.java)
    val loc = listOf(LocationManager.PASSIVE_PROVIDER, LocationManager.NETWORK_PROVIDER)
        .mapNotNull { runCatching { lm.getLastKnownLocation(it) }.getOrNull() }
        .maxByOrNull { it.time } ?: return Dictionary()
    return Dictionary().apply { put("lat", loc.latitude); put("lon", loc.longitude); put("time", loc.time) }
}
```

Call it from `set_active(true)`; if it returns nothing, keep the cached location.

## Known gaps

- **Live Open-Meteo calls are untested here**: the build sandbox can't reach the API, so fixtures are synthetic (exact response shape, invented values). First on-device run should eyeball one real response against `testdata/openmeteo/`.
- No CI workflow yet. Both suites run in seconds and are easy to add once this lands in a repo.
- The Android location plugin above is a sketch, not compiled.
- Palette values are a first pass; they need tuning against the actual art.
- Tropical seasons are flattened to `tropical` (no wet/dry season).
