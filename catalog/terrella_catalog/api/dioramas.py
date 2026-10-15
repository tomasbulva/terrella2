from math import asin, cos, radians, sin, sqrt

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user, get_session, require_admin
from ..ledger import ancestors, diorama_cost
from ..models import Asset, AssetParent, CatalogEvent, Diorama, Recipe, User
from ..recipes import normalize_recipe, recipe_hash
from ..schemas import (
    CatalogEventOut,
    DioramaCost,
    DioramaCreate,
    DioramaOut,
    Manifest,
    ManifestDiorama,
    ManifestFile,
    PublishRequest,
    RecipeBody,
    RecipeOut,
    usd,
)
from .assets import SHIPPED_KINDS
from .common import asset_out, blob_url, emit, get_or_404

router = APIRouter()

KIT_KINDS = {"kit_piece", "material", "atlas"}


# ---------- recipes ----------
def recipe_out(request: Request, s: Session, r: Recipe) -> RecipeOut:
    builds = s.scalars(
        select(Asset).where(Asset.recipe_hash == r.hash, Asset.kind == "diorama_build").order_by(Asset.created_at.desc())
    ).all()
    return RecipeOut(
        hash=r.hash,
        body=r.body,
        created_by=r.created_by,
        created_at=r.created_at,
        builds=[asset_out(request, b) for b in builds],
        cached=any(b.status == "approved" for b in builds),
    )


@router.post("/recipes", response_model=RecipeOut, tags=["recipes"], summary="Register a recipe (idempotent by content hash)")
def put_recipe(body: RecipeBody, request: Request, response: Response, s: Session = Depends(get_session), user: User = Depends(current_user)):
    spec = get_or_404(s, Asset, body.style_spec_id, "style_spec")
    if spec.kind != "style_spec":
        raise HTTPException(422, f"{body.style_spec_id} is a {spec.kind}, not a style_spec")
    if not body.kit:
        raise HTTPException(422, "kit must list at least one asset")
    for aid in body.kit:
        a = get_or_404(s, Asset, aid, "kit asset")
        if a.kind not in KIT_KINDS:
            raise HTTPException(422, f"kit entry {aid} is a {a.kind}; expected one of {sorted(KIT_KINDS)}")
        if a.status in ("rejected", "deprecated"):
            raise HTTPException(422, f"kit entry {aid} is {a.status}")
    canonical = normalize_recipe(body.model_dump(mode="json"))
    h = recipe_hash(canonical)
    r = s.get(Recipe, h)
    if r is None:
        r = Recipe(hash=h, body=canonical, created_by=user.id)
        s.add(r)
        s.commit()
        response.status_code = 201
    return recipe_out(request, s, r)


@router.get("/recipes/{h}", response_model=RecipeOut, tags=["recipes"])
def get_recipe(h: str, request: Request, s: Session = Depends(get_session), _: User = Depends(current_user)):
    return recipe_out(request, s, get_or_404(s, Recipe, h, "recipe"))


# ---------- dioramas ----------
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


