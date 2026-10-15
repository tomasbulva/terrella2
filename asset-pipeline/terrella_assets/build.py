"""Orchestrates a kit build: generate -> clean -> validate -> export -> ledger.

Output layout (everything the catalog backend needs to ingest):
    <out>/index.json                     all asset manifests (catalog ingest)
    <out>/ledger.jsonl                   append-only cost rows
    <out>/kits/<kit>/palette.png         shared palette atlas
    <out>/kits/<kit>/kit.json            kit manifest (style + piece ids)
    <out>/assets/<asset_id>/piece.glb    the kit piece
    <out>/assets/<asset_id>/manifest.json
    <out>/cache/<geometry_hash>.npz      cleaned geometry (cache)
    <out>/work/<geometry_hash>/          generator intermediates (concept images, raw meshes, logs)

Ids are content addresses:
    geometry_hash = H(generator id + version (+ script hash), kind, params, seed, pivot, height, budget, pipeline version)
    asset_id      = H(geometry_hash, palette_hash)
so identical requests are cache hits and a restyle only re-exports.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, generators
from .cleanup import clean
from .export import load_parts, palette_png, save_parts, sha256, to_single_mesh, validate, write_glb
from .ledger import Ledger, PriceTable
from .spec import ROLES, KitSpec, PieceRequest, load_kit
from .export import GRID, SWATCH_PX


def canonical_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recipe(req: PieceRequest, gen, style) -> dict:
    """Everything that can change the geometry, and nothing that can't (the
    palette colours are deliberately absent, so a restyle is a cache hit)."""
    style_inputs = gen.style_inputs(req, style) if hasattr(gen, "style_inputs") else {"wobble": style.wobble}
    r = {
        "pipeline_version": __version__,
        "generator": gen.id, "generator_version": gen.version,
        "kind": req.kind, "params": req.params, "seed": req.seed, "pivot": req.pivot,
        "target_height_m": req.target_height_m, "budget": asdict(req.budget),
        "style_inputs": style_inputs,
    }
    script = getattr(gen, "script", None)
    if script is not None and Path(script).exists():
        r["script_sha256"] = sha256(Path(script).read_bytes())
    return r


def build_kit(kit_src: str | Path | dict, out: str | Path, prices_path: str | Path, *, user_id: str = "local",
              job_id: str | None = None, budget_usd: float | None = None, only: set[str] | None = None,
              force: bool = False, log=print) -> list[dict]:
    out = Path(out)
    kit: KitSpec = load_kit(kit_src)
    kit_base = None if isinstance(kit_src, dict) else Path(kit_src).parent   # for relative blender scripts
    job_id = job_id or f"job_{uuid.uuid4().hex[:12]}"
    ledger = Ledger(out / "ledger.jsonl", PriceTable.load(prices_path), user_id, job_id, budget_usd)

    palette = palette_png(kit.style)
    palette_hash = sha256(palette)
    kit_dir = out / "kits" / kit.name
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "palette.png").write_bytes(palette)

    manifests = []
    for req in kit.pieces:
        if only and req.name not in only:
            continue
        gen = generators.get(req.generator, kit_base)
        rec = recipe(req, gen, kit.style)
        geometry_hash = canonical_hash(rec)
        asset_id = canonical_hash({"geometry": geometry_hash, "palette": palette_hash})[:20]
        cache = out / "cache" / f"{geometry_hash}.npz"
        work = out / "work" / geometry_hash[:20]
        gen_meta_path = work / "generated.json"

        cached = cache.exists() and gen_meta_path.exists() and not force
        if cached:
            parts = load_parts(cache)
            gen_meta = json.loads(gen_meta_path.read_text())
            rows = []
            log(f"  {req.name:<18} cache hit  ({geometry_hash[:10]})")
        else:
            if not gen.available():
                raise generators.NotConfigured(f"{req.name}: generator {req.generator} is not available here")
            est = ledger.check(gen.estimate(req), req.name)
            if work.exists():
                shutil.rmtree(work)
            work.mkdir(parents=True)
            g = gen.generate(req, kit.style, work)
            parts = clean(g.parts, req)
            save_parts(parts, cache)
            rows = ledger.record(asset_id, g.usage)
            gen_meta = {"provenance": g.provenance, "usage": [asdict(u) for u in g.usage],
                        "estimate_usd": est, "generated_at": _now(), "job_id": job_id, "user_id": user_id}
            gen_meta_path.write_text(json.dumps(gen_meta, indent=2))
            log(f"  {req.name:<18} generated  ${sum(r.usd for r in rows):.4f}")

        mesh = to_single_mesh(parts, palette)
        adir = out / "assets" / asset_id
        adir.mkdir(parents=True, exist_ok=True)
        glb = write_glb(mesh, req.name, adir / "piece.glb")
        v = validate(parts, mesh, req)
        if not v["ok"]:
            log(f"  {req.name:<18} INVALID: {'; '.join(v['issues'])}")

        manifest = {
            "schema": "terrella.asset/1",
            "id": asset_id,
            "name": req.name,
            "slug": req.slug,
            "category": req.category,
            "kind": req.kind,
            "tags": list(req.tags),
            "kit": {"name": kit.name, "version": kit.version},
            "geometry_hash": geometry_hash,
            "palette_hash": palette_hash,
            "recipe": rec,
            "files": {"glb": f"assets/{asset_id}/piece.glb", "glb_sha256": sha256(glb), "glb_bytes": len(glb),
                      "palette": f"kits/{kit.name}/palette.png"},
            "pivot": req.pivot,
            "units": "m", "up": "+Y", "front": "+Z",
            "validation": {"ok": v["ok"], "issues": v["issues"]},
            "stats": v["stats"],
            "provenance": {
                **gen_meta["provenance"],
                "style": {"name": kit.style.name, "source": kit.style.source},
                "generated_at": gen_meta["generated_at"], "generated_by_job": gen_meta["job_id"],
                "generated_for_user": gen_meta["user_id"], "work_dir": f"work/{geometry_hash[:20]}",
            },
            # Cost is attributed to the generation that made the geometry; a
            # cache hit (incl. restyle) adds nothing. Ledger rows are the truth.
            "cost": {"usd": round(sum(_usd(u, ledger.prices) for u in gen_meta["usage"]), 6),
                     "usage": gen_meta["usage"], "price_table": ledger.prices.version, "cache_hit": cached},
        }
        (adir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        manifests.append(manifest)

    _write_kit(kit_dir, kit, palette_hash, manifests)
    _merge_index(out, manifests)
    return manifests


def _usd(u: dict, prices: PriceTable) -> float:
    return prices.cost([generators.Usage(**u)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_kit(kit_dir: Path, kit: KitSpec, palette_hash: str, manifests: list[dict]) -> None:
    (kit_dir / "kit.json").write_text(json.dumps({
        "schema": "terrella.kit/1", "name": kit.name, "version": kit.version,
        "style": asdict(kit.style), "palette_hash": palette_hash,
        "palette_layout": {"grid": GRID, "swatch_px": SWATCH_PX, "roles": list(ROLES)},
        "pieces": {m["name"]: m["id"] for m in manifests},
        "slugs": {m["slug"]: m["id"] for m in manifests},
    }, indent=2))


def _merge_index(out: Path, manifests: list[dict]) -> None:
    path = out / "index.json"
    idx = json.loads(path.read_text()) if path.exists() else {"schema": "terrella.index/1", "assets": {}}
    for m in manifests:
        idx["assets"][m["id"]] = m
    idx["updated_at"] = _now()
    path.write_text(json.dumps(idx, indent=2))
