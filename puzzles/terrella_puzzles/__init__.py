"""Terrella puzzle and collectible rules. Engine-free, stdlib only.

Entry points:
  generate(scene, ctx, slot=..., tier=..., ptype=...) -> puzzle instance (dict)
  validate(instance, scene) -> list of problems (empty means valid)
  check(instance, attempt) -> {"solved", "progress", "feedback"}
  pick_rewards(instance, catalog, inventory, user_id, granted_at) -> list of grants
"""
from .check import check
from .collectibles import load_catalog, pick_rewards
from .generate import NoPuzzle, generate
from .model import InputError, Scene, WorldContext
from .validate import answer_attempt, validate

__all__ = [
    "InputError", "NoPuzzle", "Scene", "WorldContext",
    "answer_attempt", "check", "generate", "load_catalog", "pick_rewards", "validate",
]
