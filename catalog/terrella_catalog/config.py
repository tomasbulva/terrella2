from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    blob_dir: Path
    public_base_url: str  # prefix for blob URLs in the manifest; empty = relative

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("TERRELLA_DATA_DIR", "./data"))
        return cls(
            database_url=os.environ.get("TERRELLA_DATABASE_URL", f"sqlite:///{data_dir / 'catalog.db'}"),
            blob_dir=Path(os.environ.get("TERRELLA_BLOB_DIR", data_dir / "blobs")),
            public_base_url=os.environ.get("TERRELLA_PUBLIC_BASE_URL", "").rstrip("/"),
        )
