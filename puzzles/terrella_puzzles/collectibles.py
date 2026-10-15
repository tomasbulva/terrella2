"""Collectible catalog, eligibility and reward selection.

Rewards are picked at grant time (they depend on the player's inventory), not
at generation time. Selection is deterministic per (puzzle, user), so a retried
grant request returns the same collectible and the grant id is idempotent.
"""
from __future__ import annotations

import json
from pathlib import Path

from .rng import Rng, derive_seed

DATA = Path(__file__).resolve().parent.parent / "data"
CATEGORIES = ("trinket", "charm", "postcard", "seasonal", "stamp", "keepsake")
RARITY_WEIGHT = {"common": 60, "uncommon": 25, "rare": 10, "legendary": 5}
VARIANT_AXES = ("season", "weather", "phase")


def load_catalog(path: str | Path | None = None) -> list[dict]:
    defs = json.loads(Path(path or DATA / "collectibles.json").read_text())["collectibles"]
    ids = [d["id"] for d in defs]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate collectible ids")
    for d in defs:
        if d["category"] not in CATEGORIES:
            raise ValueError(f"{d['id']}: unknown category {d['category']}")
        if d["rarity"] not in RARITY_WEIGHT:
            raise ValueError(f"{d['id']}: unknown rarity {d['rarity']}")
        if d.get("variant_axis") not in (None, *VARIANT_AXES):
            raise ValueError(f"{d['id']}: unknown variant axis")
    return defs


def eligible(defn: dict, tags: set[str]) -> bool:
    e = defn.get("eligibility", {})
    if not set(e.get("all", [])) <= tags:
        return False
    if e.get("any") and not set(e["any"]) & tags:
        return False
    if set(e.get("none", [])) & tags:
        return False
    return True


def _variant(defn: dict, ctx: dict) -> str | None:
    axis = defn.get("variant_axis")
    return f"{axis}:{ctx[axis]}" if axis else None


def pick_rewards(instance: dict, catalog: list[dict], inventory: dict[str, int],
                 user_id: str, granted_at: str) -> list[dict]:
    """Return the grants for solving `instance`: one collectible, plus the place stamp on a first solve here.

    `inventory` maps collectible id -> count owned. Stamps are not in the catalog;
    they are minted per diorama as `stamp:<diorama_id>` and drawn by the client
    from the diorama's style spec.
    """
    tags = set(instance["reward_tags"])
    rng = Rng(derive_seed(instance["id"], user_id))
    pool = [d for d in catalog if d["category"] != "stamp" and eligible(d, tags)]
    if not pool:
        raise ValueError("catalog has no eligible collectible; it must contain a catch-all common")
    fresh = [d for d in pool if inventory.get(d["id"], 0) == 0]
    draw_from = fresh or pool
    draw_from = sorted(draw_from, key=lambda d: d["id"])
    pick = rng.weighted(draw_from, [RARITY_WEIGHT[d["rarity"]] for d in draw_from])
    ctx = instance["context"]
    base = {
        "user_id": user_id,
        "puzzle_id": instance["id"],
        "slot": instance["slot"],
        "diorama_id": instance["diorama"]["id"],
        "geocell": ctx.get("geocell", ""),
        "context_tags": sorted(tags),
        "granted_at": granted_at,
    }
    grants = [{
        **base,
        "grant_id": f"gr_{derive_seed(user_id, instance['id'], pick['id']):08x}",
        "collectible_id": pick["id"],
        "variant": _variant(pick, ctx),
        "duplicate": not fresh,
        "count_after": inventory.get(pick["id"], 0) + 1,
    }]
    stamp = f"stamp:{instance['diorama']['id']}"
    if inventory.get(stamp, 0) == 0:
        grants.append({
            **base,
            "grant_id": f"gr_{derive_seed(user_id, instance['id'], stamp):08x}",
            "collectible_id": stamp,
            "variant": f"season:{ctx['season']}",
            "duplicate": False,
            "count_after": 1,
        })
    return grants
