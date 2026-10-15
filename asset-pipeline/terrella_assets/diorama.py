"""Diorama assembly: kit pieces + layout -> diorama.glb + puzzle_scene.json.

The first layout generator is `canal_street`: a synthetic row of canal houses
on a quay with props and a canal, seeded. OSM-driven layouts plug in later
behind the same output contract:

  * diorama.glb: instanced kit meshes (one mesh per kit piece, many nodes),
    one shared palette material. Every node a player can tap is named with
    its puzzle entity id; helper geometry is "<entity>~<part>" or
    "env~<part>". Engines map a tap to the nearest ancestor whose name has
    no "~". Node extras = {kind, attrs, tags, kit_piece}, so the renderer
    can apply puzzles/data/context_rules.json per node (lit windows/lamps,
    snowy roofs, foliage, boats present).
  * puzzle_scene.json (terrella.puzzle_scene/1): the puzzle library's view of
    the same build. Ids are stable for a given recipe hash (seeded layout, no
    wall clock, no dict-order dependence).
  * Visible attrs are derived from what is actually rendered: a house's
    `color` is the name of its facade palette colour, `shutters` is the
    shutter colour or "none", etc. A clue can never name something the
    player can't see.
  * `hide_spot` is only given to anchors that are unoccluded from enough
    orbit poses within the camera limits (render-time visibility pass, SPEC
    open question 1).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from .gltf import Node, PieceMesh, read_piece, world_transforms, write_scene

LAYOUT_VERSION = "0.1.0"
FLOOR_H = 3.0
HOUSE_DEPTH = 8.0
QUAY_Z = (0.3, 4.0)          # sidewalk/quay in front of the facades
CANAL_Z = (4.0, 10.5)
FAR_QUAY_Z = (10.5, 12.5)
WATER_Y = -0.8

# Named colours for visible attrs. Clues say "the house painted <name>", so
# names are coarse and distinct.
COLOUR_NAMES = {
    "red": "#a8402f", "brown": "#5c4033", "cream": "#efe6cf", "white": "#f6f6f2", "black": "#262626",
    "green": "#2f6a40", "mint": "#9fd8c0", "blue": "#365a8c", "grey": "#8a8a8a", "yellow": "#e3c04f",
    "orange": "#d07a30", "pink": "#e59ab0",
}


def colour_name(hexv: str) -> str:
    def rgb(h):
        h = h.lstrip("#")
        return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)
    c = rgb(hexv)
    return min(COLOUR_NAMES, key=lambda n: float(np.sum((rgb(COLOUR_NAMES[n]) - c) ** 2)))


def recipe_hash(body: dict) -> str:
    """Same canonicalisation as the catalog (terrella_catalog.recipes)."""
    out = dict(body)
    out["kit"] = sorted(set(out.get("kit", [])))
    return hashlib.sha256(json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass
class KitView:
    """What the assembler needs per kit piece, keyed by slug."""
    meshes: dict[str, PieceMesh]
    manifests: dict[str, dict]
    palette_png: bytes
    palette: dict[str, str]      # role -> hex
    kit_name: str

    def has(self, slug: str) -> bool:
        return slug in self.meshes

    def s(self, name: str) -> str:
        return f"{self.kit_name}.{name}"

    def extent(self, slug: str) -> np.ndarray:
        return np.asarray(self.manifests[slug]["stats"]["extent_m"])

    def role_of(self, slug: str) -> str | None:
        return self.manifests[slug]["recipe"]["params"].get("role")

    @classmethod
    def from_out(cls, out: Path, kit_name: str) -> "KitView":
        kit = json.loads((out / "kits" / kit_name / "kit.json").read_text())
        idx = json.loads((out / "index.json").read_text())["assets"]
        manifests = {slug: idx[aid] for slug, aid in kit["slugs"].items()}
        return cls(
            meshes={slug: read_piece((out / m["files"]["glb"]).read_bytes()) for slug, m in manifests.items()},
            manifests=manifests, palette_png=(out / "kits" / kit_name / "palette.png").read_bytes(),
            palette=kit["style"]["palette"], kit_name=kit_name,
        )


class _Rng:
    def __init__(self, seed: int):
        self.r = np.random.default_rng(seed)

    def chance(self, p: float) -> bool:
        return bool(self.r.random() < p)

    def choice(self, xs):
        return xs[int(self.r.integers(len(xs)))]

    def uniform(self, a: float, b: float) -> float:
        return float(self.r.uniform(a, b))


def canal_street(kit: KitView, seed: int, params: dict) -> tuple[Node, list[dict]]:
    """Returns the node tree and the entity list (positions filled in later)."""
    rng = _Rng(seed)
    n_houses = int(params.get("houses", 6))
    root = Node("diorama")
    ents: list[dict] = []

    def ent(node: Node, kind: str, slug: str | None, attrs: dict | None = None, tags=(), parent: str | None = None):
        e = {"id": node.name, "kind": kind, "tags": list(tags), "attrs": attrs or {}}
        if parent:
            e["parent"] = parent
        if slug:
            e["kit_piece"] = slug
        node.extras = {"kind": kind, "attrs": e["attrs"], "tags": e["tags"], **({"kit_piece": slug} if slug else {})}
        ents.append(e)
        return node

    facades = [s for s in (kit.s("facade.brick"), kit.s("facade.dark"), kit.s("facade.white"), kit.s("facade.green"))
               if kit.has(s)]
    gables = [(g, n) for g, n in ((kit.s("gable.step"), "step"), (kit.s("gable.bell"), "bell"), (None, "cornice"))
              if g is None or kit.has(g)]
    windows = [s for s in (kit.s("window.tall"), kit.s("window.flowers"), kit.s("window.plain")) if kit.has(s)]
    doors = [s for s in (kit.s("door.stoep"), kit.s("door.plain")) if kit.has(s)]
    shutter_colour = colour_name(kit.palette.get("wood", "#000000"))
    door_colour = colour_name(kit.palette.get("door", "#000000"))

    x = 0.0
    door_xs: list[float] = []
    last_facade = None
    for h in range(n_houses):
        hid = f"house_{h:02d}"
        w = rng.choice([4.2, 4.6, 5.0])
        floors = rng.choice([2, 3, 3, 4])
        H = floors * FLOOR_H + 0.4
        fac = rng.choice([f for f in facades if f != last_facade] or facades)
        last_facade = fac
        gslug, gname = rng.choice(gables)
        hx = x + w / 2
        x += w + 0.05
        house = ent(Node(hid, translation=(hx, 0.0, 0.0)), "house", fac, tags=["building"],
                    attrs={"color": colour_name(kit.palette[kit.role_of(fac) or "wall"]), "gable": gname,
                           "floors": floors})
        root.children.append(house)
        house.children.append(Node(f"{hid}~facade", mesh=fac, scale=(w, H, 1.0)))
        house.children.append(Node(f"{hid}~body", mesh=kit.s("slab.wall"), translation=(0, 0, -HOUSE_DEPTH / 2),
                                   scale=(w - 0.02, H, HOUSE_DEPTH)))
        g_h = 1.2
        if gslug:
            s = w / float(kit.extent(gslug)[0])
            g_h = float(kit.extent(gslug)[1]) * s
            house.children.append(Node(f"{hid}~gable", mesh=gslug, translation=(0, H, 0), scale=(s, s, s)))
        else:
            house.children.append(Node(f"{hid}~cornice", mesh=kit.s("slab.stone"), translation=(0, H, 0.15),
                                       scale=(w + 0.1, 0.25, 0.5)))
        house.children.append(ent(Node(f"{hid}_roof", mesh=kit.s("roof.gable"), translation=(0, H, -HOUSE_DEPTH / 2 - 0.1),
                                       scale=(w, g_h * 0.95, HOUSE_DEPTH - 0.2)), "roof", kit.s("roof.gable"), parent=hid))
        if kit.has(kit.s("chimney.brick")) and rng.chance(0.6):
            house.children.append(ent(Node(f"{hid}_chimney", mesh=kit.s("chimney.brick"),
                                           translation=(w * 0.22, H + g_h * 0.45 - 0.35, -HOUSE_DEPTH * 0.6)),
                                      "chimney", kit.s("chimney.brick"), parent=hid))
        cols = 3 if w >= 4.6 else 2
        door_col = 1 if cols == 3 else 0
        dslug = rng.choice(doors)
        house.children.append(ent(Node(f"{hid}_door", mesh=dslug,
                                       translation=((door_col - (cols - 1) / 2) * w / cols, 0, 0.3)),
                                  "door", dslug, parent=hid,
                                  attrs={"color": door_colour,
                                         "lantern": bool(kit.manifests[dslug]["recipe"]["params"].get("lantern", False))}))
        door_xs.append(hx + (door_col - (cols - 1) / 2) * w / cols)
        for r in range(floors):
            for c in range(cols):
                if r == 0 and c == door_col:
                    continue
                ws = rng.choice(windows)
                p = kit.manifests[ws]["recipe"]["params"]
                wy = r * FLOOR_H + (1.0 if r == 0 else 0.8)
                house.children.append(ent(
                    Node(f"{hid}_w{r}{c}", mesh=ws, translation=((c - (cols - 1) / 2) * w / cols, wy, 0.3)),
                    "window", ws, parent=hid,
                    attrs={"row": r, "col": c, "shutters": shutter_colour if p.get("shutters") else "none",
                           "flower_box": bool(p.get("flower_box", False)),
                           "occupied": rng.chance(0.7), "night_owl": rng.chance(0.3)}))

    L = x - 0.05
    cx = L / 2

    # --- environment (not entities)
    def env(name, slug, z0, z1, y0, y1, x0=-1.0, x1=None):
        x1 = L + 1.0 if x1 is None else x1
        root.children.append(Node(f"env~{name}", mesh=kit.s(slug), translation=((x0 + x1) / 2, y0, (z0 + z1) / 2),
                                  scale=(x1 - x0, y1 - y0, z1 - z0)))
    env("plinth", "slab.ground", -HOUSE_DEPTH - 1.5, FAR_QUAY_Z[1] + 0.5, -2.6, -1.6, x0=-2.0, x1=L + 2.0)
    env("backyard", "slab.ground", -HOUSE_DEPTH - 1.5, 0.0, -1.6, -0.02)
    env("quay", "slab.stone", QUAY_Z[0] - 0.3, QUAY_Z[1], -1.6, 0.0)
    env("canal_bed", "slab.stone", CANAL_Z[0], CANAL_Z[1], -1.6, -1.4)
    env("water", "slab.water", CANAL_Z[0], CANAL_Z[1], -1.4, WATER_Y)
    env("far_quay", "slab.stone", FAR_QUAY_Z[0], FAR_QUAY_Z[1], -1.6, 0.0)

    # --- props: lanes along the quay, kept off doors and each other
    taken: dict[str, list[float]] = {}

    def free(lane: str, px: float, gap: float, also=()) -> bool:
        for ln in (lane, *also):
            if any(abs(px - q) < gap for q in taken.get(ln, [])):
                return False
        return 0.4 < px < L - 0.4

    def place(lane: str, px: float):
        taken.setdefault(lane, []).append(px)

    lamp_slugs = [s for s in (kit.s("lamp.street"), kit.s("lamp.lantern")) if kit.has(s)]
    i = 0
    for px in np.arange(1.5, L, 7.0):
        slug = lamp_slugs[i % len(lamp_slugs)]
        root.children.append(ent(Node(f"lamp_{i}", mesh=slug, translation=(float(px), 0, 3.2)), "lamp", slug,
                                 attrs={"style": slug.split(".")[-1]}))
        place("edge", float(px))
        i += 1
    trees = [s for s in (kit.s("tree.lime"), kit.s("tree.poplar")) if kit.has(s)]
    i = 0
    for px in np.arange(5.0, L, 7.0):
        if not free("edge", float(px), 1.5):
            continue
        slug = rng.choice(trees)
        species = slug.split(".")[-1]
        root.children.append(ent(Node(f"tree_{i}", mesh=slug, translation=(float(px), 0, 3.4), yaw=rng.uniform(0, 6.28),
                                      scale=(0.75, 0.75, 0.75)),
                                 "tree", slug, attrs={"species": species, "deciduous": True,
                                                      "blossom": species == "lime" and rng.chance(0.4)}))
        place("edge", float(px))
        i += 1
    i = 0
    for px in np.arange(0.8, L, 2.6):
        if free("bollard", float(px), 1.0, also=("edge",)) and rng.chance(0.8):
            root.children.append(ent(Node(f"bollard_{i}", mesh=kit.s("bollard"), translation=(float(px), 0, 3.8)),
                                     "bollard", kit.s("bollard")))
            place("bollard", float(px))
            i += 1
    for d in door_xs:
        place("front", d)
    bike_colour = colour_name(kit.palette.get("metal", "#000000"))
    for i in range(int(params.get("bikes", max(2, n_houses // 2)))):
        for _ in range(20):
            px = rng.uniform(0.8, L - 0.8)
            if free("front", px, 1.6):
                root.children.append(ent(Node(f"bike_{i}", mesh=kit.s("bike.omafiets"), translation=(px, 0, 1.5)),
                                         "bike", kit.s("bike.omafiets"), attrs={"color": bike_colour, "basket": False}))
                place("front", px)
                break
    if kit.has(kit.s("planter.ai")):
        pc = colour_name(kit.palette[kit.role_of(kit.s("planter.ai")) or "foliage"])
        for i in range(int(params.get("planters", 3))):
            for _ in range(20):
                px = rng.uniform(0.6, L - 0.6)
                if free("front", px, 1.3):
                    root.children.append(ent(Node(f"planter_{i}", mesh=kit.s("planter.ai"), translation=(px, 0, 1.0)),
                                             "planter", kit.s("planter.ai"), attrs={"color": pc}))
                    place("front", px)
                    break
    if kit.has(kit.s("boat.sloop")):
        bc = colour_name(kit.palette[kit.role_of(kit.s("boat.sloop")) or "door"])
        for i in range(int(params.get("boats", 2))):
            for _ in range(20):
                px = rng.uniform(3.0, L - 3.0)
                lane = "boat_a" if i % 2 == 0 else "boat_b"
                if free(lane, px, 6.0):
                    bz = 5.4 if lane == "boat_a" else 9.0
                    root.children.append(ent(Node(f"boat_{i}", mesh=kit.s("boat.sloop"), translation=(px, WATER_Y - 0.25, bz)),
                                             "boat", kit.s("boat.sloop"), tags=["notable"],
                                             attrs={"color": bc, "moored": rng.chance(0.7)}))
                    place(lane, px)
                    break
    root.translation = (-cx, 0.0, 0.0)          # centre the street on the origin
    return root, ents


# ---------------------------------------------------------------- visibility

HIDE_KINDS = {"chimney", "door", "planter", "bollard", "bike", "tree", "boat", "lamp"}


def _world_meshes(root: Node, kit: KitView) -> tuple[trimesh.Trimesh, np.ndarray, dict[str, np.ndarray]]:
    """One world-space mesh for ray tests + per-face owning entity id."""
    xf = world_transforms(root)
    vs, fs, owner, off = [], [], [], 0
    bounds: dict[str, np.ndarray] = {}

    def walk(n: Node, ent_id: str):
        nonlocal off
        eid = n.name if "~" not in n.name and n.name != "diorama" else ent_id
        if n.mesh:
            pm = kit.meshes[n.mesh]
            m = xf[n.name]
            v = (np.c_[pm.positions, np.ones(len(pm.positions))] @ m.T)[:, :3]
            f = pm.indices.reshape(-1, 3)
            vs.append(v)
            fs.append(f + off)
            owner.extend([eid] * len(f))
            off += len(v)
            b = np.array([v.min(0), v.max(0)])
            bounds[eid] = b if eid not in bounds else np.array([np.minimum(bounds[eid][0], b[0]),
                                                               np.maximum(bounds[eid][1], b[1])])
        for c in n.children:
            walk(c, eid)
    walk(root, "env")
    return trimesh.Trimesh(np.vstack(vs), np.vstack(fs), process=False), np.array(owner), bounds


def camera_limits(bounds: np.ndarray) -> dict:
    span = float(max(bounds[1, 0] - bounds[0, 0], bounds[1, 2] - bounds[0, 2]))
    return {"pitch_min": 10.0, "pitch_max": 70.0, "dist_min": round(span * 0.3, 2), "dist_max": round(span * 1.4, 2)}


def visibility(root: Node, kit: KitView, ents: list[dict], cam: dict, min_fraction: float = 0.25) -> dict[str, float]:
    world, owner, bounds = _world_meshes(root, kit)
    centre = world.bounds.mean(axis=0)
    dist = (cam["dist_min"] + cam["dist_max"]) / 2
    eyes = []
    for pitch in np.radians([cam["pitch_min"] + 15, 40.0, cam["pitch_max"] - 10]):
        for yaw in np.radians(np.arange(0, 360, 30)):
            eyes.append(centre + dist * np.array([np.cos(pitch) * np.sin(yaw), np.sin(pitch), np.cos(pitch) * np.cos(yaw)]))
    eyes = np.array(eyes)
    out = {}
    cands = [e for e in ents if e["kind"] in HIDE_KINDS and e["id"] in bounds]
    for e in cands:
        b = bounds[e["id"]]
        anchor = np.array([(b[0, 0] + b[1, 0]) / 2, b[1, 1] + 0.05, (b[0, 2] + b[1, 2]) / 2])
        d = anchor - eyes
        L = np.linalg.norm(d, axis=1)
        dirs = d / L[:, None]
        locs, ray_idx, tri_idx = world.ray.intersects_location(eyes, dirs, multiple_hits=True)
        blocked = np.zeros(len(eyes), bool)
        if len(locs):
            hit_d = np.linalg.norm(locs - eyes[ray_idx], axis=1)
            mask = (hit_d < L[ray_idx] - 0.1) & (owner[tri_idx] != e["id"])
            blocked[np.unique(ray_idx[mask])] = True
        out[e["id"]] = float((~blocked).mean())
    return out


# ---------------------------------------------------------------- build

def build_diorama(kit: KitView, *, diorama_id: str, recipe: dict, out: Path, layout: str = "canal_street",
                  kit_asset_ids: dict[str, str] | None = None) -> dict:
    """`recipe` is a catalog RecipeBody; its hash keys the build and the
    puzzle scene. Returns the build manifest."""
    if layout != "canal_street":
        raise KeyError(f"unknown layout {layout!r}")
    rh = recipe_hash(recipe)
    bdir = out / "dioramas" / diorama_id / rh[:20]
    root, ents = canal_street(kit, int(recipe["seed"]), dict(recipe.get("params", {})))

    xf = world_transforms(root)
    for e in ents:
        e["pos"] = [round(float(v), 3) for v in xf[e["id"]][:3, 3]]
    world, _, _ = _world_meshes(root, kit)
    cam = camera_limits(world.bounds)
    vis = visibility(root, kit, ents, cam)
    for e in ents:
        if vis.get(e["id"], 0.0) >= 0.25:
            e["tags"] = sorted(set(e["tags"]) | {"hide_spot"})
    # keep node extras in sync with final tags
    def sync(n: Node, by_id: dict):
        if n.name in by_id and n.extras is not None:
            n.extras["tags"] = by_id[n.name]["tags"]
        for c in n.children:
            sync(c, by_id)
    sync(root, {e["id"]: e for e in ents})

    scene = {
        "schema": "terrella.puzzle_scene/1",
        "diorama_id": diorama_id,
        "recipe_hash": f"sha256:{rh}",
        "style": kit.kit_name,
        "landmarks": [],
        "camera": cam,
        "entities": ents,
    }
    glb = write_scene(root, kit.meshes, kit.palette_png, extras={
        "schema": "terrella.diorama/1", "diorama_id": diorama_id, "recipe_hash": f"sha256:{rh}",
        "layout": {"name": layout, "version": LAYOUT_VERSION}, "context_rules": "terrella.context_rules/1",
        "tap_rule": "nearest ancestor node whose name has no '~'",
    })
    _check_ids(glb, ents)
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "diorama.glb").write_bytes(glb)
    (bdir / "puzzle_scene.json").write_text(json.dumps(scene, indent=1))
    used = sorted({e.get("kit_piece") for e in ents if e.get("kit_piece")} |
                  {n for n in _meshes_used(root)})
    manifest = {
        "schema": "terrella.diorama_build/1",
        "diorama_id": diorama_id, "recipe_hash": rh, "recipe": recipe,
        "layout": {"name": layout, "version": LAYOUT_VERSION},
        "files": {"glb": str((bdir / "diorama.glb").relative_to(out)), "glb_sha256": hashlib.sha256(glb).hexdigest(),
                  "glb_bytes": len(glb), "puzzle_scene": str((bdir / "puzzle_scene.json").relative_to(out))},
        "kit_pieces": used,
        "parents": [kit_asset_ids[s] for s in used] if kit_asset_ids else [],
        "stats": {"entities": len(ents), "tris": int(len(world.faces)),
                  "hide_spots": sum("hide_spot" in e["tags"] for e in ents),
                  "kinds": {k: sum(e["kind"] == k for e in ents) for k in sorted({e["kind"] for e in ents})}},
    }
    (bdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _meshes_used(root: Node) -> set[str]:
    s = set()
    def walk(n):
        if n.mesh:
            s.add(n.mesh)
        for c in n.children:
            walk(c)
    walk(root)
    return s


def _check_ids(glb: bytes, ents: list[dict]) -> None:
    from .gltf import _chunks
    js, _ = _chunks(glb)
    names = [n["name"] for n in js["nodes"]]
    if len(set(names)) != len(names):
        raise AssertionError("duplicate glTF node names")
    missing = {e["id"] for e in ents} - set(names)
    if missing:
        raise AssertionError(f"entities without a glTF node: {sorted(missing)[:5]}")
