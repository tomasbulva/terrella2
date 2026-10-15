# asset-pipeline

Agent-driven asset generation for Terrella v2. It turns **a style spec and piece requests into mobile glTF kit pieces**, then **assembles kit pieces into a diorama** (`diorama.glb` + `puzzle_scene.json`). Every artefact carries its recipe and provenance, and every paid call is billed. It runs standalone (writing an output folder) or as a **worker for `../catalog`**. The GLBs load in Godot, Filament and Unity.

```
pip install -e '.[dev]'            # add '.[blender]' for the bpy wheel, or put `blender` on PATH
python -m terrella_assets build kits/nl_canal.toml --out out          # kit pieces
python -m terrella_assets diorama --out out --houses 6 --seed 7       # diorama.glb + puzzle_scene.json
python -m terrella_assets ledger out --by provider                    # or user | artefact | job | model
python -m terrella_assets preview out      # three.js preview; serves terrella-v2/ so it can read ../puzzles rules
python -m terrella_assets sync-prices --catalog URL --token ADMIN     # push prices.toml rows the catalog lacks
python -m terrella_assets worker  --catalog URL --token WORKER        # claim kit.build / diorama.build jobs
pytest                                                                # 14 tests; integration ones need ../catalog, ../puzzles
```

Screenshots: [kit pieces](examples/kit_pieces.png), [diorama by day](examples/diorama_day.png), [at night with context rules](examples/diorama_night.png). Example sidecar: [puzzle_scene.json](examples/puzzle_scene.dio_nl_synthetic_canal.json).

## Stages

```
kit.toml ─► generator ─► cleanup ─► export ─────────────► kit pieces (GLB + manifest + ledger rows)
            procedural    repair     palette-atlas GLB          │
            blender       decimate   validate                   ▼
            ai3d:<prov>   scale,     (budget, pivot)      layout (canal_street) ─► diorama.glb + puzzle_scene.json
                          pivot                           + hide-spot visibility pass
```

| Generator key | What | Status |
|---|---|---|
| `procedural` | trimesh primitives: facade, slab, roof_gable, window, door, shutter_pair, chimney, bollard, street_lamp, tree, gable_step, flower_box, bike, boat | works |
| `blender`, `blender:<script.py>` | headless Blender script (binary or `bpy` wheel); `blender/kit_pieces.py` has gable_bell and lantern | works with bpy 5.2.2 |
| `ai3d:<mesh>[+<image>]` | prompt → concept image → image-to-3D | `mock` works; `hi3d`, `hunyuan3d`, `trellis2-local`, `gemini-image` are stubs that refuse to run |

## Contracts

**Kit pieces**
- The frame is metres, +Y up, front +Z. Pivots: `base` = bottom centre; `wall` = bottom centre of the back plane, protruding along +Z; `center`.
- Each piece is one mesh with one primitive and one material. Base colour comes from a 4×4 palette atlas, one swatch per role (`spec.ROLES`, append-only). The shader gets the role from the UV cell (`cell = floor(uv*4); role = cell.y*4 + cell.x`). Restyling swaps the PNG; seasons, snow and time of day belong in the shader.
- Ids: `geometry_hash = H(recipe)` covers generator + version (+ script hash), kind, params, seed, pivot, height, budget and the style inputs that change geometry (wobble; for AI, the prompt). `asset_id = H(geometry, palette)`. Same recipe → cache hit → $0.
- The catalog slug is `<kit>.<piece name>`, e.g. `nl_canal.window.tall`.
- **Normal maps:** `TEXCOORD_0` is constant per face, so engines can't derive tangents from it (Godot gets NaN and normal-mapped faces turn white). Every GLB therefore also ships `TEXCOORD_1`, a box projection in metres, plus explicit `TANGENT`s consistent with it. Sample normal and detail maps with `TEXCOORD_1` (Godot: `UV2`). All outputs pass the Khronos glTF validator with 0 errors and 0 warnings.

**Diorama (`diorama.glb`)**
- Instanced: one mesh per kit piece, with many nodes pointing at it, and one shared material.
- **Node name = puzzle entity id.** Helper geometry is named `<entity>~<part>` or `env~<part>`. Tap rule: walk up to the nearest ancestor whose name has no `~`.
- **Node extras = `{kind, attrs, tags, kit_piece}`**, so the renderer can apply `../puzzles/data/context_rules.json` per node. The preview does exactly that for lit windows and lamps and for boats being present.

**Puzzle scene (`terrella.puzzle_scene/1`)**
- Stable for a recipe hash: the layout is seeded, the output is byte-identical on rebuild, and this is tested.
- Visible attrs are derived from what is rendered. `house.color` is the name of the facade's palette colour, `window.shutters` is the shutter colour or `none`, and so on. A clue can't name something the player can't see.
- `hide_spot` is given only to anchors unoccluded from ≥25% of 36 orbit poses inside the camera limits. This is a ray-cast pass, and it answers SPEC open question 1.
- Checked against `terrella_puzzles`: all 5 types × 3 tiers × 4 slots × 5 fixture contexts (300 combinations) generate, validate and solve.

**Catalog (`../catalog/openapi.json`)**, as a `worker`:
- `kit.build {kit: <kit toml as dict>, only?}` produces a `style_spec` (`spec.roles` = role → hex), an `atlas` (palette PNG), a `seed_image` per AI piece (parent role `concept`) and a `kit_piece` per piece (parents `atlas`, `style`).
- `diorama.build {recipe_hash, diorama_id}` reads the `RecipeBody`, downloads the kit blobs and uploads a `diorama_build` (parents `kit`, `style`). `puzzle_scene.json` is uploaded as a blob and referenced at `meta.puzzle_scene.sha256`.
- Usage: each non-local usage row goes to `POST /jobs/{id}/usage`, tagged with the asset it produced, for the user who enqueued the job. Cache hits report nothing.
- Rebuilding an unchanged kit is free and mints nothing: the geometry cache means no usage is reported, and the catalog returns the identical latest version (`reused: true`), which the job lists as its result.
- `prices.toml` uses exact `(provider, model, unit)` keys like the catalog. Real providers have **placeholder** rows, flagged as such in the catalog's price note. Replace them from invoices before the first paid call.

## Plugging in `dutch_houses.py`

Wrap its builders as kinds in a script that follows the contract in `terrella_assets/generators/blender.py`:
- read `--request req.json`;
- build in Blender (+Z up, front −Y);
- name each material after its palette role;
- export GLB to `--out`.

Reference it as `generator = "blender:path/to/script.py"`. The lean/bend belongs in the layout as a per-house transform, not baked into pieces.

## Known gaps

- **AI meshes lose their own texture.** They get recoloured to one role until an atlas bake step exists.
- **No baked AO.** This is the biggest look risk on a phone; it belongs in a Blender bake stage.
- **Layout is synthetic (`canal_street`), not from OSM.** The output contract is what an OSM layout must also meet.
- **Per-node emission (lit windows) needs per-instance shader params in the engine.** Godot supports `instance uniform`.
- **One worker per cache dir.** There's no locking.
- **`puzzle_scene` is not its own asset kind** in the catalog; it's a blob referenced from build meta. Worth adding a kind if clients ever download it.
- **The preview is a plain three.js viewer, not the engine's web export.**
