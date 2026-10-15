# puzzles/

Engine-free treasure-hunt puzzle and collectible rules for Terrella v2. Design: [SPEC.md](SPEC.md).

```bash
cd puzzles
python3 -m unittest discover -s tests -t .                                  # Python reference (3.11+, no deps)
godot --headless --path godot --script res://tests/run_vectors.gd           # GDScript checker conformance
python3 tools/make_check_vectors.py                                         # after changing generation or checking
```

```python
from terrella_puzzles import Scene, WorldContext, generate, validate, check, answer_attempt, load_catalog, pick_rewards
inst = generate(scene, ctx, slot="daily")      # deterministic per (recipe_hash, date, slot)
assert validate(inst, scene) == []
check(inst, {"select": "house_03_w00"})       # {"solved": ..., "progress": ..., "feedback": ...}
pick_rewards(inst, load_catalog(), inventory, user_id, granted_at)
```
