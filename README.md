# Terrella

A cozy, fully 3D miniature of where you are, as an explorable app and an Android live wallpaper. It follows your location, the time of day, the season and the live weather. Each diorama also hides a small treasure-hunt puzzle; solving it plays a reward animation and grants a collectible.

It's an art project first and a showcase of agent-driven art generation second. Dioramas are not painted by one big generative model. They are **assembled from small, reusable kit pieces under a style spec**. A hallucination can therefore only produce a wrong colour or one replaceable prop, never a broken world, and every asset can be traced back to the recipe, model and prompt that made it.

## How it fits together

```
 style spec (from a seed image)            OSM / layout rules (synthetic for now)
          │                                          │
          ▼                                          ▼
 asset-pipeline ── kit pieces (glTF) ──► diorama assembly ──► diorama.glb + puzzle_scene.json
   procedural · Blender · AI 3D               │                      │
          │ usage + provenance                ▼                      ▼
          └──────────────────────────► catalog ◄──────────── puzzles (generate/validate/check)
                                   assets · recipes · jobs ·          ▲
                                   ledger · client manifest           │ context (phase, weather, season)
                                              │                       │
                                              ▼                world-context ── Open-Meteo
                                     godot-spike (app + live wallpaper) ◄── scene state (light, sky, rain, snow)
```

| Directory | What | Status |
|---|---|---|
| [`asset-pipeline/`](asset-pipeline/README.md) | Kit pieces from procedural code, Blender scripts or AI image-to-3D. Cleanup to mobile budgets, a palette-atlas material, content-hashed cache, provenance and cost ledger. Assembles instanced dioramas and emits `puzzle_scene.json`. Runs as a catalog worker. | Working; AI providers stubbed |
| [`catalog/`](catalog/README.md) | Asset catalog, diorama recipes, generation job queue, per-user cost ledger with budgets, client manifest. FastAPI + SQLAlchemy. | Working (SQLite) |
| [`world-context/`](world-context/README.md) | Location + time + weather → one versioned scene state (key light, sky, precipitation, wetness, snow, season). Python reference + GDScript port + golden vectors. | Working |
| [`puzzles/`](puzzles/README.md) | Puzzle and collectible rules ([SPEC](puzzles/SPEC.md)). Five puzzle types, generated and validated as unique by construction, with a GDScript checker. `data/context_rules.json` is shared with the renderer. | Working |
| [`godot-spike/`](godot-spike/README.md) | Godot 4 app + live wallpaper spike that measures fps, memory and battery on Pixel 7 / 9 Pro. Loads the pipeline's diorama. | Spike |

### Contracts between the parts
- **glTF kit pieces.** Metres, +Y up, front +Z. One mesh and one material per piece, palette atlas in `TEXCOORD_0`, box-projected `TEXCOORD_1` plus explicit tangents for normal maps.
- **`diorama.glb`.** Static geometry is merged into one mesh, a handful of draw calls. Each vertex carries its puzzle entity index (`TEXCOORD_2`). Entity nodes are named with the puzzle entity id, and their extras carry `{kind, attrs, tags, entity_index, aabb}`, which the renderer evaluates with `puzzles/data/context_rules.json`. That way the window a clue calls lit is the window the shader lights. Water is a scene element (`terrella.water` material plus `extras.water`), rendered by the engine's water shader.
- **`puzzle_scene.json`** (`terrella.puzzle_scene/1`). Stable per recipe hash.
- **Scene state** (`world-context/schema/scene-state.v1.schema.json`). Plain JSON, so any renderer can consume it.
- **Catalog API** ([`catalog/openapi.json`](catalog/openapi.json)). The pipeline is a `worker`; apps read the public manifest.

## Decisions so far
- **Engine:** Godot 4 for both the app and the Android wallpaper, gated by the measurements in `godot-spike/`. The fallback is a native Filament wallpaper plus a Godot app, sharing the same glTF and catalog.
- **No video wallpaper.** The product is a living game, and the wallpaper is one view of it. Higher battery use is accepted, and users are told.
- **Platform:** Android first. iOS later; it has no third-party live wallpaper API, so iOS gets the app and widgets.

## Legacy
`app/`, `backend/` and `docs/ARCHITECTURE.md` are the earlier terrella2 draft: Filament/SceneView, an MP4 day/night wallpaper and one monolithic GLB per city. The v2 directories above supersede them. They stay until the v2 app replaces the Android module, and CI (`.github/workflows/build.yml`) still builds only that module.

## Secrets policy
No keys in the repo. CI secrets live in GitHub Actions settings; local builds use gitignored files or environment variables (e.g. `KS_PASS` for signing the spike APK). Paid AI providers are stubbed until their keys and real prices are configured outside the repo.
