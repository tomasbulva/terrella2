import struct

import pytest
from fastapi.testclient import TestClient

from terrella_catalog.app import create_app
from terrella_catalog.auth import hash_token
from terrella_catalog.config import Settings
from terrella_catalog.models import User


def make_glb(tag: str = "x") -> bytes:
    """Smallest valid-looking GLB: header + one JSON chunk."""
    js = ('{"asset":{"version":"2.0"},"extras":{"t":"%s"}}' % tag).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


class Api:
    def __init__(self, client: TestClient, token: str):
        self.c, self.h = client, {"Authorization": f"Bearer {token}"}

    def __getattr__(self, method):
        def call(path, expect=None, **kw):
            r = getattr(self.c, method)(path, headers={**self.h, **kw.pop("headers", {})}, **kw)
            if expect is not None:
                assert r.status_code == expect, r.text
            return r

        return call


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_url=f"sqlite:///{tmp_path/'t.db'}", blob_dir=tmp_path / "blobs", public_base_url="https://cdn.test"))


@pytest.fixture
def client(app):
    return TestClient(app)


def _bootstrap(app, name, role, budget=None):
    token = f"tok-{name}"
    with app.state.db.sessionmaker() as s:
        s.add(User(name=name, role=role, token_hash=hash_token(token), monthly_budget_nanos=budget))
        s.commit()
    return token


@pytest.fixture
def admin(app, client):
    return Api(client, _bootstrap(app, "admin", "admin"))


@pytest.fixture
def worker(app, client):
    return Api(client, _bootstrap(app, "worker", "worker"))


@pytest.fixture
def anon(client):
    return Api(client, "nope")


@pytest.fixture
def new_user(admin, client):
    def make(name="alice", budget=None):
        body = admin.post("/users", expect=201, json={"name": name, "monthly_budget_usd": budget}).json()
        return Api(client, body["token"]), body["id"]

    return make


@pytest.fixture
def upload(admin):
    def put(data: bytes, ctype="application/octet-stream"):
        return admin.put("/blobs", expect=201, content=data, headers={"content-type": ctype}).json()["sha256"]

    return put


PROV = {"producer": "test", "model": "unit", "prompt": "a cozy thing"}


@pytest.fixture
def kit(admin, upload):
    """A style spec plus two kit pieces and an atlas, all approved."""

    def asset(kind, slug, **extra):
        a = admin.post("/assets", expect=201, json={"kind": kind, "slug": slug, "provenance": PROV, **extra}).json()
        admin.post(f"/assets/{a['id']}/status", expect=200, json={"status": "approved"})
        return a

    spec = asset("style_spec", "amsterdam-canal", spec={"kit_family": "nl-canal", "palette": ["#7a3b2e", "#f2e6d0"]})
    window = asset("kit_piece", "nl-canal.window.sash", blob_sha256=upload(make_glb("w")), style_family="nl-canal", category="window")
    gable = asset("kit_piece", "nl-canal.gable.step", blob_sha256=upload(make_glb("g")), style_family="nl-canal", category="gable")
    atlas = asset("atlas", "nl-canal.atlas", blob_sha256=upload(b"\x89PNG\r\n\x1a\n" + b"0" * 32), style_family="nl-canal")
    return {"spec": spec, "window": window, "gable": gable, "atlas": atlas}
