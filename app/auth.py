"""Authentication and authorization helpers."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTClaimsError, JWTError


HTTP_BEARER = HTTPBearer(auto_error=True)

ISSUER = os.getenv("JWT_ISSUER", "http://localhost:8000")
AUDIENCE = os.getenv("JWT_AUDIENCE", "aiddiag-api")
JWKS_PATH = os.getenv("JWT_PUBLIC_JWKS_PATH", "app/static/jwks.json")
ALLOWED_ALGORITHMS: tuple[str, ...] = ("RS256",)


def _load_jwks() -> Dict[str, Any]:
    """Load the JWKS from the configured location."""

    if not os.path.exists(JWKS_PATH):
        raise RuntimeError(f"JWKS file not found at {JWKS_PATH}")
    with open(JWKS_PATH, "r", encoding="utf-8") as handler:
        return json.load(handler)


def _jwks_by_kid() -> Dict[str, Dict[str, Any]]:
    """Return the JWKS indexed by key id for quick lookup."""

    jwks = _load_jwks()
    keys = jwks.get("keys", [])
    return {k["kid"]: k for k in keys if "kid" in k}


def _get_public_key(kid: str) -> Dict[str, Any]:
    """Resolve a public key from the JWKS by KID."""

    key = _jwks_by_kid().get(kid)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown signing key",
        )
    if key.get("alg") not in ALLOWED_ALGORITHMS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported signing algorithm",
        )
    return key


def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and validate an RS256 JWT token."""

    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing key id")

    key = _get_public_key(kid)

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=list(ALLOWED_ALGORITHMS),
            audience=AUDIENCE,
            issuer=ISSUER,
            options={"verify_aud": True, "verify_iss": True, "verify_exp": True},
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        ) from exc
    except JWTClaimsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims"
        ) from exc
    except JWTError as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    for field in ("sub", "tenant_id", "role", "scope"):
        if field not in claims or not claims[field]:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid claims")

    return claims


class Auth:
    """FastAPI dependency that authenticates incoming requests using JWT."""

    def __call__(
        self, credentials: HTTPAuthorizationCredentials = Depends(HTTP_BEARER)
    ) -> Dict[str, Any]:
        token = credentials.credentials
        return decode_jwt(token)


def require_roles(*roles: str):
    """Dependency factory enforcing that the caller has one of the provided roles."""

    expected = {role for role in roles}

    def _dependency(claims: Dict[str, Any] = Depends(Auth())) -> Dict[str, Any]:
        role = claims.get("role")
        if expected and role not in expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return claims

    return _dependency

