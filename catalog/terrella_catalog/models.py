"""Relational model.

Money is stored as integer nano-USD (1e-9 USD). Token prices are fractions of a
micro-dollar, and integers keep sums exact on both SQLite and Postgres.
"""
from datetime import datetime, timezone
import secrets

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NANOS_PER_USD = 1_000_000_000

ASSET_KINDS = (
    "kit_piece",  # reusable glTF piece: window, gable, lamp, boat...
    "material",  # tileable surface: brick, roof tiles, cobbles
    "atlas",  # packed texture atlas shared by a kit, AO baked in
    "seed_image",  # mood-board image a style spec is read from
    "style_spec",  # palette, gable types, roof colours... (JSON in `spec`)
    "diorama_build",  # generator output for one recipe (glTF)
    "preview",  # renders or a web export used for review
)
ASSET_STATUSES = ("draft", "approved", "rejected", "deprecated")
JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
OPEN_JOB_STATUSES = ("queued", "running")
ROLES = ("admin", "worker", "user")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("usr"))
    name: Mapped[str] = mapped_column(String(120), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="user")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # None = unlimited. Budget resets on the first of each UTC month.
    monthly_budget_nanos: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Blob(Base):
    """Content-addressed file. Many assets may point at the same bytes."""

    __tablename__ = "blobs"
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Asset(Base):
    """One immutable version of something in the catalog.

    (kind, slug, version) is unique; a new upload under the same slug gets the
    next version. Every asset carries provenance and its parent assets.
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("kind", "slug", "version"),
        Index("ix_assets_recipe", "recipe_hash"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ast"))
    kind: Mapped[str] = mapped_column(String(32))
    slug: Mapped[str] = mapped_column(String(160))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    style_family: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. "nl-canal"
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. "window"
    blob_sha256: Mapped[str | None] = mapped_column(ForeignKey("blobs.sha256"), nullable=True)
    spec: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # style_spec body
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # bounds, sockets, lod, tris...
    tags: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[dict] = mapped_column(JSON)
    recipe_hash: Mapped[str | None] = mapped_column(ForeignKey("recipes.hash"), nullable=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    blob: Mapped[Blob | None] = relationship()
    parents: Mapped[list["AssetParent"]] = relationship(
        foreign_keys="AssetParent.asset_id", cascade="all, delete-orphan", lazy="selectin"
    )


class AssetParent(Base):
    __tablename__ = "asset_parents"
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("assets.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(40), default="input")  # seed, source_mesh, atlas, kit...


class Recipe(Base):
    """A diorama as data: OSM extract + style spec + pinned kit + generator + seed.

    The primary key is the SHA-256 of the canonical JSON body, so the same
    recipe always maps to the same build and rebuilds are cache hits.
    """

    __tablename__ = "recipes"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    body: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Diorama(Base):
    """A place clients can show. Points at its published build."""

    __tablename__ = "dioramas"
    slug: Mapped[str] = mapped_column(String(160), primary_key=True)  # "amsterdam-nl"
    name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    published_build_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_kind", "status", "kind"), Index("ix_jobs_dedupe", "dedupe_key"))
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("job"))
    kind: Mapped[str] = mapped_column(String(80))  # "kit_piece.generate", "diorama.build"...
    status: Mapped[str] = mapped_column(String(16), default="queued")
    stage: Mapped[str | None] = mapped_column(String(80), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    input: Mapped[dict] = mapped_column(JSON)
    dedupe_key: Mapped[str] = mapped_column(String(64))
    estimate_nanos: Mapped[int] = mapped_column(BigInteger, default=0)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))  # who pays
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result_asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Price(Base):
    """Versioned price list. The newest row with effective_from <= now wins."""

    __tablename__ = "prices"
    __table_args__ = (Index("ix_prices_lookup", "provider", "model", "unit", "effective_from"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(80))  # "google", "hi3d", "anthropic"
    model: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(40))  # "input_token", "image", "gpu_second", "call"
    nanos_per_unit: Mapped[int] = mapped_column(BigInteger)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class LedgerEntry(Base):
    """Append-only. Corrections are new rows with negative cost, never edits."""

    __tablename__ = "ledger"
    __table_args__ = (
        Index("ix_ledger_user_ts", "user_id", "ts"),
        Index("ix_ledger_job", "job_id"),
        Index("ix_ledger_asset", "asset_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(40))
    qty: Mapped[float] = mapped_column(Float)
    price_id: Mapped[int | None] = mapped_column(ForeignKey("prices.id"), nullable=True)
    cost_nanos: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(16), default="usage")  # usage | adjustment
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class CatalogEvent(Base):
    """Monotonic change log. The manifest version is the highest seq."""

    __tablename__ = "catalog_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    entity: Mapped[str] = mapped_column(String(32))  # "asset" | "diorama"
    entity_id: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(32))  # approved, deprecated, published, unpublished
