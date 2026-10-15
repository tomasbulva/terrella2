"""Job queue. Users enqueue (budget-checked), workers claim, report usage and complete.

Usage reported against a job is charged to the user who enqueued it, not the worker.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..auth import current_user, get_session, require_worker
from ..ledger import check_budget, record_usage
from ..models import OPEN_JOB_STATUSES, Asset, Job, User, utcnow
from ..recipes import recipe_hash
from ..schemas import JobClaim, JobComplete, JobCreate, JobOut, JobProgress, LedgerEntryOut, UsageCreate, nanos
from .common import entry_out, get_or_404, job_out

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _visible(job: Job, user: User) -> None:
    if user.role == "user" and job.user_id != user.id:
        raise HTTPException(404, f"job {job.id} not found")


def _open(job: Job) -> None:
    if job.status not in OPEN_JOB_STATUSES:
        raise HTTPException(409, f"job is {job.status}")


@router.post("", response_model=JobOut, status_code=201)
def enqueue(body: JobCreate, response: Response, s: Session = Depends(get_session), user: User = Depends(current_user)):
    key = body.dedupe_key or recipe_hash({"kind": body.kind, "input": body.input})
    if not body.force:
        existing = s.scalar(
            select(Job).where(Job.dedupe_key == key, Job.status.in_(OPEN_JOB_STATUSES)).order_by(Job.created_at).limit(1)
        )
        if existing:
            response.status_code = 200
            return job_out(existing, deduped=True)
    estimate = nanos(body.estimate_usd)
    check_budget(s, user, estimate)
    job = Job(kind=body.kind, input=body.input, dedupe_key=key, estimate_nanos=estimate, user_id=user.id)
    s.add(job)
    s.commit()
    return job_out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = None,
    kind: str | None = None,
    limit: int = Query(100, le=1000),
    s: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    q = select(Job)
    if user.role == "user":
        q = q.where(Job.user_id == user.id)
    if status:
        q = q.where(Job.status == status)
    if kind:
        q = q.where(Job.kind == kind)
    return [job_out(j) for j in s.scalars(q.order_by(Job.created_at.desc()).limit(limit))]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, s: Session = Depends(get_session), user: User = Depends(current_user)):
    job = get_or_404(s, Job, job_id, "job")
    _visible(job, user)
    return job_out(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel(job_id: str, s: Session = Depends(get_session), user: User = Depends(current_user)):
    job = get_or_404(s, Job, job_id, "job")
    _visible(job, user)
    _open(job)
    job.status = "cancelled"  # a running worker sees this on its next progress call
    s.commit()
    return job_out(job)


@router.post("/claim", response_model=JobOut | None, summary="Worker: take the oldest queued job of the given kinds")
def claim(body: JobClaim, response: Response, s: Session = Depends(get_session), _: User = Depends(require_worker)):
    for _attempt in range(5):
        job = s.scalar(
            select(Job).where(Job.status == "queued", Job.kind.in_(body.kinds)).order_by(Job.created_at, Job.id).limit(1)
        )
        if job is None:
            response.status_code = 204
            return None
        # Compare-and-set so two workers can't take the same job.
        won = s.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(status="running", worker_id=body.worker_id, stage="claimed", updated_at=utcnow())
        ).rowcount
        s.commit()
        if won:
            s.refresh(job)
            return job_out(job)
    raise HTTPException(503, "contention; retry")


@router.post("/{job_id}/progress", response_model=JobOut, summary="Worker: update stage/progress. 409 if cancelled.")
def progress(job_id: str, body: JobProgress, s: Session = Depends(get_session), _: User = Depends(require_worker)):
    job = get_or_404(s, Job, job_id, "job")
    _open(job)
    if body.stage is not None:
        job.stage = body.stage
    if body.progress is not None:
        job.progress = body.progress
    s.commit()
    return job_out(job)


@router.post("/{job_id}/usage", response_model=LedgerEntryOut, status_code=201, summary="Worker: record spend, charged to the job's owner")
def usage(job_id: str, body: UsageCreate, s: Session = Depends(get_session), worker: User = Depends(require_worker)):
    job = get_or_404(s, Job, job_id, "job")
    if body.asset_id:
        get_or_404(s, Asset, body.asset_id, "asset")
    # Allowed after completion too: provider invoices can land late.
    entry = record_usage(
        s, user_id=job.user_id, recorded_by=worker.id, provider=body.provider, model=body.model, unit=body.unit,
        qty=body.qty, job_id=job.id, asset_id=body.asset_id, cost_nanos=nanos(body.cost_usd), note=body.note,
    )
    s.commit()
    return entry_out(entry)


@router.post("/{job_id}/complete", response_model=JobOut)
def complete(job_id: str, body: JobComplete, s: Session = Depends(get_session), _: User = Depends(require_worker)):
    job = get_or_404(s, Job, job_id, "job")
    if job.status == "cancelled" and body.status != "cancelled":
        raise HTTPException(409, "job was cancelled")
    if job.status not in (*OPEN_JOB_STATUSES, "cancelled"):
        raise HTTPException(409, f"job is {job.status}")
    # Results may be this job's new assets or existing ones it reused. Ownership (asset.job_id) is set
    # only at creation, so reusing an asset never moves its cost.
    for aid in body.result_asset_ids:
        get_or_404(s, Asset, aid, "result asset")
    job.status = body.status
    job.result_asset_ids = body.result_asset_ids
    job.error = body.error
    if body.status == "succeeded":
        job.progress = 1.0
    s.commit()
    return job_out(job)
