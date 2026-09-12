"""
Authentication & authorization for the MPLADS auditor portal.

- Passwords: bcrypt via passlib (never stored in plain text)
- Sessions: signed JWT bearer tokens (24 h validity)
- Roles: 'public' | 'analyst' | 'auditor' | 'admin'

Role capabilities (enforced by require_role()):
  public  — read-only project analytics (all existing endpoints stay public)
  analyst — save projects, create/manage own investigations
  auditor — everything an analyst can do + save/manage audit cases
  admin   — everything + user management + system-wide investigation view

Users can only ever read/write their OWN saved projects, investigations and
cases; broader access requires an explicit role grant (admin sees all).
"""

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import models

# `get_db` lives in main.py (defined next to SessionLocal); importing it here
# would create a circular import, so auth declares its own identical session
# dependency over the same engine.
from database import SessionLocal

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Configuration ────────────────────────────────────────────────────────
# Secret can be overridden via env var; the default is generated per process
# so tokens never use a well-known value. Set MPLADS_JWT_SECRET for stability
# across restarts (e.g. behind a load balancer).
SECRET_KEY = os.environ.get("MPLADS_JWT_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
RESET_TOKEN_EXPIRE_MINUTES = 30

ROLES = ("public", "analyst", "auditor", "admin")
# Higher rank = broader access. admin(3) passes auditor(2) checks, etc.
ROLE_RANK = {"public": 0, "analyst": 1, "auditor": 2, "admin": 3}

# bcrypt 5.x raises on >72-byte secrets; passlib 1.7.4 predates that API.
# Pinning to the last bcrypt 4.x release restores compatibility.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__ident="2b",
)
try:
    import logging
    logging.getLogger("passlib").setLevel(logging.ERROR)
except Exception:
    pass
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(user_id: int, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_reset_token() -> str:
    return secrets.token_urlsafe(32)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%S")


# ── Current-user resolution ──────────────────────────────────────────────
def _decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User | None:
    """Resolve the bearer token to a User row; None when unauthenticated.

    Optional by design — analytics endpoints remain public without a token.
    """
    if credentials is None or not credentials.credentials:
        return None
    user_id = _decode_token(credentials.credentials)
    if user_id is None:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        return None
    return user


def require_role(minimum_role: str):
    """
    Dependency factory: 401 when not authenticated, 403 when the account's
    role ranks below `minimum_role`. Admin passes every check.
    """

    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: Session = Depends(get_db),
    ) -> models.User:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = _decode_token(credentials.credentials)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid — please sign in again",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found or disabled")
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{minimum_role}' role",
            )
        return user

    return dependency


def require_self_or_admin(user: models.User, owner_id: int):
    """Guards user-scoped resources: only the owner (or admin) may access."""
    if user.id != owner_id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own records")
