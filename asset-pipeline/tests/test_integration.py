"""Contract tests against the sibling services, run in-process:
  * terrella-v2/catalog: worker claims jobs, uploads assets, reports usage.
  * terrella-v2/puzzles: emitted puzzle_scene.json generates valid puzzles.
Skipped when the sibling directory or its deps are missing."""
import json
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SIBLINGS = ROOT.parent
KIT = tomllib.loads((ROOT / "kits" / "nl_canal.toml").read_text())
KIT["piece"] = [p for p in KIT["piece"] if p.get("generator", "procedural") != "blender"]   # fast, no bpy


def _import_sibling(name, module):
    path = SIBLINGS / name
    if not path.exists():
        pytest.skip(f"no sibling {path}")
    sys.path.insert(0, str(path))
    try:
        return __import__(module)
    except ImportError as e:
        pytest.skip(f"{module} not importable: {e}")


# ------------------------------------------------------------------ catalog

@pytest.fixture
def catalog(tmp_path):
    _import_sibling("catalog", "terrella_catalog")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from terrella_catalog.app import create_app
    from terrella_catalog.auth import hash_token
    from terrella_catalog.config import Settings
    from terrella_catalog.models import User

    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'c.db'}", blob_dir=tmp_path / "blobs",
                              public_base_url=""))
    http = TestClient(app)
    with app.state.db.sessionmaker() as s:
        for name, role in (("admin", "admin"), ("worker", "worker"), ("tomas", "user")):
            s.add(User(name=name, role=role, token_hash=hash_token(f"tok-{name}")))
        s.commit()
    from terrella_assets.catalog_client import CatalogClient
    return {r: CatalogClient(token=f"tok-{r}", http=http) for r in ("admin", "worker", "tomas")}


def _enqueue(c, kind, inp, estimate=0.0):
    return c._req("POST", "/jobs", "enqueue", json={"kind": kind, "input": inp, "estimate_usd": estimate, "force": True}).json()


def test_worker_contract(catalog, tmp_path):
    from terrella_assets.ledger import sync_prices
    from terrella_assets.worker import run_once
    admin, worker, user = catalog["admin"], catalog["worker"], catalog["tomas"]

    added = sync_prices(admin, ROOT / "prices.toml")
    assert any("hi3d/hi3d/generation" in a and "PLACEHOLDER" in a for a in added)
    assert sync_prices(admin, ROOT / "prices.toml") == []                 # idempotent

    cache = tmp_path / "cache"
    job = _enqueue(user, "kit.build", {"kit": KIT}, estimate=0.5)
    run_once(worker, "w1", cache=cache)
    job = user._req("GET", f"/jobs/{job['id']}", "job").json()
    assert job["status"] == "succeeded", job["error"]
    pieces = {worker.get_asset(i)["slug"]: worker.get_asset(i) for i in job["result_asset_ids"]}
    pot = pieces["nl_canal.planter.ai"]
    assert {p["role"] for p in pot["parents"]} == {"atlas", "style", "concept"}
    assert pot["provenance"]["prompt"].startswith("A single planter")
    assert user._req("GET", f"/assets/{pot['id']}/cost", "cost").json()["direct_usd"] == pytest.approx(0.34)
    entries = user._req("GET", "/ledger/entries", "entries").json()
    n_entries = len(entries)
    assert n_entries == 2                                                  # image + mesh, nothing local

    # Re-running the same kit: cache hits and no new spend. The catalog only
    # accepts a job's own assets as results, so pieces come back as new
    # versions of the same slugs with identical blobs.
    job2 = _enqueue(user, "kit.build", {"kit": KIT})
    run_once(worker, "w1", cache=cache)
    job2 = user._req("GET", f"/jobs/{job2['id']}", "job").json()
    assert job2["status"] == "succeeded", job2["error"]
    again = {worker.get_asset(i)["slug"]: worker.get_asset(i) for i in job2["result_asset_ids"]}
    assert set(again) == set(pieces)
    assert all(again[s]["blob"]["sha256"] == pieces[s]["blob"]["sha256"] for s in pieces)
    cost = user._req("GET", f"/assets/{again['nl_canal.planter.ai']['id']}/cost", "cost").json()
    assert cost["direct_usd"] == 0 and cost["lineage_usd"] == pytest.approx(0.34)   # via rebuild_of
    assert len(user._req("GET", "/ledger/entries", "entries").json()) == n_entries

    # Diorama from a registered recipe.
    style_id = next(p["asset_id"] for p in pot["parents"] if p["role"] == "style")
    rec = user._req("POST", "/recipes", "recipe", json={
        "generator": {"name": "canal_street", "version": "0.1.0"}, "osm": {"extract_id": "synthetic"},
        "style_spec_id": style_id, "kit": job["result_asset_ids"], "seed": 7, "params": {"houses": 5}}).json()
    dj = _enqueue(user, "diorama.build", {"recipe_hash": rec["hash"], "diorama_id": "dio_test_canal"})
    run_once(worker, "w1", cache=cache)
    dj = user._req("GET", f"/jobs/{dj['id']}", "job").json()
    assert dj["status"] == "succeeded", dj["error"]
    build = worker.get_asset(dj["result_asset_ids"][0])
    assert build["kind"] == "diorama_build" and build["recipe_hash"] == rec["hash"]
    scene = json.loads(worker.get_blob(build["meta"]["puzzle_scene"]["sha256"]))
    assert scene["recipe_hash"] == f"sha256:{rec['hash']}"
    from terrella_assets.gltf import _chunks
    js, _ = _chunks(worker.get_blob(build["blob"]["sha256"]))
    names = {n["name"] for n in js["nodes"]}
    assert {e["id"] for e in scene["entities"]} <= names
    assert {p["role"] for p in build["parents"]} == {"kit", "style"}


