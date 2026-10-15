# Terrella catalog

Asset catalog, diorama recipes, generation job queue and per-user cost ledger for Terrella v2.
Engine-agnostic: everything a client renders is glTF binary (`.glb`) plus textures, addressed by SHA-256.

Replaces the terrella2 `backend/` idea of "one city = one monolithic GLB" with:

- **Kit pieces, materials, atlases**: small reusable assets per regional style (`nl-canal.window.sash`).
- **Style specs**: JSON read from a seed image (palette, gable types, roof colours, trees, props, water).
- **Recipes**: a diorama as data. `generator + OSM extract + style spec + pinned kit + seed + params`.
  Keyed by the SHA-256 of its canonical JSON, so the same recipe is always the same build and a rebuild is a cache hit.
- **Builds**: `diorama_build` assets produced from a recipe. A `Diorama` (a place) publishes one approved build.
- **Provenance on every asset** (producer, model, version, prompt, seed, inputs, licence, attribution) and **parent links**, so any asset's full lineage is queryable.
- **Ledger**: append-only spend rows priced from a versioned price table, with per-user monthly budgets enforced *before* enqueue.

## Run

```sh
pip install -e '.[dev]'
pytest
export TERRELLA_DATA_DIR=./data          # SQLite db + blobs land here
terrella-catalog create-user tomas --role admin   # prints a token once
terrella-catalog serve --port 8080       # OpenAPI UI at /docs
```

| Env var | Default | |
|---|---|---|
| `TERRELLA_DATA_DIR` | `./data` | |
| `TERRELLA_DATABASE_URL` | `sqlite:///$DATA_DIR/catalog.db` | Postgres: `postgresql+psycopg://…` (install `.[postgres]`) |
| `TERRELLA_BLOB_DIR` | `$DATA_DIR/blobs` | |
| `TERRELLA_PUBLIC_BASE_URL` | empty (relative URLs) | Prefix for blob URLs in the manifest, e.g. a CDN |

## Roles

| Role | Can |
|---|---|
| `user` | Register recipes and assets, enqueue jobs (budget-checked), read own jobs, own ledger, own budget |
| `worker` | All of the above, plus claim jobs, report progress, record usage, complete jobs. Pipeline services run as workers |
| `admin` | Everything, plus create users, set budgets and prices, approve/reject assets, create and publish dioramas, ledger adjustments |

Public (no token): `GET /catalog/manifest`, `GET /catalog/changes`, `GET /dioramas`, `GET /dioramas/{slug}`, `GET /blobs/{sha}`.

## API for the other services

Full schema: [`openapi.json`](openapi.json) (regenerate with `terrella-catalog openapi --out openapi.json`).

**Asset generation pipeline** (runs as a `worker`):
1. `POST /jobs/claim {worker_id, kinds}` → oldest queued job, or `204`. Compare-and-set, safe with several workers.
2. `POST /jobs/{id}/progress {stage, progress}` while working. A `409` means the user cancelled: stop.
3. `POST /jobs/{id}/usage {provider, model, unit, qty, asset_id?}` for every paid call. Charged to the user who enqueued the job. Without a matching price row it returns `422` instead of silently booking $0; pass `cost_usd` to record a provider-reported amount.
4. `PUT /blobs` (raw body) → `sha256`, then `POST /assets {kind, slug, blob_sha256, provenance, parents, job_id, recipe_hash?}`. A new upload under an existing slug becomes the next version, unless the latest version already has the same blob (and spec): then you get that asset back with `200` and `reused: true`, so rebuilding a kit doesn't mint identical versions. Pass `dedupe: false` to force a new version. `kit_piece` and `diorama_build` must be GLB (checked by magic bytes).
5. `POST /jobs/{id}/complete {status, result_asset_ids}`. List new and reused assets alike. A reused asset keeps its original `job_id`, so this job's spend is split only across the assets it actually created.

**App / wallpaper client** (no auth):
- `GET /dioramas?lat=..&lon=..` → nearest published places with `distance_km`.
- `GET /catalog/manifest` → `{version, dioramas: [{build, dependencies, attribution, ...}]}`. Each file has `sha256`, `size`, `url`; blobs are immutable, so cache by hash forever.
- `GET /catalog/changes?since=<version>` → what changed since the client's last manifest.
- A build's `dependencies` are its direct parents that ship (kit_piece, material, atlas, diorama_build) with a blob. The generator decides what a client must download by declaring them as parents.

**Web prompting / preview UI** (not built here):
- `POST /recipes` returns `{hash, builds, cached}`. If `cached` is true, show the existing build instead of enqueueing.
- `POST /jobs {kind, input, estimate_usd}`. Identical open jobs are deduplicated (`200` + `deduped: true`); `force: true` skips that. `402` with `budget_exceeded` when over budget.
- `GET /assets/{id}/lineage`, `GET /assets/{id}/cost`, `GET /dioramas/{slug}/cost`, `GET /users/me/budget`, `GET /ledger/summary?group_by=user|job|asset|provider|model|unit|day|month`.

**World context service**: only needs `GET /dioramas?lat&lon` to map a location to a place.

## Cost model

- Money is stored as integer nano-USD. Token prices are below a micro-dollar, and integers keep sums exact.
- **Asset direct cost** = ledger rows tagged with the asset + the untagged spend of its producing job, split evenly across that job's results.
- **Asset lineage cost** = direct cost of the asset and every ancestor, each counted once.
- **Diorama cost** = build lineage *excluding* the recipe's shared assets (kit + style spec), plus each shared asset's lineage cost divided by the number of recipes that use it. So a kit piece used by 50 towns costs each one 1/50th.
- **Budget**: `spent this UTC month + open jobs' unspent estimates + new estimate <= monthly budget`. Refunds and corrections are `POST /ledger/adjustments` rows with negative cost; nothing is ever edited.

## Not done yet (deliberate)

- **Migrations**: tables come from `create_all`. Add Alembic before the first schema change that must keep data.
- **Postgres**: models are portable and avoid backend-specific SQL, but tests only run on SQLite.
- **Object storage**: `storage.BlobStore` is local disk behind `put/path/exists`; an S3/R2 backend slots in there.
- **Scale shortcuts**: tag filtering, `recipe_usage_counts` and the reservation sum run in Python. Fine for thousands of rows, needs SQL before tens of thousands.
- **Stale jobs**: a worker that dies leaves its job `running`. Needs a lease/heartbeat timeout.
- **Web UI**: lives with the generation pipeline's preview work; this service only provides its API.
