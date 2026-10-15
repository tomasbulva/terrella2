# Terrella puzzles and collectibles: design spec

*v0.1, 15 Oct 2026. Engine-free. Reference implementation in `terrella_puzzles/` (Python, stdlib only); on-device checker in `godot/puzzle_check.gd`.*

## 1. Goals

- Every diorama always has one small, optional puzzle. It takes 1 to 5 minutes, needs no text input, and is solved by looking at and tapping the diorama.
- Puzzles are about **this place, right now**: they point at its kit pieces, and the harder ones only make sense in the current hour, season or weather ("the lit window near a bike" at night, rubber ducks when it rains).
- Solving plays a reward animation and grants a collectible. Collecting is the long-term hook; puzzles are the short one.
- **Generated, never hand-authored**, and correct by construction: every clue has exactly one answer, checked by the validator before anyone sees it.

**Non-goals for v1:** typed answers, timers, fail states, leaderboards, multiplayer, real-world GPS hunts (walking to places). Nothing can be lost. Wrong taps only give gentle feedback.

## 2. Where each part runs

| Part | Runs on | Why |
|---|---|---|
| `generate` | Backend, once per diorama per slot | Same puzzle for everyone on that diorama that day: cacheable, shareable ("today's Prinsengracht riddle"), costs nothing per user. |
| `validate` | Backend, after every generation and on cache load when rules/generator/diorama versions change | Catches broken scenes and generator bugs before players do. |
| `check` | Device (instant feedback) **and** backend (before granting) | Pure function of instance + attempt, ported to GDScript. |
| `pick_rewards` | Backend at grant time | Depends on the player's inventory; deterministic per (puzzle, user), so retries are idempotent. |

**Offline:** the device caches the current instance plus the next day's context-free one. Context-bound puzzles need a live context, so offline players get the context-free fallback. Generation is deterministic over a portable RNG (`rng.py`, conformance vectors included), so it can be ported to the device later if offline matters more than expected. Solves made offline queue their attempt and are granted on reconnect.

