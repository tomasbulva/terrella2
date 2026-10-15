"""Thin client for the terrella-catalog API (terrella-v2/catalog/openapi.json).

Only the calls the pipeline worker needs. `http` is any httpx.Client-like
object; tests pass the catalog's FastAPI TestClient so the contract is
exercised in-process without a server.
"""
from __future__ import annotations

from typing import Any


class CatalogError(RuntimeError):
    def __init__(self, status: int, body: str, what: str):
        super().__init__(f"{what}: HTTP {status}: {body[:300]}")
        self.status = status


class JobCancelled(RuntimeError):
    pass


class CatalogClient:
    def __init__(self, base_url: str = "", token: str = "", http: Any = None):
        if http is None:
            import httpx
            http = httpx.Client(base_url=base_url, timeout=60)
        self.http = http
        self.h = {"Authorization": f"Bearer {token}"} if token else {}

    def _req(self, method: str, path: str, what: str, ok=(200, 201), **kw):
        r = self.http.request(method, path, headers={**self.h, **kw.pop("headers", {})}, **kw)
        if r.status_code not in ok:
            raise CatalogError(r.status_code, r.text, what)
        return r

    # ---- jobs
    def claim(self, worker_id: str, kinds: list[str]) -> dict | None:
        r = self._req("POST", "/jobs/claim", "claim", ok=(200, 204), json={"worker_id": worker_id, "kinds": kinds})
        return None if r.status_code == 204 or not r.content or r.json() is None else r.json()

    def progress(self, job_id: str, stage: str, progress: float | None = None) -> None:
        r = self.http.request("POST", f"/jobs/{job_id}/progress", headers=self.h,
                              json={"stage": stage, "progress": progress})
        if r.status_code == 409:
            raise JobCancelled(job_id)
        if r.status_code != 200:
            raise CatalogError(r.status_code, r.text, "progress")

    def usage(self, job_id: str, provider: str, model: str, unit: str, qty: float,
              asset_id: str | None = None, cost_usd: float | None = None, note: str | None = None) -> dict:
        body = {"provider": provider, "model": model, "unit": unit, "qty": qty, "asset_id": asset_id,
                "cost_usd": cost_usd, "note": note}
        return self._req("POST", f"/jobs/{job_id}/usage", "usage",
                         json={k: v for k, v in body.items() if v is not None}).json()

    def complete(self, job_id: str, status: str, result_asset_ids: list[str] = (), error: str | None = None) -> dict:
        return self._req("POST", f"/jobs/{job_id}/complete", "complete",
                         json={"status": status, "result_asset_ids": list(result_asset_ids), "error": error}).json()

    # ---- blobs and assets
    def put_blob(self, data: bytes, content_type: str = "application/octet-stream") -> str:
        return self._req("PUT", "/blobs", "put_blob", content=data, headers={"Content-Type": content_type}).json()["sha256"]

    def get_blob(self, sha: str) -> bytes:
        return self._req("GET", f"/blobs/{sha}", "get_blob").content

    def create_asset(self, body: dict) -> dict:
        return self._req("POST", "/assets", "create_asset", json=body).json()

    def get_asset(self, asset_id: str) -> dict:
        return self._req("GET", f"/assets/{asset_id}", "get_asset").json()

    def get_recipe(self, h: str) -> dict:
        return self._req("GET", f"/recipes/{h}", "get_recipe").json()

    # ---- prices (admin)
    def prices(self) -> list[dict]:
        return self._req("GET", "/prices", "prices").json()

    def add_price(self, provider: str, model: str, unit: str, usd_per_unit: float, note: str | None = None) -> dict:
        return self._req("POST", "/prices", "add_price", json={
            "provider": provider, "model": model, "unit": unit, "usd_per_unit": usd_per_unit, "note": note}).json()
