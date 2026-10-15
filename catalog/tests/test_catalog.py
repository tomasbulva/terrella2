import pytest

from conftest import PROV, make_glb


def test_auth(anon, new_user, client):
    assert client.get("/assets").status_code == 401
    assert anon.get("/assets").status_code == 401
    alice, _ = new_user()
    alice.post("/users", expect=403, json={"name": "mallory"})
    assert alice.get("/users/me", expect=200).json()["name"] == "alice"


def test_asset_versions_and_validation(admin, upload):
    sha = upload(make_glb())
    a1 = admin.post("/assets", expect=201, json={"kind": "kit_piece", "slug": "lamp", "blob_sha256": sha, "provenance": PROV}).json()
    assert a1["reused"] is False
    sha2 = upload(make_glb("v2"))
    a2 = admin.post("/assets", expect=201, json={"kind": "kit_piece", "slug": "lamp", "blob_sha256": sha2, "provenance": PROV}).json()
    assert (a1["version"], a2["version"]) == (1, 2)
    # Same bytes as an older version is a real change (a revert), so it gets a new version.
    a3 = admin.post("/assets", expect=201, json={"kind": "kit_piece", "slug": "lamp", "blob_sha256": sha, "provenance": PROV}).json()
    assert a3["version"] == 3
    assert a1["blob"]["media_type"] == "model/gltf-binary"
    assert a1["url"] == f"https://cdn.test/blobs/{sha}"
    latest = admin.get("/assets", params={"slug": "lamp", "latest": True}).json()
    assert [a["version"] for a in latest] == [3]

    png = upload(b"\x89PNG\r\n\x1a\n1234")
    admin.post("/assets", expect=422, json={"kind": "kit_piece", "slug": "bad", "blob_sha256": png, "provenance": PROV})
    admin.post("/assets", expect=422, json={"kind": "style_spec", "slug": "s", "provenance": PROV})  # no spec
    admin.post("/assets", expect=422, json={"kind": "kit_piece", "slug": "nob", "provenance": PROV})  # no blob
    admin.post("/assets", expect=422, json={"kind": "kit_piece", "slug": "lamp", "blob_sha256": sha})  # no provenance


def test_blob_roundtrip_is_content_addressed(admin, upload, client):
    data = make_glb("same")
    assert upload(data) == upload(data)
    r = client.get(f"/blobs/{upload(data)}")
    assert r.status_code == 200 and r.content == data
    assert "immutable" in r.headers["cache-control"]


def test_lineage(admin, upload):
    seed = admin.post("/assets", expect=201, json={"kind": "seed_image", "slug": "seed", "blob_sha256": upload(b"\xff\xd8\xff..."), "provenance": {"producer": "nano-banana"}}).json()
    spec = admin.post("/assets", expect=201, json={
        "kind": "style_spec", "slug": "spec", "spec": {"kit_family": "f", "palette": ["#fff"]},
        "provenance": {"producer": "gemini-flash", "prompt": "read the mood board"}, "parents": [{"asset_id": seed["id"], "role": "seed"}],
    }).json()
    piece = admin.post("/assets", expect=201, json={
        "kind": "kit_piece", "slug": "p", "blob_sha256": upload(make_glb()), "provenance": PROV,
        "parents": [{"asset_id": spec["id"], "role": "style"}],
    }).json()
    nodes = admin.get(f"/assets/{piece['id']}/lineage", expect=200).json()
    assert [(n["asset"]["id"], n["role"], n["depth"]) for n in nodes] == [(spec["id"], "style", 1), (seed["id"], "seed", 2)]


def test_recipe_is_idempotent_and_order_insensitive(admin, kit):
    body = {
        "generator": {"name": "dutch_houses", "version": "0.3.0"},
        "osm": {"extract_id": "osm:abc"},
        "style_spec_id": kit["spec"]["id"],
        "kit": [kit["window"]["id"], kit["gable"]["id"]],
        "seed": 7,
    }
    r1 = admin.post("/recipes", expect=201, json=body).json()
    r2 = admin.post("/recipes", expect=200, json={**body, "kit": list(reversed(body["kit"]))}).json()
    assert r1["hash"] == r2["hash"] and r1["cached"] is False
    r3 = admin.post("/recipes", expect=201, json={**body, "seed": 8}).json()
    assert r3["hash"] != r1["hash"]
    admin.post("/recipes", expect=422, json={**body, "style_spec_id": kit["window"]["id"]})
    admin.post("/recipes", expect=422, json={**body, "kit": [kit["spec"]["id"]]})
    admin.post("/recipes", expect=422, json={**body, "surprise": 1})


