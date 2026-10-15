"""Catalog worker: claim jobs, build, upload with provenance + parents, report usage.

Job kinds (JobCreate.kind, `^[a-z0-9_]+\\.[a-z0-9_]+$`):

  kit.build      input {"kit": <kit spec as a dict, same shape as kits/*.toml>,
                        "only": [piece names]?}
                 -> style_spec + atlas + one kit_piece per piece (+ seed_image
                    for AI pieces). Result ids = the kit pieces.
  diorama.build  input {"recipe_hash": str, "diorama_id": str}
                 -> one diorama_build (GLB); puzzle_scene.json is uploaded as a
                    blob and referenced from the build's meta.

Billing: each paid call (non-"local" usage) is reported with
POST /jobs/{id}/usage, tagged with the asset it produced, so the catalog
charges the user who enqueued the job. Usage is reported only for geometry
that was actually generated in this job; cache hits cost nothing.
"""
from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import traceback
from pathlib import Path

from . import __version__
from .build import build_kit
from .catalog_client import CatalogClient, JobCancelled
from .diorama import LAYOUT_VERSION, KitView, build_diorama, recipe_hash
from .gltf import read_piece
from .spec import ROLES, load_kit

KINDS = ["kit.build", "diorama.build"]


def _get_or_create(c: CatalogClient, body: dict, blob: bytes | None = None, content_type: str = "application/octet-stream",
                   result: bool = False) -> dict:
    """Inputs (style spec, atlas, concept image) are reused across jobs when the
    content is identical. Results are reused only within the same job (a
    retry), because the catalog requires a job's results to belong to it; a
    cache-hit rebuild therefore mints a new version with zero cost."""
    if blob is not None:
        body["blob_sha256"] = c.put_blob(blob, content_type)
    found = c.find_asset(body["kind"], body["slug"], body.get("blob_sha256"), body.get("spec"),
                         job_id=body.get("job_id") if result else None)
    return found or c.create_asset(body)


def _style_spec_body(kit) -> dict:
    st = kit.style
    order = [r for r in ROLES if r in st.palette]
    return {
        "kit_family": kit.name,
        "palette": [st.palette[r] for r in order],
        "roles": {r: st.palette[r] for r in order},          # extra key: role -> hex (what the generator consumes)
        "notes": st.notes or None,
        "wobble": st.wobble,
    }


def run_kit_build(c: CatalogClient, job: dict, cache: Path, tmp: Path) -> list[str]:
    jid = job["id"]
    raw = job["input"]["kit"]
    kit = load_kit(raw)
    only = set(job["input"].get("only") or []) or None

    c.progress(jid, "style_spec", 0.02)
    spec_body = _style_spec_body(kit)
    style = _get_or_create(c, {
        "kind": "style_spec", "slug": f"{kit.name}.style", "style_family": kit.name, "spec": spec_body,
        "provenance": {"producer": kit.style.source.get("kind", "hand-authored"), **{
            k: v for k, v in kit.style.source.items() if k != "kind"}},
        "job_id": jid,
    })

    c.progress(jid, "generate", 0.05)
    out = cache                      # persistent: geometry cache hits are what make re-runs free
    manifests = build_kit(raw, out, Path(__file__).resolve().parents[1] / "prices.toml",
                          user_id=job["user_id"], job_id=jid, only=only, log=lambda *_: None)
    palette = (out / "kits" / kit.name / "palette.png").read_bytes()
    atlas = _get_or_create(c, {
        "kind": "atlas", "slug": f"{kit.name}.palette", "style_family": kit.name,
        "meta": {"layout": json.loads((out / "kits" / kit.name / "kit.json").read_text())["palette_layout"]},
        "provenance": {"producer": "terrella_assets.palette", "model_version": __version__},
        "parents": [{"asset_id": style["id"], "role": "style"}], "job_id": jid,
    }, palette, "image/png")

    results = []
    for i, m in enumerate(manifests):
        c.progress(jid, f"upload:{m['name']}", 0.1 + 0.9 * i / max(1, len(manifests)))
        prov = m["provenance"]
        parents = [{"asset_id": atlas["id"], "role": "atlas"}, {"asset_id": style["id"], "role": "style"}]
        concept = out / prov["work_dir"] / "concept.png"
        if "prompt" in prov and concept.exists():
            seed_img = _get_or_create(c, {
                "kind": "seed_image", "slug": f"{m['slug']}.concept", "style_family": kit.name,
                "provenance": {"producer": prov["image"]["provider"], "model": prov["image"]["model"],
                               "prompt": prov["prompt"], "seed": prov.get("seed")},
                "parents": [{"asset_id": style["id"], "role": "style"}], "job_id": jid,
            }, concept.read_bytes(), "image/png")
            parents.append({"asset_id": seed_img["id"], "role": "concept"})
        glb = (out / m["files"]["glb"]).read_bytes()
        prev = c.find_asset("kit_piece", m["slug"], hashlib.sha256(glb).hexdigest())
        if prev is not None and prev.get("job_id") != jid:
            # Same bytes built earlier: link it so lineage cost still reaches the original spend.
            parents.append({"asset_id": prev["id"], "role": "rebuild_of"})
        mesh_prov = prov.get("mesh", {})
        asset = _get_or_create(c, {
            "kind": "kit_piece", "slug": m["slug"], "style_family": kit.name, "category": m["category"],
            "tags": m["tags"],
            "meta": {k: m[k] for k in ("geometry_hash", "palette_hash", "recipe", "stats", "validation", "pivot",
                                       "units", "up", "front")} | {"pipeline_asset_id": m["id"]},
            "provenance": {
                "producer": f"terrella_assets:{m['recipe']['generator']}",
                "model": mesh_prov.get("model") or prov.get("builder"),
                "model_version": m["recipe"]["generator_version"],
                "prompt": prov.get("prompt"), "seed": prov.get("seed"), "params": m["recipe"]["params"],
                "geometry_hash": m["geometry_hash"], "pipeline_version": __version__,
                **({"script_sha256": prov["script_sha256"]} if "script_sha256" in prov else {}),
            },
            "parents": parents, "job_id": jid,
        }, glb, "model/gltf-binary", result=True)
        if not m["cost"]["cache_hit"]:
            for u in m["cost"]["usage"]:
                if u["provider"] != "local":
                    c.usage(jid, u["provider"], u["model"], u["unit"], u["qty"], asset_id=asset["id"])
        results.append(asset["id"])
    return results


