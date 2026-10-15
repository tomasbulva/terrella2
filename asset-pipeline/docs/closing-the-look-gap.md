# Closing the gap between the spike's stand-in canal and the kit diorama

Status: pipeline side implemented (water element, merged batch, house lean). The engine side is listed under "Engine changes" for the spike owner.

## What the phone data says

Six CSVs from 2026-10-15, 22:17–22:22. The device is an **SM-F776B (Galaxy Z Flip7)**, not one of the Pixel reference phones. Every run is "high" quality, capped at 30 fps, and all of them hold 29.9 fps. The numbers below are steady state, with the seconds after a scene switch left out.

| Run | Draw calls | CPU % | PSS MB | VRAM MB |
|---|---|---|---|---|
| App, Vulkan, stand-in | 53–63 / 128–144 (two views) | ~15 | 595–656 | 175 |
| App, Vulkan, kit | 206–213 / 285–292 | ~20 | 558–686 | 175 |
| App, GL, kit | 185–217 | ~34 | 384 | 59 |
| Wallpaper, Vulkan, stand-in | 43–47 | ~8 | 534 | 147 |

- **Draw calls.** For the same view, the kit costs 3.5–4x the stand-in. The "45–55" figure is the wallpaper's; in the app the stand-in sits at 55–145 depending on the view.
- **Geometry is not the problem.** Primitives are similar (kit 72–78k, stand-in 58–79k). The cost is per-object overhead: the kit GLB has **92 mesh nodes**, each drawn once per pass, while the stand-in merges into about 15 surfaces.
- **CPU.** The kit runs about 5 points higher than the stand-in on Vulkan. GL runs about 14 points higher than Vulkan for the same kit. That matches Tomas's "Vulkan used less CPU".
- **Memory needs watching.** Vulkan PSS is 560–690 MB, against 384 on GL. The wallpaper process alone is at **534 MB**. That's large for a live wallpaper, which the system is quick to kill, and it's a separate problem from this one.
- **Battery current isn't usable** from these runs. It swings with screen and transition state, so it would need a longer fixed-scene run.

## Why the stand-in looks better (ranked)

1. **Water.** The stand-in uses a dedicated alpha-blended shader: depth tint from shallow to deep, two scrolling noise normals, a fresnel alpha, rain rings and a foam band at the quay. It also has a dark canal bed and resin cut-away faces, which make the canal read as a diorama. The kit had `slab.water`, an opaque palette box with a sine wobble.
2. **Surface detail.** The stand-in's `base.gdshader` adds world-space brick courses with mortar, roof tiles, cobbles and planks. Kit faces are flat palette colour.
3. **Colour variety.** The stand-in picks each house from 4 brick and 6 plaster colours. The kit has 4 facade pieces over 2 wall roles.
4. **Silhouette.** The stand-in adds per-house lean and list, 4 gable types, cornices, glazing bars, stoep steps, ivy and a bridge. The kit has no lean and fewer details.
5. **Framing.** The stand-in sits on a wooden plinth with resin ends. The kit has a stone slab.

## What the pipeline now does

| Change | Effect |
|---|---|
| **Water is a scene element.** `env~water` is a 1 m gridded surface with its own material, `terrella.water` (alpha blend). `extras.water` = `{level, bed, bounds, shallow, deep, flow}`. `TEXCOORD_0` = (along, across) in 0..1, and `TEXCOORD_1` is in metres. `env~resin` closes both canal ends. | The engine swaps in its water shader by material name. `slab.water` is no longer used. |
| **Merged batch (`--batch merged`, the default).** All static kit geometry is baked into one mesh, `env~static`, with one palette material. Each vertex carries `TEXCOORD_2` = (entity_index, height above its piece's pivot). Entity nodes stay as empty nodes, with extras `{kind, attrs, tags, kit_piece, entity_index, aabb}`. Boats stay instanced because they move and toggle. | **92 mesh nodes become 5** (static, water, resin, 2 boats). Puzzle entities are byte-identical to the instanced build, and the test checks this. |
| **House lean.** Each house gets a list of ±1.2% and a lean toward the canal of 1–3.5%. This is on for recipes with layout ≥ 0.2.0 and can be turned off with `params.lean`. | It's baked in during the merge. Instanced output refuses lean, because glTF TRS can't express shear. |
| **Preview.** Lit windows now come from a per-entity state texture, taps resolve through `TEXCOORD_2`, and the water gets a cheap ripple stand-in. | Same scheme the engine should use. |

Costs:
- The GLB grows from 0.5 MB to 2.0 MB (26.8k vertices, with no instancing reuse). Gzip in transit roughly halves that. If it matters, quantizing positions and normals (`KHR_mesh_quantization`) is the next lever.
- Both GLBs pass the Khronos validator with 0 errors and 0 warnings.

Expected on the phone: kit draw calls about equal to the stand-in's for the same view, and CPU within a point or two. That's an inference, not a measurement, until the spike loads the merged GLB.

## Engine changes (godot-spike owner)

1. **Materials by name.** `kit_palette` maps to `kit.gdshader`, and `terrella.water` maps to `water.gdshader`. Feed `shallow`/`deep` from `extras.water`. Replace the `abs(world_pos.z) / edge_half_width` edge with `abs(UV.y * 2.0 - 1.0)`, because the pipeline's canal isn't centred on z = 0.
2. **Entity state texture.** Make an N+1 × 1 texture, filled from `context_rules.json` per entity (lit, highlight, hidden). The shader reads `entity = int(CUSTOM0.x + 0.5)`. Godot should import `TEXCOORD_2` as `CUSTOM0`, but **verify on import**; if it doesn't, tell the pipeline and it'll move the channel.
3. **Foliage sway.** Use `CUSTOM0.y` (height above the piece's pivot) instead of `VERTEX.y`, so window-box flowers don't sway like treetops.
4. **Taps.** Hit-test `extras.aabb` (in root space), or use the physics ray's `face_index`, then the triangle's `CUSTOM0.x`. Anchors and puzzle positions don't change.
5. **Re-measure** kit vs stand-in with the same camera and the same seed.

## Next pipeline steps (not done)

- **Surface patterns per role.** Port `base.gdshader`'s brick, tile, cobble and plank patterns into `kit.gdshader`. Select them with a per-kit `surface` table in `kit.json` (role → pattern, scale), sampling `UV2` (`TEXCOORD_1`, metres, consistent across the merged mesh). This is a cheap win with no extra geometry.
- **Colour variants.** Give each house a facade variant from a `[style.variants]` list, carried in the entity state texture as a tint index. `house.color` then names the variant, so clues still match what's rendered.
- **Detail pieces.** Cornices, glazing bars, stoep steps, ivy, a bridge and more gable types. These are kit pieces plus layout rules. Merging makes them free in draw calls.
- **Plinth and bed.** A wooden plinth piece and a dark canal-bed role.
- **Baked AO.** Still the largest look item on a phone. It belongs in a Blender bake stage.
