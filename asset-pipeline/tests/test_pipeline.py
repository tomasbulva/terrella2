import json
import struct
from pathlib import Path

import numpy as np
import pytest

from terrella_assets import generators
from terrella_assets.build import build_kit
from terrella_assets.generators.blender import blender_command
from terrella_assets.ledger import BudgetExceeded, read_rows
from terrella_assets.spec import ROLES

ROOT = Path(__file__).resolve().parents[1]
PRICES = ROOT / "prices.toml"

KIT = """
[kit]
name = "t"
version = "0"
seed = 3

[style]
name = "s"
wobble = {wobble}
[style.palette]
wall = "{wall}"
glass = "#223344"
window_frame = "#eeeeee"
stone = "#999999"
wood = "#335544"
metal = "#222222"
foliage = "#558833"

[[piece]]
name = "win"
kind = "window"
pivot = "wall"
params = {{ shutters = true }}

[[piece]]
name = "lamp"
kind = "street_lamp"

[[piece]]
name = "pot"
kind = "planter"
generator = "ai3d:mock"
target_height_m = 0.8
params = {{ role = "foliage" }}
budget = {{ max_tris = 300 }}
"""


def kit(tmp_path, wall="#884433", wobble=0.015, name="kit.toml"):
    p = tmp_path / name
    p.write_text(KIT.format(wall=wall, wobble=wobble))
    return p


def build(tmp_path, k, **kw):
    return {m["name"]: m for m in build_kit(k, tmp_path / "out", PRICES, log=lambda *_: None, **kw)}


