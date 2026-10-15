"""API request/response shapes. Money is exposed as float USD; storage is nano-USD."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import NANOS_PER_USD

AssetKind = Literal["kit_piece", "material", "atlas", "seed_image", "style_spec", "diorama_build", "preview"]
AssetStatus = Literal["draft", "approved", "rejected", "deprecated"]
Role = Literal["admin", "worker", "user"]


def usd(nanos: int | None) -> float | None:
    return None if nanos is None else round(nanos / NANOS_PER_USD, 9)


def nanos(usd_value: float | None) -> int | None:
    return None if usd_value is None else round(usd_value * NANOS_PER_USD)


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- users ----------
class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Role = "user"
    monthly_budget_usd: float | None = Field(default=None, ge=0)


class UserOut(BaseModel):
    id: str
    name: str
    role: Role
    monthly_budget_usd: float | None


class UserCreated(UserOut):
    token: str = Field(description="Shown once. Store it; only its hash is kept.")


class BudgetOut(BaseModel):
    monthly_budget_usd: float | None
    spent_this_month_usd: float
    reserved_usd: float = Field(description="Estimates of this user's queued and running jobs")
    remaining_usd: float | None


# ---------- provenance / assets ----------
class Provenance(BaseModel):
    """Where an asset came from. Required on every asset.

    `producer` is the tool or model family ("hi3d", "nano-banana", "blender:dutch_houses.py",
    "human"). Unknown keys are kept, so pipelines can add what they need.
    """

    model_config = ConfigDict(extra="allow")
    producer: str
    model: str | None = None
    model_version: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    params: dict[str, Any] = {}
    inputs: list[str] = Field(default=[], description="External inputs: URLs, OSM ids, Wikipedia pages")
    licence: str | None = Field(default=None, description="e.g. CC0-1.0, ODbL-1.0 for OSM-derived data")
    attribution: str | None = None


class ParentRef(BaseModel):
    asset_id: str
    role: str = "input"


class StyleSpecBody(BaseModel):
    """What the generator consumes. A hallucination here can only produce a wrong colour."""

    model_config = ConfigDict(extra="allow")
    kit_family: str = Field(description="Which kit pieces this style draws from, e.g. 'nl-canal'")
    palette: list[str] = Field(min_length=1, description="Hex colours, most dominant first")
    roof_colors: list[str] = []
    gable_types: list[str] = []
    tree_species: list[str] = []
    props: list[str] = []
    water_style: str | None = None
    notes: str | None = None


class AssetCreate(BaseModel):
    kind: AssetKind
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,159}$")
    blob_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    style_family: str | None = None
    category: str | None = None
    spec: StyleSpecBody | None = None
    meta: dict[str, Any] = {}
    tags: list[str] = []
    provenance: Provenance
    parents: list[ParentRef] = []
    recipe_hash: str | None = None
    job_id: str | None = None
    dedupe: bool = Field(
        default=True,
        description="If the latest version of (kind, slug) has the same blob and spec, return it (200, reused=true) "
        "instead of minting a new version. The existing asset's provenance and parents are kept.",
    )


class AssetStatusUpdate(BaseModel):
    status: AssetStatus
    reason: str | None = None


class BlobOut(ORM):
    sha256: str
    size: int
    media_type: str


class AssetOut(ORM):
    id: str
    kind: AssetKind
    slug: str
    version: int
    status: AssetStatus
    style_family: str | None
    category: str | None
    blob: BlobOut | None
    url: str | None = None
    spec: dict | None
    meta: dict
    tags: list[str]
    provenance: dict
    parents: list[ParentRef]
    recipe_hash: str | None
    job_id: str | None
    created_by: str
    created_at: datetime
    reused: bool = Field(default=False, description="True when POST /assets returned an existing identical asset")


class LineageNode(BaseModel):
    asset: AssetOut
    role: str
    depth: int


# ---------- recipes / dioramas ----------
class GeneratorRef(BaseModel):
    name: str
    version: str


class OsmRef(BaseModel):
    extract_id: str = Field(description="Stable id of the OSM extract, e.g. a hash of the Overpass query result")
    bbox: tuple[float, float, float, float] | None = Field(default=None, description="min_lon, min_lat, max_lon, max_lat")


class RecipeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generator: GeneratorRef
    osm: OsmRef
    style_spec_id: str = Field(description="Asset id of a style_spec version (ids pin versions)")
    kit: list[str] = Field(description="Asset ids of kit_piece/material/atlas versions")
    seed: int
    params: dict[str, Any] = {}


class RecipeOut(BaseModel):
    hash: str
    body: dict
    created_by: str
    created_at: datetime
    builds: list[AssetOut] = Field(description="Existing diorama_build assets for this recipe, newest first")
    cached: bool = Field(description="True when an approved build already exists")


class DioramaCreate(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,159}$")
    name: str
    country: str | None = Field(default=None, min_length=2, max_length=2)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DioramaOut(ORM):
    slug: str
    name: str
    country: str | None
    lat: float
    lon: float
    published_build_id: str | None
    distance_km: float | None = None


class PublishRequest(BaseModel):
    build_id: str | None = Field(description="An approved diorama_build, or null to unpublish")


# ---------- manifest ----------
class ManifestFile(BaseModel):
    asset_id: str
    kind: AssetKind
    slug: str
    version: int
    role: str
    sha256: str
    size: int
    media_type: str
    url: str


class ManifestDiorama(BaseModel):
    slug: str
    name: str
    country: str | None
    lat: float
    lon: float
    recipe_hash: str | None
    build: ManifestFile
    dependencies: list[ManifestFile]
    attribution: list[str]


class Manifest(BaseModel):
    version: int
    dioramas: list[ManifestDiorama]


class CatalogEventOut(ORM):
    seq: int
    ts: datetime
    entity: str
    entity_id: str
    action: str


# ---------- jobs ----------
class JobCreate(BaseModel):
    kind: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$", examples=["kit_piece.generate", "diorama.build"])
    input: dict[str, Any]
    estimate_usd: float = Field(default=0, ge=0, description="Checked against the user's budget before enqueue")
    dedupe_key: str | None = Field(default=None, description="Defaults to a hash of kind + input")
    force: bool = Field(default=False, description="Enqueue even if an identical job is open")


class JobOut(ORM):
    id: str
    kind: str
    status: str
    stage: str | None
    progress: float
    input: dict
    dedupe_key: str
    estimate_usd: float
    user_id: str
    worker_id: str | None
    result_asset_ids: list[str]
    error: str | None
    created_at: datetime
    updated_at: datetime
    deduped: bool = False


class JobClaim(BaseModel):
    worker_id: str
    kinds: list[str] = Field(min_length=1)


class JobProgress(BaseModel):
    stage: str | None = None
    progress: float | None = Field(default=None, ge=0, le=1)


class JobComplete(BaseModel):
    status: Literal["succeeded", "failed", "cancelled"]
    result_asset_ids: list[str] = Field(
        default=[],
        description="Assets this job produced or reused. Create new assets with job_id set; reused ones keep their original job "
        "and do not take a share of this job's spend.",
    )
    error: str | None = None


# ---------- prices / ledger ----------
class PriceCreate(BaseModel):
    provider: str
    model: str
    unit: str
    usd_per_unit: float = Field(ge=0)
    effective_from: datetime | None = None
    note: str | None = None


class PriceOut(BaseModel):
    id: int
    provider: str
    model: str
    unit: str
    usd_per_unit: float
    effective_from: datetime
    note: str | None


class UsageCreate(BaseModel):
    provider: str
    model: str
    unit: str
    qty: float
    asset_id: str | None = None
    cost_usd: float | None = Field(
        default=None, description="Override: provider-reported cost. Otherwise priced from the price table."
    )
    note: str | None = None


class AdjustmentCreate(BaseModel):
    user_id: str
    cost_usd: float = Field(description="Negative for refunds or corrections")
    job_id: str | None = None
    asset_id: str | None = None
    note: str


class LedgerEntryOut(BaseModel):
    id: int
    ts: datetime
    user_id: str
    job_id: str | None
    asset_id: str | None
    provider: str
    model: str
    unit: str
    qty: float
    price_id: int | None
    cost_usd: float
    kind: str
    note: str | None


class SummaryRow(BaseModel):
    key: str | None
    cost_usd: float
    entries: int


class AssetCost(BaseModel):
    asset_id: str
    direct_usd: float = Field(description="Entries tagged with this asset, plus its producing job's untagged spend split across the job's results")
    lineage_usd: float = Field(description="direct + every ancestor's direct cost (each ancestor counted once)")


class DioramaCost(BaseModel):
    slug: str
    build_id: str
    build_lineage_usd: float
    kit_amortised_usd: float = Field(description="Each kit asset's lineage cost divided by the number of recipes using it")
    total_usd: float
