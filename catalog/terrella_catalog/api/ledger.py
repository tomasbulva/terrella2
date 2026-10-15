from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user, get_session, require_admin, require_worker
from ..ledger import record_usage
from ..models import Asset, Job, LedgerEntry, Price, User
from ..schemas import AdjustmentCreate, LedgerEntryOut, PriceCreate, PriceOut, SummaryRow, UsageCreate, nanos, usd
from .common import entry_out, get_or_404, price_out

router = APIRouter(tags=["ledger"])

GROUPS = {
    "user": LedgerEntry.user_id,
    "job": LedgerEntry.job_id,
    "asset": LedgerEntry.asset_id,
    "provider": LedgerEntry.provider,
    "model": LedgerEntry.model,
    "unit": LedgerEntry.unit,
}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@router.post("/prices", response_model=PriceOut, status_code=201)
def add_price(body: PriceCreate, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    kwargs = dict(
        provider=body.provider, model=body.model, unit=body.unit, nanos_per_unit=nanos(body.usd_per_unit), note=body.note
    )
    if body.effective_from:
        kwargs["effective_from"] = _utc(body.effective_from)
    p = Price(**kwargs)
    s.add(p)
    s.commit()
    return price_out(p)


@router.get("/prices", response_model=list[PriceOut])
def list_prices(s: Session = Depends(get_session), _: User = Depends(current_user)):
    return [price_out(p) for p in s.scalars(select(Price).order_by(Price.provider, Price.model, Price.unit, Price.effective_from))]


@router.post("/ledger/usage", response_model=LedgerEntryOut, status_code=201, summary="Worker: spend not tied to a job (charged to caller)")
def usage(body: UsageCreate, s: Session = Depends(get_session), worker: User = Depends(require_worker)):
    if body.asset_id:
        get_or_404(s, Asset, body.asset_id, "asset")
    e = record_usage(
        s, user_id=worker.id, recorded_by=worker.id, provider=body.provider, model=body.model, unit=body.unit,
        qty=body.qty, asset_id=body.asset_id, cost_nanos=nanos(body.cost_usd), note=body.note,
    )
    s.commit()
    return entry_out(e)


@router.post("/ledger/adjustments", response_model=LedgerEntryOut, status_code=201, summary="Admin: corrections and refunds")
def adjust(body: AdjustmentCreate, s: Session = Depends(get_session), admin: User = Depends(require_admin)):
    get_or_404(s, User, body.user_id, "user")
    if body.job_id:
        get_or_404(s, Job, body.job_id, "job")
    if body.asset_id:
        get_or_404(s, Asset, body.asset_id, "asset")
    e = LedgerEntry(
        user_id=body.user_id, recorded_by=admin.id, provider="adjustment", model="-", unit="usd", qty=1,
        cost_nanos=nanos(body.cost_usd), kind="adjustment", job_id=body.job_id, asset_id=body.asset_id, note=body.note,
    )
    s.add(e)
    s.commit()
    return entry_out(e)


def _filtered(q, user: User, user_id, job_id, asset_id, since, until):
    if user.role == "user":
        if user_id not in (None, user.id):
            raise HTTPException(403, "users can only read their own ledger")
        user_id = user.id
    for col, val in ((LedgerEntry.user_id, user_id), (LedgerEntry.job_id, job_id), (LedgerEntry.asset_id, asset_id)):
        if val is not None:
            q = q.where(col == val)
    if since:
        q = q.where(LedgerEntry.ts >= _utc(since))
    if until:
        q = q.where(LedgerEntry.ts < _utc(until))
    return q


@router.get("/ledger/entries", response_model=list[LedgerEntryOut])
def entries(
    user_id: str | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(200, le=5000),
    offset: int = 0,
    s: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    q = _filtered(select(LedgerEntry), user, user_id, job_id, asset_id, since, until)
    return [entry_out(e) for e in s.scalars(q.order_by(LedgerEntry.ts.desc(), LedgerEntry.id.desc()).limit(limit).offset(offset))]


@router.get("/ledger/summary", response_model=list[SummaryRow])
def summary(
    group_by: Literal["user", "job", "asset", "provider", "model", "unit", "day", "month"] = "user",
    user_id: str | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    s: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    if group_by in ("day", "month"):
        # Group in Python: date truncation SQL differs between SQLite and Postgres.
        q = _filtered(select(LedgerEntry.ts, LedgerEntry.cost_nanos), user, user_id, job_id, asset_id, since, until)
        fmt = "%Y-%m-%d" if group_by == "day" else "%Y-%m"
        acc: dict[str, list[int]] = {}
        for ts, cost in s.execute(q):
            k = ts.strftime(fmt)
            acc.setdefault(k, [0, 0])
            acc[k][0] += cost
            acc[k][1] += 1
        return [SummaryRow(key=k, cost_usd=usd(v[0]), entries=v[1]) for k, v in sorted(acc.items())]
    col = GROUPS[group_by]
    q = select(col, func.sum(LedgerEntry.cost_nanos), func.count()).group_by(col)
    q = _filtered(q, user, user_id, job_id, asset_id, since, until)
    rows = s.execute(q).all()
    return sorted((SummaryRow(key=k, cost_usd=usd(c), entries=n) for k, c, n in rows), key=lambda r: -r.cost_usd)
