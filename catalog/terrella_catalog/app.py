from fastapi import FastAPI

from .api import assets, dioramas, jobs, ledger, users
from .config import Settings
from .db import Database
from .storage import BlobStore


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(
        title="Terrella catalog",
        version="0.1.0",
        description="Kit pieces, style specs, diorama recipes, generation jobs and a per-user cost ledger. "
        "Engine-agnostic: shipped geometry is glTF binary (.glb).",
    )
    app.state.settings = settings
    app.state.db = Database(settings.database_url)
    app.state.blobs = BlobStore(settings.blob_dir)
    for r in (users.router, assets.router, dioramas.router, jobs.router, ledger.router):
        app.include_router(r)

    @app.get("/health", tags=["meta"])
    def health():
        return {"ok": True}

    return app