def test_end_to_end_build_publish_manifest_and_costs(admin, worker, new_user, upload, kit, client):
    alice, alice_id = new_user()
    admin.post("/prices", expect=201, json={"provider": "hi3d", "model": "hi3d-v2", "unit": "call", "usd_per_unit": 0.25})
    admin.post("/prices", expect=201, json={"provider": "google", "model": "gemini-flash", "unit": "input_token", "usd_per_unit": 0.0000003})

    # Kit pieces cost something to make (charged to the worker account that made them).
    worker.post("/ledger/usage", expect=201, json={"provider": "hi3d", "model": "hi3d-v2", "unit": "call", "qty": 4, "asset_id": kit["window"]["id"]})

    recipe_body = {"generator": {"name": "dutch_houses", "version": "0.3.0"}, "osm": {"extract_id": "osm:ams-1"},
                   "style_spec_id": kit["spec"]["id"], "kit": [kit["window"]["id"], kit["gable"]["id"], kit["atlas"]["id"]], "seed": 1}
    recipe = alice.post("/recipes", expect=201, json=recipe_body).json()
    # A second recipe shares the window, so its cost is split in two.
    admin.post("/recipes", expect=201, json={**recipe_body, "seed": 2, "kit": [kit["window"]["id"]]})

    job = alice.post("/jobs", expect=201, json={"kind": "diorama.build", "input": {"recipe_hash": recipe["hash"]}, "estimate_usd": 1}).json()
    dup = alice.post("/jobs", expect=200, json={"kind": "diorama.build", "input": {"recipe_hash": recipe["hash"]}}).json()
    assert dup["id"] == job["id"] and dup["deduped"]

    claimed = worker.post("/jobs/claim", expect=200, json={"worker_id": "w1", "kinds": ["diorama.build"]}).json()
    assert claimed["id"] == job["id"] and claimed["status"] == "running"
    assert worker.post("/jobs/claim", json={"worker_id": "w2", "kinds": ["diorama.build"]}).status_code == 204
    worker.post(f"/jobs/{job['id']}/progress", expect=200, json={"stage": "assemble", "progress": 0.5})

    worker.post(f"/jobs/{job['id']}/usage", expect=422, json={"provider": "nobody", "model": "m", "unit": "call", "qty": 1})
    e = worker.post(f"/jobs/{job['id']}/usage", expect=201, json={"provider": "google", "model": "gemini-flash", "unit": "input_token", "qty": 1_000_000}).json()
    assert e["user_id"] == alice_id and e["cost_usd"] == pytest.approx(0.3)

    build = worker.post("/assets", expect=201, json={
        "kind": "diorama_build", "slug": "amsterdam-nl", "blob_sha256": upload(make_glb("build")),
        "recipe_hash": recipe["hash"], "job_id": job["id"],
        "provenance": {"producer": "blender:dutch_houses.py", "model_version": "0.3.0", "seed": 1,
                       "licence": "ODbL-1.0", "attribution": "© OpenStreetMap contributors"},
        "parents": [{"asset_id": kit["atlas"]["id"], "role": "atlas"}, {"asset_id": kit["window"]["id"], "role": "kit"},
                    {"asset_id": kit["gable"]["id"], "role": "kit"}, {"asset_id": kit["spec"]["id"], "role": "style"}],
    }).json()
    done = worker.post(f"/jobs/{job['id']}/complete", expect=200, json={"status": "succeeded", "result_asset_ids": [build["id"]]}).json()
    assert done["progress"] == 1.0

    admin.post("/dioramas", expect=201, json={"slug": "amsterdam-nl", "name": "Amsterdam", "country": "NL", "lat": 52.37, "lon": 4.89})
    admin.post("/dioramas/amsterdam-nl/publish", expect=422, json={"build_id": build["id"]})  # still draft
    v_before = client.get("/catalog/manifest").json()["version"]
    admin.post(f"/assets/{build['id']}/status", expect=200, json={"status": "approved"})
    admin.post("/dioramas/amsterdam-nl/publish", expect=200, json={"build_id": build["id"]})

    m = client.get("/catalog/manifest").json()
    assert m["version"] > v_before
    [d] = m["dioramas"]
    assert d["build"]["asset_id"] == build["id"] and d["recipe_hash"] == recipe["hash"]
    assert {f["role"] for f in d["dependencies"]} == {"atlas", "kit"}  # style_spec has no blob, not shipped
    assert d["attribution"] == ["© OpenStreetMap contributors"]
    changes = client.get("/catalog/changes", params={"since": v_before}).json()
    assert [c["action"] for c in changes] == ["approved", "published"]

    assert alice.post("/recipes", expect=200, json=recipe_body).json()["cached"] is True

    # Costs: build 0.30 own; window 1.00 shared by 2 recipes -> 0.50; gable/atlas/spec cost 0.
    cost = alice.get("/dioramas/amsterdam-nl/cost", expect=200).json()
    assert cost["build_lineage_usd"] == pytest.approx(0.3)
    assert cost["kit_amortised_usd"] == pytest.approx(0.5)
    assert cost["total_usd"] == pytest.approx(0.8)
    assert alice.get(f"/assets/{kit['window']['id']}/cost").json()["direct_usd"] == pytest.approx(1.0)

    by_user = {r["key"]: r["cost_usd"] for r in admin.get("/ledger/summary", params={"group_by": "user"}).json()}
    assert by_user[alice_id] == pytest.approx(0.3)
    alice.get("/ledger/summary", expect=403, params={"user_id": "someone-else"})
    assert [r["cost_usd"] for r in alice.get("/ledger/summary", params={"group_by": "month"}).json()] == [pytest.approx(0.3)]

    near = client.get("/dioramas", params={"lat": 52.3, "lon": 4.8}).json()
    assert near[0]["slug"] == "amsterdam-nl" and 0 < near[0]["distance_km"] < 15


