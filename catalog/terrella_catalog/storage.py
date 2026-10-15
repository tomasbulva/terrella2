"""Content-addressed blob store on the local filesystem.

The interface is put/open/exists by SHA-256, so an S3/R2 backend can replace it
without touching the API layer.
"""
from hashlib import sha256
from pathlib import Path
import os
import tempfile


class BlobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest

    def put(self, data: bytes) -> str:
        digest = sha256(data).hexdigest()
        dest = self.path(digest)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=dest.parent)
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
        return digest

    def exists(self, digest: str) -> bool:
        return self.path(digest).exists()


def sniff_media_type(data: bytes, declared: str | None) -> str:
    """Trust magic bytes over the client for the formats we care about."""
    if data[:4] == b"glTF":
        return "model/gltf-binary"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:12] == b"\xabKTX 20\xbb\r\n\x1a\n":
        return "image/ktx2"
    return declared or "application/octet-stream"
