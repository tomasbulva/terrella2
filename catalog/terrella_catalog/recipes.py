from hashlib import sha256
import json


def canonical_json(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def recipe_hash(body: dict) -> str:
    return sha256(canonical_json(body).encode()).hexdigest()


def normalize_recipe(body: dict) -> dict:
    """Order-insensitive parts are sorted so equal recipes hash equally."""
    out = dict(body)
    out["kit"] = sorted(set(out.get("kit", [])))
    return out
