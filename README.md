# Terrella2 — the new worlds

Living miniature worlds: AI-generated 3D dioramas (Amsterdam, Prague, London…) rendered
on-device, driven by real time-of-day, weather, and season. Built as live wallpaper + in-app.

## Pipeline
`prompt → World Labs Marble API (world gen, ~6 min) → free PLY splats / $2.80 GLB mesh
→ server-side mesh optimization → on-device render (SceneView/Filament, Godot for wallpaper)
→ sun/sky/weather driven by real clock + open-meteo`

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Secrets policy
No keys in the repo. Ever. CI secrets in GitHub Actions settings; local builds via
gitignored `local.properties`/`secrets.properties`. API keys stored in OpenClaw's
protected secret store (egress-proxied, never in chat or shell logs).

## Status
Scaffold. Spike: Marble API world-gen ✅ (2 full worlds, draft-vs-full quality verified),
GLB mesh export ✅. Next: on-device SceneView render with dynamic sun/weather.