def glb_uvs(path: Path) -> np.ndarray:
    b = path.read_bytes()
    jl = struct.unpack("<I", b[12:16])[0]
    g = json.loads(b[20:20 + jl])
    binary = b[20 + jl + 8:]
    acc = g["accessors"][g["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"]]
    bv = g["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return np.frombuffer(binary[start:start + acc["count"] * 8], dtype="<f4").reshape(-1, 2), g


def test_build_valid_and_ledgered(tmp_path):
    ms = build(tmp_path, kit(tmp_path), user_id="u1")
    assert all(m["validation"]["ok"] for m in ms.values()), {n: m["validation"] for n, m in ms.items()}
    rows = read_rows(tmp_path / "out" / "ledger.jsonl")
    ai = [r for r in rows if r.provider == "mock"]
    assert {r.unit for r in ai} == {"image", "generation"}
    assert all(r.user_id == "u1" and r.artefact_id == ms["pot"]["id"] for r in ai)
    assert ms["pot"]["cost"]["usd"] == pytest.approx(0.34)
    assert ms["pot"]["provenance"]["prompt"].startswith("A single planter")


def test_budgets_and_pivots(tmp_path):
    ms = build(tmp_path, kit(tmp_path))
    pot = ms["pot"]
    assert pot["stats"]["tris"] <= 300                       # decimated from ~5k
    assert pot["stats"]["extent_m"][1] == pytest.approx(0.8)  # scale-normalised
    (lo, hi) = pot["stats"]["bounds_m"]
    assert lo[1] == pytest.approx(0) and lo[0] == pytest.approx(-hi[0], abs=1e-3)   # base pivot
    wlo = ms["win"]["stats"]["bounds_m"][0]
    assert wlo[1] == pytest.approx(0, abs=1e-4) and wlo[2] == pytest.approx(0, abs=1e-4)  # wall pivot


def test_rebuild_is_cache_hit(tmp_path):
    k = kit(tmp_path)
    a = build(tmp_path, k)
    n_rows = len(read_rows(tmp_path / "out" / "ledger.jsonl"))
    b = build(tmp_path, k)
    assert {n: m["id"] for n, m in a.items()} == {n: m["id"] for n, m in b.items()}
    assert all(m["cost"]["cache_hit"] for m in b.values())
    assert len(read_rows(tmp_path / "out" / "ledger.jsonl")) == n_rows
    assert a["win"]["files"]["glb_sha256"] == b["win"]["files"]["glb_sha256"]


def test_restyle_reuses_procedural_geometry_but_not_ai(tmp_path):
    a = build(tmp_path, kit(tmp_path))
    n_rows = len(read_rows(tmp_path / "out" / "ledger.jsonl"))
    b = build(tmp_path, kit(tmp_path, wall="#3355aa", name="kit2.toml"))
    assert b["win"]["geometry_hash"] == a["win"]["geometry_hash"]
    assert b["win"]["id"] != a["win"]["id"]                    # new palette -> new asset id
    assert b["win"]["cost"]["cache_hit"]
    assert b["pot"]["geometry_hash"] != a["pot"]["geometry_hash"]   # prompt changed -> regenerate
    new = read_rows(tmp_path / "out" / "ledger.jsonl")[n_rows:]
    assert {r.artefact_id for r in new if r.usd > 0} == {b["pot"]["id"]}


def test_wobble_changes_geometry(tmp_path):
    a = build(tmp_path, kit(tmp_path))
    b = build(tmp_path, kit(tmp_path, wobble=0.04, name="kit2.toml"))
    assert a["win"]["geometry_hash"] != b["win"]["geometry_hash"]


def test_budget_enforced_before_generation(tmp_path):
    with pytest.raises(BudgetExceeded):
        build(tmp_path, kit(tmp_path), budget_usd=0.10)
    rows = read_rows(tmp_path / "out" / "ledger.jsonl")
    assert not [r for r in rows if r.provider == "mock"]


def test_uv_cells_match_roles(tmp_path):
    ms = build(tmp_path, kit(tmp_path))
    uv, g = glb_uvs(tmp_path / "out" / ms["lamp"]["files"]["glb"])
    cells = {int(u * 4) + 4 * int(v * 4) for u, v in uv}       # glTF uv: top-left origin
    assert cells == {ROLES.index("metal"), ROLES.index("glass")}
    assert len(g["materials"]) == 1 and len(g["meshes"][0]["primitives"]) == 1


def test_real_ai_providers_refuse(tmp_path, monkeypatch):
    monkeypatch.setenv("HI3D_API_KEY", "x")
    gen = generators.get("ai3d:hi3d")
    assert not gen.available()
    with pytest.raises(generators.NotConfigured):
        gen.mesh.generate(Path("x.png"), tmp_path / "o.glb", 0)


@pytest.mark.skipif(blender_command() is None, reason="no blender / bpy")
def test_blender_generator(tmp_path):
    p = tmp_path / "b.toml"
    p.write_text(KIT.format(wall="#884433", wobble=0.0).split("[[piece]]")[0] + """
[[piece]]
name = "lantern"
kind = "lantern"
generator = "blender"
""")
    ms = build(tmp_path, p)
    m = ms["lantern"]
    assert m["validation"]["ok"], m["validation"]
    assert set(m["stats"]["roles"]) == {"metal", "glass"}
    assert m["stats"]["extent_m"][1] > 3.0


def test_tangents_and_uv2_are_usable(tmp_path):
    """Palette UVs are constant per face, so engines can't derive tangents
    from UV0 (Godot gives NaN and normal-mapped faces go white). Every GLB
    ships explicit tangents consistent with a varying TEXCOORD_1."""
    from terrella_assets.gltf import read_piece
    ms = build(tmp_path, kit(tmp_path))
    for m in ms.values():
        pm = read_piece((tmp_path / "out" / m["files"]["glb"]).read_bytes())
        t, n = pm.tangents, pm.normals / np.linalg.norm(pm.normals, axis=1, keepdims=True)
        assert np.isfinite(t).all() and np.isfinite(pm.uv2).all()
        assert np.allclose(np.linalg.norm(t[:, :3], axis=1), 1, atol=1e-4)
        assert np.abs(np.einsum("ij,ij->i", t[:, :3], n)).max() < 1e-3
        assert set(np.unique(t[:, 3])) <= {-1.0, 1.0}
        tri = pm.indices.reshape(-1, 3)
        assert (np.ptp(pm.uv2[tri], axis=1).max(axis=1) > 0).mean() > 0.95   # UV2 varies across faces
