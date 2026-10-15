from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user, get_session, require_admin
from ..ledger import ancestors, asset_direct_nanos, asset_lineage_nanos
from ..models import Asset, AssetParent, Blob, Job, Recipe, User
from ..schemas import AssetCost, AssetCreate, AssetKind, AssetOut, AssetStatus, AssetStatusUpdate, BlobOut, LineageNode, usd
from ..storage import sniff_media_type
from .common import asset_out, emit, get_or_404

router = APIRouter(tags=["assets"])

MAX_BLOB_BYTES = 200 * 1024 * 1024
GLB_KINDS = {"kit_piece", "diorama_build"}
# Kinds whose approval changes what clients download.
SHIPPED_KINDS = {"kit_piece", "material", "atlas", "diorama_build"}


@router.put("/blobs", response_model=BlobOut, status_code=201, summary="Upload raw bytes; returns their SHA-256")
async def put_blob(request: Request, s: Session = Depends(get_session), _: User = Depends(current_user)):
    data = await request.body()
    if not data:
        raise HTTPException(422, "empty body")
    if len(data) > MAX_BLOB_BYTES:
        raise HTTPException(413, "blob too large")
    digest = request.app.state.blobs.put(data)
    blob = s.get(Blob, digest)
    if blob is None:
        blob = Blob(sha256=digest, size=len(data), media_type=sniff_media_type(data, request.headers.get("content-type")))
        s.add(blob)
        s.commit()
    return blob


@router.get("/blobs/{sha}", summary="Download bytes by hash (public; hashes are unguessable)")
def get_blob(sha: str, request: Request, s: Session = Depends(get_session)):
    blob = get_or_404(s, Blob, sha, "blob")
    return FileResponse(
        request.app.state.blobs.path(sha),
        media_type=blob.media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{sha}"'},
    )


@router.post("/assets", response_model=AssetOut, status_code=201, summary="Create the next version of (kind, slug), or reuse an identical latest one")
def create_asset(
    body: AssetCreate, request: Request, response: Response, s: Session = Depends(get_session), user: User = Depends(current_user)
):
    if body.kind == "style_spec":
        if body.spec is None:
            raise HTTPException(422, "style_spec assets need `spec`")
    elif body.spec is not None:
        raise HTTPException(422, "`spec` is only valid on style_spec assets")
    if body.kind != "style_spec" and not body.blob_sha256:
        raise HTTPException(422, f"{body.kind} assets need `blob_sha256` (PUT /blobs first)")
    if body.blob_sha256:
        blob = get_or_404(s, Blob, body.blob_sha256, "blob")
        if body.kind in GLB_KINDS and blob.media_type != "model/gltf-binary":
            raise HTTPException(422, f"{body.kind} must be a .glb (got {blob.media_type})")
    if body.kind == "diorama_build" and not body.recipe_hash:
        raise HTTPException(422, "diorama_build assets need `recipe_hash`")
    if body.recipe_hash:
        get_or_404(s, Recipe, body.recipe_hash, "recipe")
    if body.job_id:
        get_or_404(s, Job, body.job_id, "job")
    for p in body.parents:
        get_or_404(s, Asset, p.asset_id, "parent asset")

    spec = body.spec.model_dump(mode="json") if body.spec else None
    latest = s.scalar(
        select(Asset).where(Asset.kind == body.kind, Asset.slug == body.slug).order_by(Asset.version.desc()).limit(1)
    )
    if (
        body.dedupe
        and latest is not None
        and latest.status != "rejected"
        and latest.blob_sha256 == body.blob_sha256
        and latest.spec == spec
    ):
        response.status_code = 200
        return asset_out(request, latest).model_copy(update={"reused": True})
    version = (latest.version if latest else 0) + 1
    asset = Asset(
        kind=body.kind,
        slug=body.slug,
        version=version,
        style_family=body.style_family,
        category=body.category,
        blob_sha256=body.blob_sha256,
        spec=spec,
        meta=body.meta,
        tags=body.tags,
        provenance=body.provenance.model_dump(mode="json", exclude_none=True),
        recipe_hash=body.recipe_hash,
        job_id=body.job_id,
        created_by=user.id,
    )
    s.add(asset)
    s.flush()
    for p in {(p.asset_id, p.role) for p in body.parents}:
        s.add(AssetParent(asset_id=asset.id, parent_id=p[0], role=p[1]))
    s.commit()
    s.refresh(asset)
    return asset_out(request, asset)


@router.get("/assets", response_model=list[AssetOut])
def list_assets(
    request: Request,
    kind: AssetKind | None = None,
    slug: str | None = None,
    status: AssetStatus | None = None,
    style_family: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    latest: bool = Query(False, description="Only the highest version per (kind, slug)"),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    s: Session = Depends(get_session),
    _: User = Depends(current_user),
):
    q = select(Asset)
    for col, val in ((Asset.kind, kind), (Asset.slug, slug), (Asset.status, status), (Asset.style_family, style_family), (Asset.category, category)):
        if val is not None:
            q = q.where(col == val)
    if latest:
        sub = select(Asset.kind, Asset.slug, func.max(Asset.version).label("v")).group_by(Asset.kind, Asset.slug).subquery()
        q = q.join(sub, (Asset.kind == sub.c.kind) & (Asset.slug == sub.c.slug) & (Asset.version == sub.c.v))
    rows = s.scalars(q.order_by(Asset.created_at.desc(), Asset.id)).all()
    if tag:  # JSON containment differs across backends; filter in Python while the catalog is small
        rows = [a for a in rows if tag in (a.tags or [])]
    return [asset_out(request, a) for a in rows[offset : offset + limit]]


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: str, request: Request, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return asset_out(request, get_or_404(s, Asset, asset_id, "asset"))


@router.get("/assets/{asset_id}/lineage", response_model=list[LineageNode], summary="All ancestors, breadth-first")
def lineage(asset_id: str, request: Request, s: Session = Depends(get_session), _: User = Depends(current_user)):
    get_or_404(s, Asset, asset_id, "asset")
    return [LineageNode(asset=asset_out(request, s.get(Asset, aid)), role=role, depth=d) for aid, role, d in ancestors(s, asset_id)]


@router.post("/assets/{asset_id}/status", response_model=AssetOut, summary="Approve, reject or deprecate (admin)")
def set_status(asset_id: str, body: AssetStatusUpdate, request: Request, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    asset = get_or_404(s, Asset, asset_id, "asset")
    if asset.status == body.status:
        return asset_out(request, asset)
    asset.status = body.status
    if body.reason:
        asset.meta = {**asset.meta, "status_reason": body.reason}
    if asset.kind in SHIPPED_KINDS and body.status in ("approved", "deprecated"):
        emit(s, "asset", asset.id, body.status)
    s.commit()
    return asset_out(request, asset)


@router.get("/assets/{asset_id}/cost", response_model=AssetCost)
def asset_cost(asset_id: str, s: Session = Depends(get_session), _: User = Depends(current_user)):
    asset = get_or_404(s, Asset, asset_id, "asset")
    return AssetCost(asset_id=asset.id, direct_usd=usd(asset_direct_nanos(s, asset)), lineage_usd=usd(asset_lineage_nanos(s, asset)))
