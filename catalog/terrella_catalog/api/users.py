from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, get_session, hash_token, new_token, require_admin
from ..ledger import month_start, reserved, spent_since
from ..models import User
from ..schemas import BudgetOut, UserCreate, UserCreated, UserOut, nanos, usd

router = APIRouter(prefix="/users", tags=["users"])


def user_out(u: User) -> UserOut:
    return UserOut(id=u.id, name=u.name, role=u.role, monthly_budget_usd=usd(u.monthly_budget_nanos))


@router.post("", response_model=UserCreated, status_code=201)
def create_user(body: UserCreate, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    if s.scalar(select(User).where(User.name == body.name)):
        raise HTTPException(409, "name taken")
    token = new_token()
    u = User(name=body.name, role=body.role, token_hash=hash_token(token), monthly_budget_nanos=nanos(body.monthly_budget_usd))
    s.add(u)
    s.commit()
    return UserCreated(**user_out(u).model_dump(), token=token)


@router.get("", response_model=list[UserOut])
def list_users(s: Session = Depends(get_session), _: User = Depends(require_admin)):
    return [user_out(u) for u in s.scalars(select(User).order_by(User.name))]


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/{user_id}/budget", response_model=BudgetOut)
def budget(user_id: str, s: Session = Depends(get_session), caller: User = Depends(current_user)):
    if user_id == "me":
        user_id = caller.id
    if caller.id != user_id and caller.role != "admin":
        raise HTTPException(403, "only admins can read other users' budgets")
    u = s.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    spent = spent_since(s, u.id, month_start())
    res = reserved(s, u.id)
    remaining = None if u.monthly_budget_nanos is None else u.monthly_budget_nanos - spent - res
    return BudgetOut(
        monthly_budget_usd=usd(u.monthly_budget_nanos),
        spent_this_month_usd=usd(spent),
        reserved_usd=usd(res),
        remaining_usd=usd(remaining),
    )


@router.patch("/{user_id}/budget", response_model=UserOut)
def set_budget(user_id: str, body: dict, s: Session = Depends(get_session), _: User = Depends(require_admin)):
    u = s.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    value = body.get("monthly_budget_usd")
    if value is not None and (not isinstance(value, (int, float)) or value < 0):
        raise HTTPException(422, "monthly_budget_usd must be a non-negative number or null")
    u.monthly_budget_nanos = nanos(value)
    s.commit()
    return user_out(u)
