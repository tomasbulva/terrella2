#!/usr/bin/env python3
"""Builds fixtures/scenes/amsterdam_canal.json: a stand-in for the puzzle sidecar
the diorama generator (dutch_houses.py and successors) should emit.

Run from puzzles/: python3 tools/make_fixture_scene.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from terrella_puzzles.rng import Rng  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "scenes" / "amsterdam_canal.json"

rng = Rng(7)
ents = []
COLORS = ["red", "blue", "green", "cream", "brown", "black"]
GABLES = ["step", "bell", "neck", "cornice", "step", "bell"]
SHUTTERS = ["green", "red", "none", "white"]
CURTAINS = ["white", "yellow", "blue", "lace"]
GRIDS = [(3, 3), (2, 3), (4, 3), (2, 2), (3, 2), (4, 3)]


def add(eid, kind, pos, tags=(), attrs=None, parent=None, kit=None):
    e = {"id": eid, "kind": kind, "pos": [round(p, 2) for p in pos], "tags": list(tags),
         "attrs": attrs or {}}
    if parent:
        e["parent"] = parent
    if kit:
        e["kit_piece"] = kit
    ents.append(e)


for h in range(6):
    hx = h * 4.5
    hid = f"house_{h:02d}"
    rows, cols = GRIDS[h]
    add(hid, "house", (hx, 0, 0), tags=["building"],
        attrs={"color": COLORS[h], "gable": GABLES[h], "floors": rows},
        kit=f"nl_canal.facade.{GABLES[h]}")
    add(f"{hid}_roof", "roof", (hx, rows * 3.0 + 1.5, 0.5), parent=hid, kit="nl_canal.roof.tiles")
    if h % 2 == 0:
        add(f"{hid}_chimney", "chimney", (hx + 1.0, rows * 3.0 + 2.5, 1.0), parent=hid,
            tags=["hide_spot"], kit="nl_canal.chimney.brick")
    add(f"{hid}_door", "door", (hx, 0.0, -0.2), parent=hid,
        tags=["hide_spot"] if h % 3 == 0 else [],
        attrs={"color": rng.choice(["green", "red", "black", "blue"]), "lantern": rng.chance(0.5)},
        kit="nl_canal.door.stoep")
    for r in range(rows):
        for c in range(cols):
            if r == 0 and c == cols // 2:
                continue  # door goes there
            add(f"{hid}_w{r}{c}", "window",
                (hx - 1.2 + c * (2.4 / max(1, cols - 1)), 1.5 + r * 3.0, -0.2), parent=hid,
                attrs={"row": r, "col": c, "shutters": rng.choice(SHUTTERS),
                       "flower_box": rng.chance(0.35), "curtains": rng.choice(CURTAINS),
                       "occupied": rng.chance(0.7), "night_owl": rng.chance(0.3)},
                kit="nl_canal.window.sash")

# Quay furniture along z = -2.5, canal at z = -5.
for i in range(5):
    add(f"lamp_{i}", "lamp", (i * 6.0 + 1.0, 0, -2.5), attrs={"style": "amsterdammertje"},
        kit="nl_canal.lamp.cast_iron")
for i in range(4):
    add(f"tree_{i}", "tree", (i * 6.0 + 4.0, 0, -2.8),
        tags=["hide_spot"] if i % 2 else ["notable"] if i == 2 else [],
        attrs={"species": "elm", "deciduous": True, "blossom": i == 0}, kit="nl_canal.tree.elm")
for i in range(7):
    add(f"bollard_{i}", "bollard", (i * 4.0 + 0.5, 0, -3.6),
        tags=["hide_spot"] if i in (1, 4, 6) else [], kit="nl_canal.bollard")
for i in range(5):
    add(f"bike_{i}", "bike", (i * 5.0 + 2.2, 0, -2.0),
        tags=["hide_spot"] if i == 3 else [],
        attrs={"color": rng.choice(["black", "red", "blue", "mint"]), "basket": rng.chance(0.5)},
        kit="nl_canal.bike.omafiets")
for i in range(3):
    add(f"planter_{i}", "planter", (i * 9.0 + 3.0, 0, -1.2), tags=["hide_spot"],
        attrs={"color": rng.choice(["terracotta", "blue", "white"])}, kit="nl_canal.planter")
for i in range(3):
    add(f"bench_{i}", "bench", (i * 9.0 + 6.5, 0, -2.6), tags=["hide_spot"] if i == 1 else [],
        attrs={"color": rng.choice(["green", "brown"])}, kit="nl_canal.bench")
add("boat_0", "boat", (5.0, -0.6, -5.5), tags=["hide_spot", "notable"],
    attrs={"color": "blue", "moored": True}, kit="nl_canal.boat.sloop")
add("boat_1", "boat", (14.0, -0.6, -6.0), attrs={"color": "red", "moored": False}, kit="nl_canal.boat.sloop")
add("boat_2", "boat", (21.0, -0.6, -5.2), tags=["hide_spot"],
    attrs={"color": "green", "moored": True}, kit="nl_canal.boat.houseboat")
add("westerkerk", "church", (11.0, 0, 9.0), tags=["notable", "landmark"],
    attrs={"name": "Westerkerk"}, kit="landmark.westerkerk")

scene = {
    "schema": "terrella.puzzle_scene/1",
    "diorama_id": "dio_nl_amsterdam_prinsengracht",
    "recipe_hash": "sha256:7f1c0e2a9b",
    "style": "nl_canal",
    "landmarks": ["westerkerk"],
    "camera": {"pitch_min": 10.0, "pitch_max": 70.0, "dist_min": 6.0, "dist_max": 35.0},
    "entities": ents,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(scene, indent=1) + "\n")
print(f"wrote {OUT} ({len(ents)} entities)")
