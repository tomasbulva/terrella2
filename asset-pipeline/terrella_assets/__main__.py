"""CLI.

    python -m terrella_assets build kits/dutch_canal.toml --out out
    python -m terrella_assets build kits/dutch_canal.toml --only window_tall,tree_lime --budget-usd 0.5
    python -m terrella_assets ledger out --by user|artefact|provider|job
    python -m terrella_assets preview out          # http://localhost:8765/preview/
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
from collections import defaultdict
from pathlib import Path

from .build import build_kit
from .ledger import BudgetExceeded, read_rows

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="terrella_assets")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build a kit")
    b.add_argument("kit")
    b.add_argument("--out", default="out")
    b.add_argument("--prices", default=str(ROOT / "prices.toml"))
    b.add_argument("--user", default="local")
    b.add_argument("--job")
    b.add_argument("--budget-usd", type=float)
    b.add_argument("--only", help="comma-separated piece names")
    b.add_argument("--force", action="store_true", help="ignore the geometry cache")

    l = sub.add_parser("ledger", help="summarise ledger.jsonl")
    l.add_argument("out")
    l.add_argument("--by", default="artefact_id", choices=["user", "artefact", "provider", "job", "model"])

    d = sub.add_parser("diorama", help="assemble a diorama (glb + puzzle_scene.json) from a built kit")
    d.add_argument("--out", default="out")
    d.add_argument("--kit", default="nl_canal")
    d.add_argument("--id", default="dio_nl_synthetic_canal", help="diorama id")
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--houses", type=int, default=6)
    d.add_argument("--boats", type=int, default=2)

    w = sub.add_parser("worker", help="claim and run catalog jobs (kit.build, diorama.build)")
    w.add_argument("--catalog", required=True, help="catalog base URL")
    w.add_argument("--token", required=True, help="worker token")
    w.add_argument("--cache", default=str(Path.home() / ".cache" / "terrella_assets"))
    w.add_argument("--once", action="store_true", help="run one job (or none) and exit")
    w.add_argument("--poll", type=float, default=5.0, help="seconds between empty polls")

    sp = sub.add_parser("sync-prices", help="push prices.toml rows the catalog is missing (admin token)")
    sp.add_argument("--catalog", required=True)
    sp.add_argument("--token", required=True)
    sp.add_argument("--prices", default=str(ROOT / "prices.toml"))

    p = sub.add_parser("preview", help="serve the web preview over an output dir")
    p.add_argument("out")
    p.add_argument("--port", type=int, default=8765)

    a = ap.parse_args(argv)
    if a.cmd == "build":
        print(f"building {a.kit} -> {a.out}")
        try:
            ms = build_kit(a.kit, a.out, a.prices, user_id=a.user, job_id=a.job, budget_usd=a.budget_usd,
                           only=set(a.only.split(",")) if a.only else None, force=a.force)
        except BudgetExceeded as e:
            print(f"refused: {e}", file=sys.stderr)
            return 2
        bad = [m["name"] for m in ms if not m["validation"]["ok"]]
        print(f"{len(ms)} pieces, {sum(m['stats']['tris'] for m in ms)} tris total, "
              f"{len(bad)} invalid{': ' + ', '.join(bad) if bad else ''}")
        return 1 if bad else 0

    if a.cmd == "diorama":
        from .diorama import LAYOUT_VERSION, KitView, build_diorama
        out = Path(a.out)
        kit = KitView.from_out(out, a.kit)
        kit_json = json.loads((out / "kits" / a.kit / "kit.json").read_text())
        ids = kit_json["slugs"]
        recipe = {"generator": {"name": "canal_street", "version": LAYOUT_VERSION},
                  "osm": {"extract_id": "synthetic"},          # no OSM yet: seeded layout
                  "style_spec_id": f"local:{kit_json['palette_hash'][:20]}",
                  "kit": sorted(ids.values()), "seed": a.seed,
                  "params": {"houses": a.houses, "boats": a.boats}}
        m = build_diorama(kit, diorama_id=a.id, recipe=recipe, out=out, kit_asset_ids=ids)
        print(json.dumps({k: m[k] for k in ("recipe_hash", "files", "stats")}, indent=2))
        _merge_dioramas(out, m)
        return 0

    if a.cmd == "worker":
        import time
        from .catalog_client import CatalogClient
        from .worker import run_once
        c = CatalogClient(a.catalog, a.token)
        while True:
            job = run_once(c, cache=Path(a.cache))
            if job:
                print(f"{job['kind']} {job['id']} done")
            if a.once:
                return 0
            if job is None:
                time.sleep(a.poll)

    if a.cmd == "sync-prices":
        from .catalog_client import CatalogClient
        from .ledger import sync_prices
        for line in sync_prices(CatalogClient(a.catalog, a.token), Path(a.prices)):
            print(line)
        return 0

    if a.cmd == "ledger":
        key = {"user": "user_id", "artefact": "artefact_id", "job": "job_id"}.get(a.by, a.by)
        totals: dict[str, float] = defaultdict(float)
        for r in read_rows(Path(a.out) / "ledger.jsonl"):
            totals[getattr(r, key)] += r.usd
        for k, v in sorted(totals.items(), key=lambda kv: -kv[1]):
            print(f"{v:10.4f}  {k}")
        print(f"{sum(totals.values()):10.4f}  TOTAL")
        return 0

    if a.cmd == "preview":
        # Serve terrella-v2/ so the page can also read ../puzzles/data/context_rules.json.
        import os
        root = ROOT.parent
        out = Path(a.out).resolve()
        if not out.is_relative_to(root):
            print(f"the out dir must be inside {root}", file=sys.stderr)
            return 2
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
        page = (ROOT / "preview").relative_to(root).as_posix()
        print(f"http://localhost:{a.port}/{page}/?out={os.path.relpath(out, ROOT / 'preview')}")
        http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler).serve_forever()
    return 0


def _merge_dioramas(out: Path, m: dict) -> None:
    path = out / "index.json"
    idx = json.loads(path.read_text())
    idx.setdefault("dioramas", {})[m["diorama_id"]] = m
    path.write_text(json.dumps(idx, indent=2))


if __name__ == "__main__":
    sys.exit(main())
