# Terrella2 Architecture

## Why
Terrella1's wall was monetization (paid app). Terrella2: free app, world credits (IAP),
Terrella Plus subscription (Play-native 7-day trial) for wallpaper/power features.
Testers: closed track is free; license testers get IAPs free.

## Proven (Sept 2026 spike)
- World Labs World API: text → explorable world. Draft (marble-1.0-draft, 150cr, ~30s,
  sketch quality) vs Full (marble-1.1, 1500cr + 80cr pano, ~6 min, production quality).
- Exports: PLY splats FREE (full/500k/150k/100k res), HQ GLB mesh 3500cr (~$2.80, cached).
- Draft quality unusable; full quality is the product look. Always generate full for real
  assets; draft for prompt iteration.
- Generation is async (long-running operations, poll). No speed/priority knob exists;
  speed comes from draft-first UX + pre-generated catalog.

## Runtime model (user never waits)
- First-launch world: pre-generated server-side catalog → instant.
- Custom world: async job + push notification when ready (~6 min, runs while user picks
  name/style). Draft preview can render while full cooks.
- Weather/time/season: NO regeneration ever — on-device rendering driven by
  open-meteo (free, no key) + device clock/location.

## Rendering
- v1 spike: SceneView (Compose + Filament) loading optimized GLB; animated sun + skybox.
- Wallpaper: Godot 4.5 + MIT live-wallpaper plugin + TCA Weather System (volumetric
  clouds, seasons, precipitation). Fallbacks: static server-rendered frames per condition.
- Mesh budget: Marble GLB ~137MB — MUST decimate (gltf-transform) + resize textures
  server-side; target < 25MB, LODs. Splats: ship 500k/150k SPZ variants for "photoreal
  memory" mode.

## Key files
- Spike assets: VPS ~/terrella2-spike/ (alpine village, Amsterdam diorama: PLY + GLB)
- World API docs: https://docs.worldlabs.ai
