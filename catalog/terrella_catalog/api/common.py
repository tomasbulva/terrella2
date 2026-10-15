from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ..models import Asset, CatalogEvent, Job, LedgerEntry, Price
from ..schemas import AssetOut, JobOut, LedgerEntryOut, ParentRef, PriceOut, usd


def blob_url(request: Request, sha: str) -> str:
    base = request.app.state.settings.public_base_url
    return f"{base}/blobs/{sha}"


def asset_out(request: Request, a: Asset) -> AssetOut:
    out = AssetOut.model_validate(a, from_attributes=True).model_copy(
        update={"parents": [ParentRef(asset_id=p.parent_id, role=p.role) for p in a.parents]}
    )
    if a.blob_sha256:
        out.url = blob_url(request, a.blob_sha256)
    return out


def job_out(j: Job, deduped: bool = False) -> JobOut:
    return JobOut.model_validate(
        {**{c: getattr(j, c) for c in JobOut.model_fields if hasattr(j, c)}, "estimate_usd": usd(j.estimate_nanos), "deduped": deduped}
    )


def entry_out(e: LedgerEntry) -> LedgerEntryOut:
    return LedgerEntryOut.model_validate(
        {**{c: getattr(e, c) for c in LedgerEntryOut.model_fields if hasattr(e, c)}, "cost_usd": usd(e.cost_nanos)}
    )


def price_out(p: Price) -> PriceOut:
    return PriceOut.model_validate(
        {**{c: getattr(p, c) for c in PriceOut.model_fields if hasattr(p, c)}, "usd_per_unit": usd(p.nanos_per_unit)}
    )


def get_or_404(s: Session, model, key, what: str):
    obj = s.get(model, key)
    if obj is None:
        raise HTTPException(404, f"{what} {key} not found")
    return obj


def emit(s: Session, entity: str, entity_id: str, action: str) -> None:
    s.add(CatalogEvent(entity=entity, entity_id=entity_id, action=action))
