"""Authentication routes for local and OIDC flows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import secrets
from typing import Any, Dict
from uuid import UUID

import hashlib
import hmac

try:  # pragma: no cover - optional dependency
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover - fallback for environments without bcrypt
    bcrypt = None
from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import AUDIENCE, ISSUER, Auth, decode_jwt, require_roles
from ..db import get_db


router = APIRouter(tags=["Auth"])

PRIVATE_KEY_PATH = os.getenv("JWT_PRIVATE_KEY_PATH", "app/static/private.pem")
DEFAULT_KID = os.getenv("JWT_LOCAL_KID", "local-rs256")
DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "demo")


def _get_private_key() -> bytes:
    if not os.path.exists(PRIVATE_KEY_PATH):
        raise RuntimeError(
            "Private key not found. Generate it with scripts/make_jwt.py first."
        )
    with open(PRIVATE_KEY_PATH, "rb") as handler:
        return handler.read()


_FALLBACK_PREFIX = "sha256$"


def _hash_password(password: str) -> str:
    if bcrypt is None:
        digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return f"{_FALLBACK_PREFIX}{digest}"
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    if hashed.startswith(_FALLBACK_PREFIX):
        candidate = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(hashed[len(_FALLBACK_PREFIX) :], candidate)
    if bcrypt is None:
        raise HTTPException(status_code=500, detail="bcrypt dependency missing")
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def _get_or_create_demo_tenant(db: Session) -> models.Tenant:
    tenant = db.query(models.Tenant).filter(models.Tenant.name == DEFAULT_TENANT_NAME).first()
    if tenant:
        return tenant
    tenant = models.Tenant(name=DEFAULT_TENANT_NAME)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _get_role(db: Session, role_name: str) -> models.Role:
    role = db.query(models.Role).filter(models.Role.name == role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def _user_to_schema(user: models.User) -> schemas.UserOut:
    # ensure roles are loaded
    _ = [role.name for role in user.roles]
    return schemas.UserOut.model_validate(user)


def _issue_local_token(user: models.User, role_name: str) -> schemas.AuthToken:
    private_key = _get_private_key()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=1)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": role_name,
        "scope": "api.read api.write",
    }
    token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": DEFAULT_KID})
    return schemas.AuthToken(token=token, expires_at=expires)


@router.post("/auth/signup", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.SignUpRequest, db: Session = Depends(get_db)) -> schemas.UserOut:
    """Register a user in the demo tenant with a hashed password."""

    tenant = _get_or_create_demo_tenant(db)
    role = _get_role(db, payload.role)

    existing = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant.id, models.User.email == payload.email)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = models.User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=_hash_password(payload.password),
    )
    user.roles.append(role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.post("/auth/signin", response_model=schemas.AuthToken)
def signin(
    payload: schemas.SignInPasswordRequest | schemas.SignInOIDCRequest,
    db: Session = Depends(get_db),
) -> schemas.AuthToken:
    """Support both local password-based login and OIDC validation."""

    if isinstance(payload, schemas.SignInPasswordRequest):
        tenant = _get_or_create_demo_tenant(db)
        user = (
            db.query(models.User)
            .filter(models.User.tenant_id == tenant.id, models.User.email == payload.email)
            .first()
        )
        if not user or not _verify_password(payload.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        role_name = user.roles[0].name if user.roles else "Paciente"
        return _issue_local_token(user, role_name)

    # OIDC mode
    claims = decode_jwt(payload.id_token)
    expires = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
    return schemas.AuthToken(token=payload.access_token, expires_at=expires)


@router.post("/auth/refresh", response_model=schemas.AuthToken)
def refresh_token(
    payload: schemas.RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> schemas.AuthToken:
    """Issue a new access token using a valid refresh token."""

    try:
        claims = decode_jwt(payload.refresh_token)
        user_id = UUID(claims["sub"])
        tenant_id = UUID(claims["tenant_id"])
        role_name = claims["role"]

        user = db.get(models.User, user_id)
        if not user or user.tenant_id != tenant_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token or user not found")

        return _issue_local_token(user, role_name)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=401, detail=f"Invalid or expired refresh token: {exc}")


@router.post("/auth/assign-role", response_model=schemas.UserOut)
def assign_role(
    payload: schemas.AssignRoleRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(require_roles("Admin")),
) -> schemas.UserOut:
    """Assign an existing role to a user (admin-only)."""

    tenant_id = UUID(claims["tenant_id"])
    user = db.get(models.User, payload.user_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    role = _get_role(db, payload.role)
    if role not in user.roles:
        user.roles.append(role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.post("/auth/mfa/enable", response_model=schemas.UserOut)
def enable_mfa(
    payload: schemas.EnableMFARequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.UserOut:
    """Simulate enabling MFA by storing a generated secret."""

    tenant_id = UUID(claims["tenant_id"])
    actor_id = UUID(claims["sub"])
    target_id = payload.user_id or actor_id

    if payload.user_id and payload.user_id != actor_id and claims.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    user = db.get(models.User, target_id)
    if not user or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")

    user.mfa_enabled = True
    user.mfa_secret = secrets.token_hex(16)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.post("/auth/password/reset", response_model=schemas.UserOut)
def password_reset(
    payload: schemas.PasswordResetRequest,
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.UserOut:
    """Simulated password reset that updates the hashed password."""

    tenant_id = UUID(claims["tenant_id"])
    user = (
        db.query(models.User)
        .filter(models.User.tenant_id == tenant_id, models.User.email == payload.email)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id != UUID(claims["sub"]) and claims.get("role") != "Admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    user.hashed_password = _hash_password(payload.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_to_schema(user)


@router.get("/auth/me", response_model=schemas.MeOut)
def me(
    db: Session = Depends(get_db),
    claims: Dict[str, Any] = Depends(Auth()),
) -> schemas.MeOut:
    """Return the authenticated user's profile along with scopes."""

    user_id = UUID(claims["sub"])
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return schemas.MeOut(
        user=_user_to_schema(user),
        scopes=claims.get("scope", "").split(),
    )

