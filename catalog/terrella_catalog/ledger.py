"""Pricing, budget checks and cost rollups."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import OPEN_JOB_STATUSES, Asset, AssetParent, Job, LedgerEntry, Price, Recipe, User, utcnow


def month_start(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def current_price(s: Session, provider: str, model: str, unit: str, at: datetime | None = None) -> Price | None:
    return s.scalar(
        select(Price)
        .where(
            Price.provider == provider,
            Price.model == model,
            Price.unit == unit,
            Price.effective_from <= (at or utcnow()),
        )
        .order_by(Price.effective_from.desc(), Price.id.desc())
        .limit(1)
    )


def record_usage(
    s: Session,
    *,
    user_id: str,
    recorded_by: str,
    provider: str,
    model: str,
    unit: str,
    qty: float,
    job_id: str | None = None,
    asset_id: str | None = None,
    cost_nanos: int | None = None,
    note: str | None = None,
) -> LedgerEntry:
    price_id = None
    if cost_nanos is None:
        price = current_price(s, provider, model, unit)
        if price is None:
            # Refuse rather than record $0: silent zero-cost rows are how ledgers rot.
            raise HTTPException(422, f"no price for {provider}/{model}/{unit}; add one or pass cost_usd")
        price_id = price.id
        cost_nanos = round(qty * price.nanos_per_unit)
    entry = LedgerEntry(
        user_id=user_id,
        recorded_by=recorded_by,
        provider=provider,
        model=model,
        unit=unit,
        qty=qty,
        job_id=job_id,
        asset_id=asset_id,
        price_id=price_id,
        cost_nanos=cost_nanos,
        note=note,
    )
    s.add(entry)
    return entry


def spent_since(s: Session, user_id: str, since: datetime) -> int:
    return s.scalar(
        select(func.coalesce(func.sum(LedgerEntry.cost_nanos), 0)).where(
            LedgerEntry.user_id == user_id, LedgerEntry.ts >= since
        )
    )


def reserved(s: Session, user_id: str) -> int:
    """Open jobs reserve their estimate minus what they have already been charged."""
    total = 0
    for job in s.scalars(select(Job).where(Job.user_id == user_id, Job.status.in_(OPEN_JOB_STATUSES))):
        charged = s.scalar(
            select(func.coalesce(func.sum(LedgerEntry.cost_nanos), 0)).where(LedgerEntry.job_id == job.id)
        )
        total += max(job.estimate_nanos - charged, 0)
    return total


def check_budget(s: Session, user: User, estimate_nanos: int) -> None:
    if user.monthly_budget_nanos is None:
        return
    committed = spent_since(s, user.id, month_start()) + reserved(s, user.id)
    if committed + estimate_nanos > user.monthly_budget_nanos:
        raise HTTPException(
            402,
            {
                "error": "budget_exceeded",
                "monthly_budget_nanos": user.monthly_budget_nanos,
                "committed_nanos": committed,
                "estimate_nanos": estimate_nanos,
            },
        )


# ---------- per-asset and per-diorama rollups ----------
def asset_direct_nanos(s: Session, asset: Asset) -> int:
    tagged = s.scalar(
        select(func.coalesce(func.sum(LedgerEntry.cost_nanos), 0)).where(LedgerEntry.asset_id == asset.id)
    )
    share = 0
    if asset.job_id:
        job = s.get(Job, asset.job_id)
        untagged = s.scalar(
            select(func.coalesce(func.sum(LedgerEntry.cost_nanos), 0)).where(
                LedgerEntry.job_id == asset.job_id, LedgerEntry.asset_id.is_(None)
            )
        )
        # Split only across results this job owns; reused assets were paid for by their own job.
        owned = s.scalar(select(func.count()).select_from(Asset).where(Asset.job_id == asset.job_id)) if job else 1
        n_results = max(owned, 1)
        share = untagged // n_results
    return tagged + share


def ancestors(s: Session, asset_id: str, stop: set[str] = frozenset()) -> list[tuple[str, str, int]]:
    """Breadth-first (asset_id, role, depth) over parents, each asset once. `stop` ids are not entered."""
    seen = {asset_id}
    out: list[tuple[str, str, int]] = []
    frontier = [asset_id]
    depth = 0
    while frontier:
        depth += 1
        rows = s.execute(select(AssetParent).where(AssetParent.asset_id.in_(frontier))).scalars().all()
        frontier = []
        for r in rows:
            if r.parent_id in seen or r.parent_id in stop:
                continue
            seen.add(r.parent_id)
            out.append((r.parent_id, r.role, depth))
            frontier.append(r.parent_id)
    return out


def asset_lineage_nanos(s: Session, asset: Asset, stop: set[str] = frozenset()) -> int:
    total = asset_direct_nanos(s, asset)
    for parent_id, _, _ in ancestors(s, asset.id, stop):
        total += asset_direct_nanos(s, s.get(Asset, parent_id))
    return total


def recipe_usage_counts(s: Session) -> dict[str, int]:
    """How many recipes reference each shared asset (kit pieces and style specs)."""
    counts: dict[str, int] = {}
    for body in s.scalars(select(Recipe.body)):
        for aid in {*body.get("kit", []), body.get("style_spec_id")}:
            if aid:
                counts[aid] = counts.get(aid, 0) + 1
    return counts


def diorama_cost(s: Session, build: Asset) -> tuple[int, int]:
    """(build lineage excluding shared assets, amortised share of shared assets)."""
    recipe = s.get(Recipe, build.recipe_hash) if build.recipe_hash else None
    shared = set()
    if recipe:
        shared = {*recipe.body.get("kit", []), recipe.body["style_spec_id"]}
    own = asset_lineage_nanos(s, build, stop=shared)
    counts = recipe_usage_counts(s) if shared else {}
    amortised = 0
    for aid in shared:
        a = s.get(Asset, aid)
        if a is not None:
            amortised += asset_lineage_nanos(s, a) // max(counts.get(aid, 1), 1)
    return own, amortised
