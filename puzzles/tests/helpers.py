import json
from pathlib import Path

from terrella_puzzles import Scene, WorldContext

ROOT = Path(__file__).resolve().parent.parent


def scene_dict() -> dict:
    return json.loads((ROOT / "fixtures/scenes/amsterdam_canal.json").read_text())


def scene() -> Scene:
    return Scene.from_dict(scene_dict())


def contexts() -> dict[str, WorldContext]:
    raw = json.loads((ROOT / "fixtures/contexts.json").read_text())
    return {k: WorldContext.from_dict(v) for k, v in raw.items()}