def test_budget_blocks_enqueue(admin, worker, new_user):
    bob, bob_id = new_user("bob", budget=1.0)
    admin.post("/prices", expect=201, json={"provider": "p", "model": "m", "unit": "call", "usd_per_unit": 0.5})
    j1 = bob.post("/jobs", expect=201, json={"kind": "kit_piece.generate", "input": {"n": 1}, "estimate_usd": 0.8}).json()
    r = bob.post("/jobs", json={"kind": "kit_piece.generate", "input": {"n": 2}, "estimate_usd": 0.5})
    assert r.status_code == 402 and r.json()["detail"]["error"] == "budget_exceeded"
    budget = bob.get("/users/me/budget", expect=200).json()
    assert budget["reserved_usd"] == pytest.approx(0.8) and budget["remaining_usd"] == pytest.approx(0.2)

    # Spend replaces reservation; after completion only actual spend counts.
    worker.post("/jobs/claim", expect=200, json={"worker_id": "w", "kinds": ["kit_piece.generate"]})
    worker.post(f"/jobs/{j1['id']}/usage", expect=201, json={"provider": "p", "model": "m", "unit": "call", "qty": 1})
    worker.post(f"/jobs/{j1['id']}/complete", expect=200, json={"status": "succeeded"})
    budget = bob.get("/users/me/budget").json()
    assert budget["spent_this_month_usd"] == pytest.approx(0.5) and budget["reserved_usd"] == 0
    bob.post("/jobs", expect=201, json={"kind": "kit_piece.generate", "input": {"n": 2}, "estimate_usd": 0.5})
    bob.post("/jobs", expect=402, json={"kind": "kit_piece.generate", "input": {"n": 3}, "estimate_usd": 0.01})

    admin.post("/ledger/adjustments", expect=201, json={"user_id": bob_id, "cost_usd": -0.5, "note": "refund"})
    bob.post("/jobs", expect=201, json={"kind": "kit_piece.generate", "input": {"n": 3}, "estimate_usd": 0.4})