# ------------------------------------------------------------------ puzzles

@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    from terrella_assets.build import build_kit
    from terrella_assets.diorama import KitView, build_diorama
    out = tmp_path_factory.mktemp("d")
    build_kit(KIT, out, ROOT / "prices.toml", log=lambda *_: None)
    ids = json.loads((out / "kits/nl_canal/kit.json").read_text())["slugs"]
    recipe = {"generator": {"name": "canal_street", "version": "0.1.0"}, "osm": {"extract_id": "synthetic"},
              "style_spec_id": "local:x", "kit": sorted(ids.values()), "seed": 7, "params": {"houses": 6}}
    m = build_diorama(KitView.from_out(out, "nl_canal"), diorama_id="dio_test", recipe=recipe, out=out, kit_asset_ids=ids)
    m2 = build_diorama(KitView.from_out(out, "nl_canal"), diorama_id="dio_test", recipe=recipe, out=out / "again")
    return out, m, m2


def test_scene_is_deterministic(scene):
    out, m, m2 = scene
    a = json.loads((out / m["files"]["puzzle_scene"]).read_text())
    b = json.loads((out / "again" / m2["files"]["puzzle_scene"]).read_text())
    assert a == b and m["files"]["glb_sha256"] == m2["files"]["glb_sha256"]


def test_scene_attrs_follow_render(scene):
    out, m, _ = scene
    sc = json.loads((out / m["files"]["puzzle_scene"]).read_text())
    houses = [e for e in sc["entities"] if e["kind"] == "house"]
    assert {h["attrs"]["color"] for h in houses} <= {"red", "brown", "cream", "green"}
    wins = [e for e in sc["entities"] if e["kind"] == "window"]
    assert all(w["attrs"]["shutters"] in ("green", "none") for w in wins)
    assert all({"occupied", "night_owl", "row", "col"} <= set(w["attrs"]) for w in wins)
    assert any("hide_spot" in e["tags"] for e in sc["entities"])


def test_puzzle_library_accepts_scene(scene):
    tp = _import_sibling("puzzles", "terrella_puzzles")
    from terrella_puzzles import Scene, WorldContext, answer_attempt, check, generate, validate
    out, m, _ = scene
    sc = Scene.from_dict(json.loads((out / m["files"]["puzzle_scene"]).read_text()))
    ctxs = json.loads((SIBLINGS / "puzzles" / "fixtures" / "contexts.json").read_text())
    failures = []
    for name, cd in ctxs.items():
        ctx = WorldContext.from_dict(cd)
        for ptype in ("riddle", "trail", "seek", "pattern", "viewpoint"):
            for tier, slot in ((1, "daily"), (2, "daily"), (3, "daily"), (1, "nightfall"), (2, "rain_start"), (3, "first_snow")):
                inst = generate(sc, ctx, slot=slot, ptype=ptype, tier=tier)
                errs = validate(inst, sc)
                if errs or not check(inst, answer_attempt(inst))["solved"]:
                    failures.append((name, ptype, tier, errs))
    assert not failures, failures[:3]