@router.post("/dioramas", response_model=DioramaOut, status_code=201, tags=["dioramas"])
def create_diorama(body: DioramaCreate, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    if s.get(Diorama, body.slug):
        raise HTTPException(409, "slug taken")
    d = Diorama(**body.model_dump())
    s.add(d)
    s.commit()
    return d


@router.get("/dioramas", response_model=list[DioramaOut], tags=["dioramas"], summary="List, or find nearest with lat/lon (public)")
def list_dioramas(
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    published_only: bool = True,
    limit: int = Query(20, le=200),
    s: Session = Depends(get_session),
):
    q = select(Diorama)
    if published_only:
        q = q.where(Diorama.published_build_id.is_not(None))
    rows = [DioramaOut.model_validate(d) for d in s.scalars(q)]
    if lat is not None and lon is not None:
        for r in rows:
            r.distance_km = round(haversine_km(lat, lon, r.lat, r.lon), 3)
        rows.sort(key=lambda r: r.distance_km)
    else:
        rows.sort(key=lambda r: r.slug)
    return rows[:limit]


@router.get("/dioramas/{slug}", response_model=DioramaOut, tags=["dioramas"])
def get_diorama(slug: str, s: Session = Depends(get_session)):
    return get_or_404(s, Diorama, slug, "diorama")


@router.post("/dioramas/{slug}/publish", response_model=DioramaOut, tags=["dioramas"])
def publish(slug: str, body: PublishRequest, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    d = get_or_404(s, Diorama, slug, "diorama")
    if body.build_id is None:
        d.published_build_id = None
        emit(s, "diorama", slug, "unpublished")
    else:
        b = get_or_404(s, Asset, body.build_id, "build")
        if b.kind != "diorama_build" or b.status != "approved":
            raise HTTPException(422, "only approved diorama_build assets can be published")
        d.published_build_id = b.id
        emit(s, "diorama", slug, "published")
    s.commit()
    return d


@router.get("/dioramas/{slug}/cost", response_model=DioramaCost, tags=["ledger"])
def get_diorama_cost(slug: str, build_id: str | None = None, s: Session = Depends(get_session), _: User = Depends(current_user)):
    d = get_or_404(s, Diorama, slug, "diorama")
    bid = build_id or d.published_build_id
    if not bid:
        raise HTTPException(404, "diorama has no published build; pass build_id")
    build = get_or_404(s, Asset, bid, "build")
    own, amortised = diorama_cost(s, build)
    return DioramaCost(slug=slug, build_id=bid, build_lineage_usd=usd(own), kit_amortised_usd=usd(amortised), total_usd=usd(own + amortised))


# ---------- client manifest ----------
def manifest_file(request: Request, a: Asset, role: str) -> ManifestFile:
    return ManifestFile(
        asset_id=a.id, kind=a.kind, slug=a.slug, version=a.version, role=role,
        sha256=a.blob.sha256, size=a.blob.size, media_type=a.blob.media_type, url=blob_url(request, a.blob.sha256),
    )


@router.get("/catalog/manifest", response_model=Manifest, tags=["catalog"], summary="Everything a client needs (public)")
def manifest(request: Request, s: Session = Depends(get_session)):
    version = s.scalar(select(func.coalesce(func.max(CatalogEvent.seq), 0)))
    out = []
    for d in s.scalars(select(Diorama).where(Diorama.published_build_id.is_not(None)).order_by(Diorama.slug)):
        build = s.get(Asset, d.published_build_id)
        deps = []
        for p in s.scalars(select(AssetParent).where(AssetParent.asset_id == build.id)):
            parent = s.get(Asset, p.parent_id)
            if parent.kind in SHIPPED_KINDS and parent.blob_sha256:
                deps.append(manifest_file(request, parent, p.role))
        attributions = []
        for a in [build, *(s.get(Asset, aid) for aid, _, _ in ancestors(s, build.id))]:
            text = a.provenance.get("attribution")
            if text and text not in attributions:
                attributions.append(text)
        out.append(
            ManifestDiorama(
                slug=d.slug, name=d.name, country=d.country, lat=d.lat, lon=d.lon, recipe_hash=build.recipe_hash,
                build=manifest_file(request, build, "build"),
                dependencies=sorted(deps, key=lambda f: (f.kind, f.slug)),
                attribution=attributions,
            )
        )
    return Manifest(version=version, dioramas=out)


@router.get("/catalog/changes", response_model=list[CatalogEventOut], tags=["catalog"], summary="Events after `since` (public)")
def changes(since: int = 0, limit: int = Query(500, le=5000), s: Session = Depends(get_session)):
    return s.scalars(select(CatalogEvent).where(CatalogEvent.seq > since).order_by(CatalogEvent.seq).limit(limit)).all()