def test_cancel_stops_worker(worker, new_user):
    alice, _ = new_user()
    job = alice.post("/jobs", expect=201, json={"kind": "kit_piece.generate", "input": {}}).json()
    worker.post("/jobs/claim", expect=200, json={"worker_id": "w", "kinds": ["kit_piece.generate"]})
    alice.post(f"/jobs/{job['id']}/cancel", expect=200)
    worker.post(f"/jobs/{job['id']}/progress", expect=409, json={"progress": 0.9})
    worker.post(f"/jobs/{job['id']}/complete", expect=409, json={"status": "succeeded"})


def test_users_only_see_their_jobs(new_user):
    alice, _ = new_user("alice")
    bob, _ = new_user("bob")
    job = alice.post("/jobs", expect=201, json={"kind": "a.b", "input": {}}).json()
    bob.get(f"/jobs/{job['id']}", expect=404)
    assert bob.get("/jobs").json() == []


def test_price_versioning(admin, worker):
    from datetime import datetime, timedelta, timezone

    past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    admin.post("/prices", expect=201, json={"provider": "p", "model": "m", "unit": "image", "usd_per_unit": 0.04, "effective_from": past})
    admin.post("/prices", expect=201, json={"provider": "p", "model": "m", "unit": "image", "usd_per_unit": 0.10, "effective_from": future})
    e = worker.post("/ledger/usage", expect=201, json={"provider": "p", "model": "m", "unit": "image", "qty": 10}).json()
    assert e["cost_usd"] == pytest.approx(0.4)


def test_rebuild_reuses_identical_assets(admin, worker, new_user, upload):
    alice, _ = new_user()
    admin.post("/prices", expect=201, json={"provider": "blender", "model": "cpu", "unit": "second", "usd_per_unit": 0.001})
    glb, changed = make_glb("door"), make_glb("door-v2")

    def run_kit_job(blobs):
        job = alice.post("/jobs", expect=201, json={"kind": "kit.build", "input": {}, "force": True}).json()
        worker.post("/jobs/claim", expect=200, json={"worker_id": "w", "kinds": ["kit.build"]})
        worker.post(f"/jobs/{job['id']}/usage", expect=201, json={"provider": "blender", "model": "cpu", "unit": "second", "qty": 100})
        results = []
        for slug, data in blobs.items():
            r = worker.post("/assets", json={"kind": "kit_piece", "slug": slug, "blob_sha256": upload(data),
                                             "job_id": job["id"], "provenance": {"producer": "blender:kit.py"}})
            assert r.status_code in (200, 201), r.text
            results.append(r.json())
        worker.post(f"/jobs/{job['id']}/complete", expect=200,
                    json={"status": "succeeded", "result_asset_ids": [a["id"] for a in results]})
        return job, results

    j1, (door1, lamp1) = run_kit_job({"door": glb, "lamp": make_glb("lamp")})
    j2, (door2, lamp2) = run_kit_job({"door": changed, "lamp": make_glb("lamp")})

    assert lamp2["reused"] and lamp2["id"] == lamp1["id"] and lamp2["version"] == 1 and lamp2["job_id"] == j1["id"]
    assert not door2["reused"] and door2["version"] == 2 and door2["job_id"] == j2["id"]
    # Job 2 spent $0.10 and owns one new asset, so the whole $0.10 lands on door v2; lamp keeps its $0.05.
    assert alice.get(f"/assets/{door2['id']}/cost").json()["direct_usd"] == pytest.approx(0.1)
    assert alice.get(f"/assets/{lamp1['id']}/cost").json()["direct_usd"] == pytest.approx(0.05)
    assert alice.get(f"/jobs/{j2['id']}").json()["result_asset_ids"] == [door2["id"], lamp1["id"]]

    # Opting out mints a new version even for identical bytes.
    r = worker.post("/assets", expect=201, json={"kind": "kit_piece", "slug": "lamp", "blob_sha256": upload(make_glb("lamp")),
                                                 "provenance": {"producer": "x"}, "dedupe": False}).json()
    assert r["version"] == 2
