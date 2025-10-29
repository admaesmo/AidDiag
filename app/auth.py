import json, os
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
from typing import Dict, Any

HTTP_BEARER = HTTPBearer(auto_error=True)

ISSUER = os.getenv("JWT_ISSUER", "http://localhost:8000")
AUDIENCE = os.getenv("JWT_AUDIENCE", "aiddiag-api")
JWKS_PATH = os.getenv("JWT_PUBLIC_JWKS_PATH", "app/static/jwks.json")

with open(JWKS_PATH, "r") as f:
    JWKS = json.load(f)

def _get_key(kid: str) -> Dict[str, Any]:
    for k in JWKS.get("keys", []):
        if k.get("kid") == kid:
            return k
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid KID")

def verify_jwt(token: str) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = _get_key(kid)

        from jose.utils import base64url_decode
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        n = int.from_bytes(base64url_decode(key["n"].encode()), "big")
        e = int.from_bytes(base64url_decode(key["e"].encode()), "big")
        public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())

        claims = jwt.decode(
            token,
            public_key,
            audience=AUDIENCE,
            options={"verify_at_hash": False, "verify_aud": True, "verify_exp": True, "verify_iss": True},
            algorithms=[key["alg"]],
            issuer=ISSUER,
        )
        if "tenant_id" not in claims or "role" not in claims or "sub" not in claims:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid claims")
        return claims
    except Exception as ex:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(ex))

def Auth(required_roles=None):
    def _dep(creds: HTTPAuthorizationCredentials = Depends(HTTP_BEARER)):
        claims = verify_jwt(creds.credentials)
        if required_roles and claims.get("role") not in required_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return claims
    return _dep