**Wallpaper vs app:** the wallpaper never hosts solving. It shows a small diegetic "puzzle waiting" cue (an envelope on a doorstep, a glint on a seek token's anchor at tier 1) and a tap opens the app at the puzzle. This keeps wallpaper input handling trivial and avoids accidental taps from the home screen.

## 3. Inputs

### 3.1 Puzzle scene (`terrella.puzzle_scene/1`)
A sidecar the diorama generator emits next to the glTF. It is the puzzle's view of the recipe: one entry per placed kit piece instance a player can recognise. **Contract with the asset pipeline:** ids must be stable for a given recipe hash and must match node names in the glTF, so the engine can map taps to ids.

```json
{"diorama_id": "dio_nl_amsterdam_prinsengracht", "recipe_hash": "sha256:…", "style": "nl_canal",
 "landmarks": ["westerkerk"],
 "camera": {"pitch_min": 10, "pitch_max": 70, "dist_min": 6, "dist_max": 35},
 "entities": [
  {"id": "house_03", "kind": "house", "pos": [13.5, 0, 0], "attrs": {"color": "brown", "gable": "cornice"}, "kit_piece": "nl_canal.facade.cornice"},
  {"id": "house_03_w00", "kind": "window", "parent": "house_03", "pos": [12.3, 1.5, -0.2],
   "attrs": {"row": 0, "col": 0, "shutters": "green", "flower_box": true, "curtains": "lace", "occupied": true, "night_owl": false}},
  {"id": "bollard_4", "kind": "bollard", "pos": [16.5, 0, -3.6], "tags": ["hide_spot"]}
 ]}
```

- `attrs`: visible properties a clue may name (`shutters`, `color`, `gable`, …) plus bookkeeping the generator uses (`row/col` for facade grids, `occupied`, `night_owl`, `deciduous`, `moored`).
- Tags: `hide_spot` (a seek token can be placed here and is visible from some camera pose), `notable` (good viewpoint subject), `landmark`.
- The fixture `fixtures/scenes/amsterdam_canal.json` (95 entities) stands in for real output until `dutch_houses.py` emits it.

### 3.2 World context (`WorldContext`)
From the world context service. Local times with offset; location is a **precision-5 geohash only** (about 5 km).
`local_date, local_time, phase (night|dawn|day|golden|dusk), phase_ends_at, season (hemisphere-corrected), weather (clear|cloudy|rain|snow|fog|storm), weather_stable_until, snow_cover, geocell`.

### 3.3 Context rules (`data/context_rules.json`)
Data-driven rules turn context into entity state: lamps lit at dusk, night and in fog; occupied windows lit at dusk/dawn (night owls only at night); roofs snowy; foliage by season; unmoored boats gone in a storm. **The renderer must read the same file.** If the shader lights a window the rules consider dark, a clue points at nothing. This is the single most important integration contract in the spec.

## 4. Puzzle types

| Type | Player sees | Player does | Uses context | Tier knobs |
|---|---|---|---|---|
| **riddle** | "Find the window that is lit and near a bike." | Taps one entity | Tier 2+: clues may name lit / snowy / foliage | Predicate count, relations, near-miss distractors |
| **trail** | A chain: "Find the boat painted green. Then find the bike close to your last find." | Taps in order | Same as riddle | 2 / 3 / 4 steps |
| **seek** | "5 rubber ducks are hiding in town." Tokens spawn at hide spots | Taps each token | Token theme: mitten (snow), duck (rain), firefly jar (night), acorn (autumn), paper boat | 3 / 5 / 7 tokens, spacing |
| **pattern** | A postcard of a facade with some windows lit | Taps windows to toggle until they match | Start state is the real lit state right now | Single-toggle at tier 1, Lights-Out cross toggles at 2+, minimum presses, grid size |
| **viewpoint** | A postcard painted from somewhere | Moves the camera until it matches; hot/cold feedback | None (the postcard renders the current weather, so it is always current) | Tolerance: 20°/3 m, 12°/2 m, 7°/1.2 m |

Clue predicates (`predicates.py`): `attr`, `parent_attr` ("on the house with a bell gable"), `near` (a kind within 2.5 m), `near_id` (trail chaining). Prompts are structured (`prompt` field) for localisation. `text.py` + `data/text_en.json` is the reference English renderer.

**Later types worth considering:** count ("how many boats?"; needs a number picker), shadow/sundial (time-based), rainbow-end (after rain), collection sets that unlock a diorama prop. Every new type needs: a generator, a validator rule, a checker branch in both languages, and conformance vectors.

## 5. Generation

- **Seed** = `fnv1a32(recipe_hash | local_date | slot)`; sub-seeds per type and tier. The RNG is mulberry32 on 32-bit integers, chosen because it ports bit-for-bit.
- **Slots:** `daily` always. Bonus slots on context events, which the context service triggers: `first_snow`, `rain_start`, `nightfall`. Bonus slots are what make weather feel rewarding rather than cosmetic. *Proposal: at most 1 daily and 2 bonus slots per local day.*
- **Type and tier:** weighted draw (types riddle 4, seek 4, trail 2, pattern 2, viewpoint 2; tiers cozy 5, curious 4, clever 2). Draws are without replacement, so a diorama that can't host a type (no hide spots, no gridded facade) falls through to the next one.
- **Riddles, unique by construction:** pick a target, add shuffled true predicates until it is the only match, then prune any predicate whose removal keeps it unique. At tier 2+, half the attempts anchor on a context highlight (lit, snowy, orange or bare foliage). Up to 24 attempts. The attempt picked is the closest to the requested tier, preferring context clues.
- **Validity:** until the end of the local day. A context-bound puzzle expires at `min(phase_ends_at, weather_stable_until)`, because "the lit window" stops being true at dawn.
- **Output:** a self-contained instance (`terrella.puzzle/1`). It carries the solution, so `check` needs no scene. The answer is on the device. That is accepted: this is a cozy toy, hashing a choice among ~100 entities protects nothing, and grants are re-checked server-side.

## 6. Difficulty

Measured on the generated puzzle (`difficulty.py`), not just requested. Scores are rough "minutes of attention": riddle = `0.6 + 0.8·predicates + 0.4·relations + 0.35·min(near-misses, 6)`. Near-misses are entities that fail exactly one predicate (the red herrings). Tier bounds are `< 2.5` cozy, `< 4.5` curious, otherwise clever. On the fixture (300 generations per type and tier), the measured tier matches the requested one 100% of the time except cozy riddles (85%) and cozy trails (96%), which slip to curious when no simpler unique clue exists.

**These weights are guesses.** Replace them with real data: log `(type, tier, difficulty, time_to_solve, taps, abandoned)` and refit the weights. Target median solve times: cozy under 1 min, curious 1–3 min, clever 3–5 min.

## 7. Validation (`validate.py`)

It rejects an instance if any of these hold: a field is missing or the schema/type is unknown; the instance was built for a different `recipe_hash`; it references an unknown entity or one absent in its context; a riddle or trail step doesn't have exactly one match; a trail step doesn't chain from the previous one, or revisits an entity; a seek target isn't a hide spot, or spawns don't match targets; a pattern's neighbour graph is asymmetric, or the pattern is unsolvable or already solved; a viewpoint pose is outside the camera limits; the validity window is empty, or a context-bound puzzle outlives its phase; the checker rejects the canonical answer.

## 8. Checking and feedback

`check(instance, attempt) -> {solved, progress 0..1, feedback}`, with feedback in `solved | keep_going | wrong | warmer | colder | invalid`.

- riddle `{"select": id}`; trail `{"selects": [ids]}` (progress = correct prefix); seek `{"found": [ids]}` (order-free); pattern `{"presses": [ids]}` (replayed, so pressing twice cancels); viewpoint `{"eye": [x,y,z], "look_at": [x,y,z], "previous_progress"?}` in world space (engine-neutral, no camera-rig assumptions).
- **Cross-language conformance:** `fixtures/check_vectors.json` has 25 cases over 6 instances. Python and GDScript both pass them (`godot --headless --path godot --script res://tests/run_vectors.gd`). A test fails if generation changes without regenerating the vectors.
- UX intent: wrong taps get a soft wobble and are never counted against the player; progress drives a subtle fill on the puzzle card; hot/cold for viewpoint maps to postcard focus/blur.

## 9. Collectibles

### 9.1 Taxonomy

| Category | What | Granted when | Example |
|---|---|---|---|
| **trinket** | Small generic objects; the common backbone | Any solve | Brass Key, Glass Marble |
| **charm** | Weather and time charms | Solved in that weather or phase | Raindrop, Snowflake, Night Owl, Lightning in a Jar |
| **seasonal** | One set per season | Solved in that season | Shiny Conker, Tulip Bulb |
| **postcard** | Place-style art, rendered from the diorama style | Solved in a style (`style:nl_canal`) | Canal House Postcard |
| **stamp** | Passport stamp, one per diorama, minted (not in the catalog) | First solve in a diorama | `stamp:dio_nl_amsterdam_prinsengracht` |
| **keepsake** | Dated or event items, limited | Specific context and date | First Snow 2026 |

**Rarity weights:** common 60, uncommon 25, rare 10, legendary 5. The real rarity comes from eligibility: Lightning in a Jar needs a storm *and* a solve during it, so it is rare because storms are.

**Variants** (`variant_axis`: season, weather or phase) re-tint one model in the shader, the same way the diorama already does seasons. That multiplies collectible value without more art. The art cost per collectible is one small kit piece, made by the same asset pipeline.

### 9.2 Data model

```text
CollectibleDef  id, name, category, rarity, set, art (catalog asset id),
                eligibility {all[], any[], none[]} over reward_tags, variant_axis?
PuzzleInstance  … reward_tags = context tags + type:, tier:, style:, context_clue
Grant           grant_id (hash of user+puzzle+collectible, idempotent), user_id, collectible_id,
                variant, puzzle_id, slot, diorama_id, geocell (precision 5), context_tags,
                granted_at, duplicate, count_after
Inventory       derived: count per (user, collectible_id[, variant])
```

**Selection:** the eligible pool, minus already-owned items while any unowned remain, then a rarity-weighted draw with RNG seeded by `(puzzle_id, user_id)`. A duplicate increments `count_after`. Proposal: duplicates "polish" the item (shine level 1–3) instead of being dead weight.

**Storage:** grants are append-only, alongside the cost ledger. They link to `puzzle_id → recipe_hash`, so the asset catalog's provenance chain reaches all the way to "this collectible came from this generated puzzle on this generated diorama". That chain is the showcase.

**Privacy:** grants never store more than the geocell. Collections reveal where someone has been at about 5 km resolution, and only to themselves unless sharing is added later.

## 10. Open questions

1. **Hide spot visibility.** Engine-free code can't know if an anchor is visible. Proposal: the diorama generator tags `hide_spot` only after a render-time visibility pass from N orbit poses. *Needs the asset pipeline thread.*
2. **Text quality.** Template English is serviceable, not charming ("the window that is lit and near a bike"). Options: per-style phrase packs, or an LLM rewrite pass at generation time (once per diorama per day, so cheap), with the structured clue kept authoritative. Recommendation: LLM rewrite, validated by checking that the rewritten text still mentions every predicate.
3. **Is a shared daily puzzle right?** I recommend it (cost, social sharing), but it means friends in the same diorama see the same answer. Per-user puzzles cost N× generation and lose shareability.
4. **Collectible economy pacing:** how many daily solves, and should bonus slots grant guaranteed charms? Needs playtesting.

## 11. Layout

```text
puzzles/
  SPEC.md                  this file
  terrella_puzzles/        reference library (Python ≥3.11, stdlib only)
  data/                    context_rules.json, text_en.json, collectibles.json
  fixtures/                stand-in puzzle scene, contexts, check_vectors.json
  godot/                   puzzle_check.gd + headless conformance runner
  tools/                   fixture and vector generators
  tests/                   python3 -m unittest discover -s tests -t .
```
