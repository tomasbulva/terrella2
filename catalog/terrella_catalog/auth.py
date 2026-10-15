"""Per-user bearer tokens. Only the SHA-256 of a token is stored."""
from hashlib import sha256
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User

_bearer = HTTPBearer(auto_error=False)


def hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def new_token() -> str:
    return "trl_" + secrets.token_urlsafe(32)


def get_session(request: Request):
    yield from request.app.state.db.session()


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    s: Session = Depends(get_session),
) -> User:
    if creds is None:
        raise HTTPException(401, "missing bearer token")
    user = s.scalar(select(User).where(User.token_hash == hash_token(creds.credentials)))
    if user is None:
        raise HTTPException(401, "invalid token")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"requires role {' or '.join(roles)}")
        return user

    return dep


require_admin = require("admin")
require_worker = require("admin", "worker")