def run_diorama_build(c: CatalogClient, job: dict, cache: Path, tmp: Path) -> list[str]:
    jid = job["id"]
    h = job["input"]["recipe_hash"]
    diorama_id = job["input"]["diorama_id"]
    rec = c.get_recipe(h)
    body = rec["body"]
    if recipe_hash(body) != h:
        raise RuntimeError(f"recipe hash mismatch: catalog {h}, local {recipe_hash(body)}")
    if body["generator"]["name"] != "canal_street":
        raise RuntimeError(f"no layout generator {body['generator']['name']!r}")

    c.progress(jid, "fetch_kit", 0.05)
    style = c.get_asset(body["style_spec_id"])
    meshes, manifests, ids, palette_png = {}, {}, {}, None
    for aid in body["kit"]:
        a = c.get_asset(aid)
        if a["kind"] != "kit_piece":
            continue
        glb = c.get_blob(a["blob"]["sha256"])
        pm = read_piece(glb)
        meshes[a["slug"]] = pm
        manifests[a["slug"]] = {"stats": a["meta"]["stats"], "recipe": a["meta"]["recipe"]}
        ids[a["slug"]] = a["id"]
        palette_png = palette_png or pm.image_png
    if not meshes:
        raise RuntimeError("recipe kit has no kit_piece assets")
    kit_family = style["spec"]["kit_family"]
    kit = KitView(meshes=meshes, manifests=manifests, palette_png=palette_png,
                  palette=style["spec"].get("roles") or {}, kit_name=kit_family)

    c.progress(jid, "assemble", 0.3)
    m = build_diorama(kit, diorama_id=diorama_id, recipe=body, out=tmp, kit_asset_ids=ids)
    out = tmp
    scene_bytes = (out / m["files"]["puzzle_scene"]).read_bytes()
    scene_sha = c.put_blob(scene_bytes, "application/json")

    c.progress(jid, "upload", 0.9)
    parents = [{"asset_id": ids[s], "role": "kit"} for s in m["kit_pieces"] if s in ids]
    parents.append({"asset_id": style["id"], "role": "style"})
    asset = _get_or_create(c, {
        "kind": "diorama_build", "slug": f"{diorama_id}.build",
        "style_family": kit_family, "recipe_hash": h,
        "meta": {"puzzle_scene": {"sha256": scene_sha, "schema": "terrella.puzzle_scene/1"},
                 "layout": m["layout"], "stats": m["stats"], "diorama_id": diorama_id},
        "provenance": {"producer": f"terrella_assets:{body['generator']['name']}",
                       "model_version": LAYOUT_VERSION, "seed": body["seed"], "params": body.get("params", {}),
                       "inputs": [f"osm:{body['osm']['extract_id']}"], "pipeline_version": __version__},
        "parents": parents, "job_id": jid,
    }, (out / m["files"]["glb"]).read_bytes(), "model/gltf-binary", result=True)
    return [asset["id"]]


HANDLERS = {"kit.build": run_kit_build, "diorama.build": run_diorama_build}


DEFAULT_CACHE = Path.home() / ".cache" / "terrella_assets"


def run_once(c: CatalogClient, worker_id: str | None = None, kinds: list[str] = KINDS,
             cache: Path = DEFAULT_CACHE) -> dict | None:
    """Claim and run one job. Returns the job, or None if the queue is empty.
    `cache` keeps the geometry cache between jobs (one worker per cache dir)."""
    worker_id = worker_id or f"terrella_assets@{socket.gethostname()}"
    job = c.claim(worker_id, kinds)
    if job is None:
        return None
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ids = HANDLERS[job["kind"]](c, job, cache, Path(tmp))
            c.complete(job["id"], "succeeded", ids)
        except JobCancelled:
            pass                                     # user cancelled; catalog already knows
        except Exception as e:                        # report, don't crash the worker loop
            c.complete(job["id"], "failed", error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
    return job
