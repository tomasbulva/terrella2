# Terrella Asset Service — API Contract v1

Backend: FastAPI on `127.0.0.1:18810`, exposed via Caddy at
`https://jillvanc.studio/terrella/api/*` (TLS handled by Caddy).

## Auth

All endpoints require `Authorization: Bearer <token>`. Shared secret stored on
the VPS at `/root/terrella-assets/service.token` (0600). The app stores it in
Settings (prefilled from BuildConfig for beta builds). Beta-grade security —
documented trade-off.

## Location key

Derived server-side from name + country, mirrored by the client for cache dirs:

```
key = f"{name},{country}".trim().lowercase(), whitespace collapsed to single space
Examples: "prague,czechia"  "amsterdam,netherlands"  "new york,united states"
```

## Endpoints

### GET /catalog
```json
{
  "version": 3,
  "assets": [
    {
      "key": "amsterdam,netherlands",
      "name": "Amsterdam",
      "country": "Netherlands",
      "day_video": "/terrella/assets/amsterdam,netherlands/day.mp4",
      "night_video": "/terrella/assets/amsterdam,netherlands/night.mp4",
      "poster": "/terrella/assets/amsterdam,netherlands/poster.jpg",
      "glb": "/terrella/assets/amsterdam,netherlands/model.glb",
      "duration_s": 6,
      "width": 720,
      "height": 1280,
      "created_at": "2026-09-13T09:00:00Z"
    }
  ]
}
```
`version` increments on every catalog mutation. Client compares versions to
avoid re-downloading manifests.

### POST /jobs
Body: `{ "name": "Rome", "country": "Italy", "lat": 41.9, "lon": 12.5 }`

Returns a Job. Dedupe rules:
- Asset already in catalog → `{ "status": "ready", "asset": {...} }` (no job created)
- In-flight job for same key → returns the existing job
- Else creates a queued job (single GPU worker, FIFO)

```json
{
  "job_id": "b3f1...",
  "key": "rome,italy",
  "status": "generating",
  "progress": 0.42,
  "stage": "three_d",
  "error": null,
  "asset": null
}
```

### GET /jobs/{job_id}
Same Job shape. Poll interval guidance for clients: 5 s.

### GET /assets/{key}/{file}
Binary download. `file` ∈ `day.mp4 | night.mp4 | poster.jpg | model.glb`.

## Progress stages & weights

| stage | progress range |
|---|---|
| cutout | 0.05 – 0.10 |
| three_d (TRELLIS) | 0.10 – 0.60 (timer-based, GPU gives no callback) |
| textures | 0.60 – 0.65 |
| qa | 0.65 – 0.70 |
| video_day | 0.70 – 0.80 |
| video_night | 0.80 – 0.90 |
| poster | 0.90 – 0.95 |
| done | 1.0 |

## Video spec (seamless loop)

- 720×1280 portrait, 30 fps, 6.0 s, H.264 yuv420p, silent, `+faststart`
- Camera: slow orbit of **exactly 360°** with vertical bob `sin(2πt)` — first
  frame == last frame so `MediaPlayer.isLooping` has no visible seam
- Day clip: neutral bright lighting. Night clip: dimmed cool-blue lighting
- `poster.jpg`: high-quality still of frame 0

## Seeding

Assets can be seeded from an existing GLB (skip 3D stage): the seeder runs
texture-fix → qa → video_day → video_night → poster → publish.
